# auth_utils.py
from flask import request, jsonify
from pymongo import MongoClient, errors
import bcrypt
import os
import datetime # Import the module
import logging
import yaml
from werkzeug.utils import secure_filename
import time
import random
import string

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

with open('secrets.yaml') as f:
    secrets = yaml.load(f, Loader=yaml.FullLoader)

os.environ["MONGO_DB_URI"] = secrets['MONGO_DB_URI']

client = None
db = None
users_collection = None
students_collection = None
companies_collection = None
courses_collection = None
contents_collection = None
mcqs_collection = None
enrollments_collection = None
fluency_test_collection = None
essay_question_collection = None
marks_collection = None


try:
    client = MongoClient(os.environ["MONGO_DB_URI"])
    db = client['Elearning']
    users_collection = db['users']
    students_collection = db['students']
    companies_collection = db['companies']
    courses_collection = db['courses']
    contents_collection = db['contents']
    mcqs_collection = db['mcqs']
    enrollments_collection = db['enrollments']
    fluency_test_collection = db['fluency_test']
    essay_question_collection = db['essay_question']
    marks_collection = db['marks']
    flow_collection = db['flow']
    qna_collection = db['qna']
    logger.info("Connected to MongoDB and collections initialized in auth_utils.py")
except Exception as e:
    logger.error(f"Error connecting to MongoDB or initializing collections in auth_utils.py: {e}")
    print(e)

def hash_password(password):
    """Hashes a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def verify_password(password, password_hash):
    """Verifies a password against its hash."""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def register_student_user(app_config):
    """Handles student user registration logic with image upload and username in users collection."""
    email = request.form.get('email')
    password = request.form.get('password')
    firstname = request.form.get('firstname')
    lastname = request.form.get('lastname')
    phone = request.form.get('phone')
    dob = request.form.get('dob')
    address = request.form.get('address')
    image_file = request.files.get('image')

    if not all([email, password, firstname, lastname]):
        logger.warning(f"Student registration failed: Missing required data for email {email}")
        return jsonify({"msg": "Missing required registration data"}), 400

    student_username = f"{firstname}{lastname}".lower().replace(" ", "")

    image_filepath_for_db = None
    actual_image_save_path = None

    if image_file:
        try:
            upload_folder = app_config['UPLOAD_IMAGE_FOLDER']
            file_extension = os.path.splitext(image_file.filename)[1]
            timestamp = str(int(time.time()))
            random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            unique_filename = f"profile_{student_username}_{timestamp}_{random_chars}{file_extension}"
            filename = secure_filename(unique_filename)
            actual_image_save_path = os.path.join(upload_folder, filename)
            image_file.save(actual_image_save_path)
            image_filepath_for_db = "/store/images/" + filename
            logger.info(f"Image saved to: {actual_image_save_path} (served as: {image_filepath_for_db}) for student {email}")
        except Exception as e:
            logger.error(f"Error saving image for student {email}: {e}")
            return jsonify({"msg": "Error saving profile picture"}), 500

    try:
        if users_collection.find_one({'email': email}):
            logger.info(f"Student registration failed: Email {email} already exists")
            return jsonify({"msg": "Email already exists"}), 400

        password_hash = hash_password(password)
        user_data = {
            "username": student_username,
            "email": email,
            "password_hash": password_hash,
            "role": 'student',
            "created_at": datetime.datetime.utcnow() # CORRECTED
        }
        user_result = users_collection.insert_one(user_data)
        user_id_obj = user_result.inserted_id

        student_data = {
            "user_id": user_id_obj,
            "firstname": firstname,
            "lastname": lastname,
            "email": email,
            "phone": phone,
            "dob": dob,
            "address": address,
            "image": image_filepath_for_db
        }
        student_result = students_collection.insert_one(student_data)

        if user_result.acknowledged and student_result.acknowledged:
            logger.info(f"Student '{student_username}' with email {email} registered successfully. User ID: {user_id_obj}")
            return jsonify({"msg": "Student registered successfully"}), 201
        else:
            logger.error(f"Student registration failed: Insert operation not fully acknowledged for email {email}")
            if user_result.acknowledged and not student_result.acknowledged and user_id_obj:
                users_collection.delete_one({'_id': user_id_obj})
                logger.info(f"Cleaned up user record for email {email} due to failed student profile creation.")
            return jsonify({"msg": "Failed to register student"}), 500

    except errors.PyMongoError as e:
        logger.error(f"MongoDB error during student registration for email {email}: {e}")
        return jsonify({"msg": f"Database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error during student registration for email {email}: {e}", exc_info=True)
        return jsonify({"msg": "Student registration failed due to a server error"}), 500


def register_company_user(app_config):
    """Handles company user registration logic with image upload and username in users collection."""
    email = request.form.get('email')
    password = request.form.get('password')
    company_name = request.form.get('company_name')
    phone = request.form.get('phone')
    br_number = request.form.get('br_number')
    about = request.form.get('about')
    image_file = request.files.get('image')

    if not all([email, password, company_name]):
        logger.warning(f"Company registration failed: Missing required data for email {email}")
        return jsonify({"msg": "Missing required registration data"}), 400

    company_username = company_name.lower().replace(" ", "_")

    image_filepath_for_db = None
    actual_image_save_path = None

    if image_file:
        try:
            upload_folder = app_config['UPLOAD_IMAGE_FOLDER']
            file_extension = os.path.splitext(image_file.filename)[1]
            timestamp = str(int(time.time()))
            random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            unique_filename = f"company_{company_username}_{timestamp}_{random_chars}{file_extension}"
            filename = secure_filename(unique_filename)
            actual_image_save_path = os.path.join(upload_folder, filename)
            image_file.save(actual_image_save_path)
            image_filepath_for_db = "/store/images/" + filename
            logger.info(f"Image saved to: {actual_image_save_path} (served as: {image_filepath_for_db}) for company {email}")
        except Exception as e:
            logger.error(f"Error saving image for company {email}: {e}")
            return jsonify({"msg": "Error saving company profile picture"}), 500

    try:
        if users_collection.find_one({'email': email}):
            logger.info(f"Company registration failed: Email {email} already exists")
            return jsonify({"msg": "Email already exists"}), 400

        password_hash = hash_password(password)
        user_data = {
            "username": company_username,
            "email": email,
            "password_hash": password_hash,
            "role": 'company',
            "created_at": datetime.datetime.utcnow() # CORRECTED
        }
        user_result = users_collection.insert_one(user_data)
        user_id_obj = user_result.inserted_id

        company_data = {
            "user_id": user_id_obj,
            "company_name": company_name,
            "email": email,
            "phone": phone,
            "br_number": br_number,
            "image": image_filepath_for_db,
            "about": about
        }
        company_result = companies_collection.insert_one(company_data)

        if user_result.acknowledged and company_result.acknowledged:
            logger.info(f"Company '{company_name}' (username: {company_username}) with email {email} registered successfully. User ID: {user_id_obj}")
            return jsonify({"msg": "Company registered successfully"}), 201
        else:
            logger.error(f"Company registration failed: Insert operation not fully acknowledged for email {email}")
            if user_result.acknowledged and not company_result.acknowledged and user_id_obj:
                users_collection.delete_one({'_id': user_id_obj})
                logger.info(f"Cleaned up user record for email {email} due to failed company profile creation.")
            return jsonify({"msg": "Failed to register company"}), 500

    except errors.PyMongoError as e:
        logger.error(f"MongoDB error during company registration for {email}: {e}")
        return jsonify({"msg": f"Database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error during company registration for {email}: {e}", exc_info=True)
        return jsonify({"msg": "Company registration failed due to a server error"}), 500


__all__ = [
    'register_student_user',
    'register_company_user',
    'verify_password',
    'users_collection',
    'client',
    'students_collection',
    'companies_collection',
    'courses_collection',
    'contents_collection',
    'mcqs_collection',
    'enrollments_collection',
    'fluency_test_collection',
    'essay_question_collection',
    'marks_collection'
]