from flask import Flask, request, jsonify, send_from_directory
from flask_jwt_extended import create_access_token, jwt_required, JWTManager, get_jwt_identity, get_jwt
from pymongo import MongoClient, errors
import os
import logging
import yaml
from werkzeug.utils import secure_filename

# Import our updated auth_utils module
from auth_utils import register_student_user, register_company_user, verify_password, users_collection, client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configure Upload Folder ---
app.config['UPLOAD_IMAGE_FOLDER'] = 'store/images'
# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_IMAGE_FOLDER'], exist_ok=True)

# Set a strong JWT secret key
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "your-jwt-secret-key")
if app.config["JWT_SECRET_KEY"] == "your-jwt-secret-key":
    logger.warning("Using default JWT secret key. This is insecure for production.")

jwt = JWTManager(app)

# --- Endpoints ---

@app.route('/register/student', methods=['POST']) # Route for student registration
def register_student():
    return register_student_user(app.config) # Pass app.config here

@app.route('/register/company', methods=['POST']) # Route for company registration
def register_company():
    return register_company_user(app.config) # Pass app.config here

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    if not data:
        return jsonify({"msg": "No data provided"}), 400

    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        logger.warning(f"Login failed: Missing email or password for email {email}")
        return jsonify({"msg": "Missing email or password"}), 400

    mongo_client = client # Use client from auth_utils
    try:
        # Check connection - client is already initialized in auth_utils
        client.admin.command('ping')

        user = users_collection.find_one({'email': email})

        if not user:
            logger.info(f"Login failed: User with email {email} not found")
            return jsonify({"msg": "Invalid email or password"}), 401

        if verify_password(password, user['password_hash']):
            access_token = create_access_token(identity=email, additional_claims={'role': user['role']})
            logger.info(f"User with email {email} logged in successfully")
            return jsonify(access_token=access_token), 200
        else:
            logger.info(f"Login failed: Incorrect password for email {email}")
            return jsonify({"msg": "Invalid email or password"}), 401

    except errors.PyMongoError as e:
        logger.error(f"MongoDB error during login: {e}")
        return jsonify({"msg": f"Login failed due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return jsonify({"msg": "Login failed due to a server error"}), 500
    # finally: # No need to close client here as it's initialized and intended to be reused in auth_utils
    #     if mongo_client:
    #         mongo_client.close() # Avoid closing the client that is intended to be reused


@app.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    current_user_email = get_jwt_identity()
    claims = get_jwt()
    user_role = claims.get('role')

    return jsonify(
        message=f"Hello, user with email {current_user_email}! You are a {user_role}.",
        user_identity=current_user_email,
        user_role=user_role
    ), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint to check if the application and database are healthy"""
    mongo_client = client # Use client from auth_utils
    try:
        # Check database connection - client is already initialized in auth_utils
        client.admin.command('ping')
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 500
    # finally: # No need to close client here as it's initialized and intended to be reused in auth_utils
    #     if mongo_client:
    #         mongo_client.close() # Avoid closing the client that is intended to be reused

@app.route('/store/images/<filename>') # Route to serve images
def serve_images(filename):
    return send_from_directory(app.config['UPLOAD_IMAGE_FOLDER'], filename)


if __name__ == '__main__':
    logger.info("Starting Flask application...")
    app.run(debug=True, host='0.0.0.0', port=5001)