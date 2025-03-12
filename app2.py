from flask import Flask, request, jsonify, send_from_directory
from flask_jwt_extended import create_access_token, jwt_required, JWTManager, get_jwt_identity, get_jwt
from pymongo import errors
import os
import logging
import yaml
from werkzeug.utils import secure_filename
from flask_cors import CORS
from bson.objectid import ObjectId
from datetime import datetime

# Import our updated auth_utils module
from auth_utils import register_student_user, register_company_user, verify_password, users_collection, client, students_collection, companies_collection

# Import course logic functions from courses.py
from courses import create_course_logic, get_course_logic, update_course_logic, delete_course_logic, get_company_courses_logic, get_all_courses_logic


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins="http://localhost:5173")

# --- Configure Upload Folders ---
app.config['UPLOAD_IMAGE_FOLDER'] = 'store/images' # Existing profile image folder
app.config['UPLOAD_COURSE_IMAGE_FOLDER'] = r'C:\Users\moham\OneDrive\Desktop\SkillNet\AIGL\store\images\course' # Course image folder
os.makedirs(app.config['UPLOAD_IMAGE_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_COURSE_IMAGE_FOLDER'], exist_ok=True) # Create course image folder if not exists

# Set a strong JWT secret key
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "your-jwt-secret-key")
if app.config["JWT_SECRET_KEY"] == "your-jwt-secret-key":
    logger.warning("Using default JWT secret key. This is insecure for production.")

jwt = JWTManager(app)


# --- Endpoints ---

@app.route('/register/student', methods=['POST'])
def register_student():
    return register_student_user(app.config)

@app.route('/register/company', methods=['POST'])
def register_company():
    return register_company_user(app.config)


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

    mongo_client = client
    try:
        client.admin.command('ping')

        user = users_collection.find_one({'email': email})

        if not user:
            logger.info(f"Login failed: User with email {email} not found")
            return jsonify({"msg": "Invalid email or password"}), 401

        if verify_password(password, user['password_hash']):
            user_role = user['role']

            profile_data = None

            if user_role == 'student':
                student_profile = students_collection.find_one({'email': email})
                if student_profile:
                    profile_data = student_profile
            elif user_role == 'company':
                company_profile = companies_collection.find_one({'email': email})
                if company_profile:
                    profile_data = company_profile

            profile_image_url = profile_data.get('image') if profile_data else None

            access_token = create_access_token(
                identity=email,
                additional_claims={
                    'role': user_role,
                    'profile_image_url': profile_image_url
                }
            )
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
    mongo_client = client
    try:
        client.admin.command('ping')
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 500


@app.route('/store/images/<filename>')
def serve_images(filename):
    return send_from_directory(app.config['UPLOAD_IMAGE_FOLDER'], filename)

@app.route('/store/course_images/<filename>')
def serve_course_images(filename):
    return send_from_directory(app.config['UPLOAD_COURSE_IMAGE_FOLDER'], filename) # Serve course images


# --- Course Routes (Calling logic from courses.py) ---

@app.route('/courses', methods=['POST'])
@jwt_required()
def create_course():
    return create_course_logic() # Call logic function from courses.py

@app.route('/courses/<course_id>', methods=['GET'])
def get_course(course_id):
    return get_course_logic(course_id) # Call logic function from courses.py

@app.route('/courses/<course_id>', methods=['PUT'])
@jwt_required()
def update_course(course_id):
    return update_course_logic(course_id) # Call logic function from courses.py

@app.route('/courses/<course_id>', methods=['DELETE'])
@jwt_required()
def delete_course(course_id):
    return delete_course_logic(course_id) # Call logic function from courses.py

@app.route('/companies/<company_name>/courses', methods=['GET'])
def get_company_courses(company_name):
    return get_company_courses_logic(company_name) # Call logic function from courses.py

@app.route('/courses', methods=['GET']) # Get all courses
def get_all_courses():
    return get_all_courses_logic() # Call logic function from courses.py


if __name__ == '__main__':
    logger.info("Starting Flask application...")
    app.run(debug=True, host='0.0.0.0', port=5001)