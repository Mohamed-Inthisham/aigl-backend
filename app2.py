from flask import Flask, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, JWTManager, get_jwt_identity, get_jwt
from pymongo import MongoClient, errors # Import MongoClient and errors here as they are used in this file
import os
import logging
import yaml # Import yaml

# Import our fixed auth_utils module - assuming auth_utils.py is in the same directory
from auth_utils import register_user, verify_password

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Set a strong JWT secret key
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "your-jwt-secret-key")
if app.config["JWT_SECRET_KEY"] == "your-jwt-secret-key":
    logger.warning("Using default JWT secret key. This is insecure for production.")

jwt = JWTManager(app)

# --- Endpoints ---

@app.route('/register', methods=['POST'])
def register():
    return register_user() # Call register_user from auth_utils which now handles DB connection

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    if not data:
        return jsonify({"msg": "No data provided"}), 400

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        logger.warning(f"Login failed: Missing username or password for user {username}")
        return jsonify({"msg": "Missing username or password"}), 400

    mongo_client = None # Initialize mongo_client here
    try:
        # Load database secrets from yaml file
        with open('secrets.yaml') as f:
            secrets = yaml.load(f, Loader=yaml.FullLoader)
        mongo_uri = secrets['MONGO_DB_URI']
        mongo_db_name = 'Elearning' # Assuming database name is 'Elearning' as per your config

        # Establish database connection WITHIN login function
        mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        mongo_client.server_info() # validate connection
        db = mongo_client[mongo_db_name]
        users_collection = db.users

        user = users_collection.find_one({'username': username})

        if not user:
            logger.info(f"Login failed: User {username} not found")
            return jsonify({"msg": "Invalid username or password"}), 401

        if verify_password(password, user['password_hash']):
            access_token = create_access_token(identity=username, additional_claims={'role': user['role']})
            logger.info(f"User {username} logged in successfully")
            return jsonify(access_token=access_token), 200
        else:
            logger.info(f"Login failed: Incorrect password for user {username}")
            return jsonify({"msg": "Invalid username or password"}), 401

    except errors.PyMongoError as e:
        logger.error(f"MongoDB error during login: {e}")
        return jsonify({"msg": f"Login failed due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return jsonify({"msg": "Login failed due to a server error"}), 500
    finally:
        if mongo_client:
            mongo_client.close()


@app.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    current_user_username = get_jwt_identity()
    claims = get_jwt()
    user_role = claims.get('role')

    return jsonify(
        message=f"Hello, {current_user_username}! You are a {user_role}.",
        user_identity=current_user_username,
        user_role=user_role
    ), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint to check if the application and database are healthy"""
    mongo_client = None # Initialize mongo_client here
    try:
        # Load database secrets from yaml file
        with open('secrets.yaml') as f:
            secrets = yaml.load(f, Loader=yaml.FullLoader)
        mongo_uri = secrets['MONGO_DB_URI']
        mongo_db_name = 'Elearning' # Assuming database name is 'Elearning' as per your config

        # Establish database connection WITHIN health_check function
        mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 500
    finally:
        if mongo_client:
            mongo_client.close()


if __name__ == '__main__':
    logger.info("Starting Flask application...")
    app.run(debug=True, host='0.0.0.0', port=5001)