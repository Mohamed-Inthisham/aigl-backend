from flask import request, jsonify
from pymongo import MongoClient, errors
import bcrypt
import os
import datetime
import logging
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

with open('secrets.yaml') as f:
    secrets = yaml.load(f, Loader=yaml.FullLoader)

os.environ["MONGO_DB_URI"] = secrets['MONGO_DB_URI']

try:
    client = MongoClient(os.environ["MONGO_DB_URI"])
    db = client['Elearning']
    users_collection = db['users']
    print("Connected to MongoDB")
except Exception as e:
    print(e)

def hash_password(password):
    """Hashes a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def verify_password(password, password_hash):
    """Verifies a password against its hash."""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def register_user():
    """Handles user registration logic, establishing DB connection within function."""
    data = request.get_json()

    if not data:
        logger.warning("Registration failed: No JSON data provided")
        return jsonify({"msg": "No data provided"}), 400

    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    role = data.get('role')

    # --- Input Validation ---
    if not username or not password or not role or role not in ['student', 'company'] or not email:
        logger.warning(f"Registration failed: Missing or invalid data for user {username}")
        return jsonify({"msg": "Missing or invalid registration data"}), 400

    mongo_client = client # Use the client connected outside
    try:
        # Check for existing users
        if users_collection.find_one({'username': username}):
            logger.info(f"Registration failed: Username {username} already exists")
            return jsonify({"msg": "Username already exists"}), 400
        if users_collection.find_one({'email': email}):
            logger.info(f"Registration failed: Email {email} already exists")
            return jsonify({"msg": "Email already exists"}), 400

        # --- Hash the password ---
        password_hash = hash_password(password)

        # --- Store user in MongoDB ---
        user_data = {
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "role": role,
            "created_at": datetime.datetime.utcnow()
        }

        result = users_collection.insert_one(user_data)

        if result.acknowledged:
            logger.info(f"User {username} registered successfully with ID: {result.inserted_id}")
            return jsonify({"msg": "User registered successfully", "user_id": str(result.inserted_id)}), 201
        else:
            logger.error(f"Registration failed: Insert operation not acknowledged for user {username}")
            return jsonify({"msg": "Failed to register user - database did not acknowledge operation"}), 500


    except errors.PyMongoError as e:
        logger.error(f"MongoDB error during user registration: {e}")
        return jsonify({"msg": f"Database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error during user registration: {e}")
        return jsonify({"msg": "An unexpected error occurred"}), 500
    # finally: # No need to close client here as it's connected outside and intended to be reused.
    #     if mongo_client:
    #         mongo_client.close() # Avoid closing the client that is intended to be reused