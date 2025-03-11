# auth_utils.py (Updated for Shorter Unique Student Image Filenames - Copy and Paste this Entire File Content)
from flask import request, jsonify
from pymongo import MongoClient, errors
import bcrypt
import os
import datetime
import logging
import yaml
from werkzeug.utils import secure_filename
import time  # Import the time module for timestamp
import random # Import random module for random characters
import string # Import string module for character set

# Configure logging (No changes)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

with open('secrets.yaml') as f:
    secrets = yaml.load(f, Loader=yaml.FullLoader)

os.environ["MONGO_DB_URI"] = secrets['MONGO_DB_URI']

try:
    client = MongoClient(os.environ["MONGO_DB_URI"])
    db = client['Elearning']
    users_collection = db['users']
    students_collection = db['students']
    companies_collection = db['companies']
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

def register_student_user(app_config): # Accept app_config
    """Handles student user registration logic with image upload and shorter unique filename."""
    # --- Get form data ---
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

    image_filepath = None

    if image_file:
        try:
            upload_folder = app_config['UPLOAD_IMAGE_FOLDER'] # Use app_config
            file_extension = os.path.splitext(image_file.filename)[1] # Get file extension
            timestamp = str(int(time.time())) # Timestamp in seconds (shorter timestamp)
            random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4)) # 4 random chars (shorter random part)
            unique_filename = f"profile_image_{timestamp}_{random_chars}{file_extension}" # Shorter unique filename
            filename = secure_filename(unique_filename)
            image_path = os.path.join(upload_folder, filename)
            image_file.save(image_path)
            image_filepath = "/store/images/" + filename # Store the unique filename
            logger.info(f"Image saved to: {image_filepath} with shorter unique name for student {email}") # Updated log message
        except Exception as e:
            logger.error(f"Error saving image for student {email}: {e}")
            return jsonify({"msg": "Error saving profile picture"}), 500


    try:
        if users_collection.find_one({'email': email}): # No changes
            logger.info(f"Student registration failed: Email {email} already exists")
            return jsonify({"msg": "Email already exists"}), 400

        password_hash = hash_password(password) # No changes
        user_data = { # No changes
            "email": email,
            "password_hash": password_hash,
            "role": 'student',
            "created_at": datetime.datetime.utcnow()
        }
        user_result = users_collection.insert_one(user_data) # No changes
        user_id = user_result.inserted_id # No changes

        student_data = { # No changes except image_filepath
            "user_id": user_id,
            "firstname": firstname,
            "lastname": lastname,
            "email": email,
            "phone": phone,
            "dob": dob,
            "address": address,
            "image": image_filepath # Store unique image_filepath
        }
        student_result = students_collection.insert_one(student_data) # No changes

        if user_result.acknowledged and student_result.acknowledged: # No changes
            logger.info(f"Student with email {email} registered successfully")
            return jsonify({"msg": "Student registered successfully"}), 201
        else: # No changes
            logger.error(f"Student registration failed: Insert operation not fully acknowledged for email {email}")
            return jsonify({"msg": "Failed to register student"}), 500

    except errors.PyMongoError as e: # No changes
        logger.error(f"MongoDB error during student registration: {e}")
        return jsonify({"msg": f"Database error during student registration: {str(e)}"}), 500
    except Exception as e: # No changes
        logger.error(f"Unexpected error during student registration: {e}")
        return jsonify({"msg": "Student registration failed due to a server error"}), 500


def register_company_user(app_config): #  register_company_user remains UNCHANGED
    """Handles company user registration logic with image upload."""
    data = request.form
    if not data:
        logger.warning("Company registration failed: No form data provided")
        return jsonify({"msg": "No data provided"}), 400

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

    image_filepath = None

    if image_file:
        try:
            upload_folder = app_config['UPLOAD_IMAGE_FOLDER'] # Use app_config
            filename = secure_filename(image_file.filename)
            image_filepath = os.path.join(upload_folder, filename)
            image_file.save(image_filepath)
            image_filepath = "/store/images/" + filename
            logger.info(f"Image saved to: {image_filepath}")
        except Exception as e:
            logger.error(f"Error saving image for company {email}: {e}")
            return jsonify({"msg": "Error saving company profile picture"}), 500

    try:
        if users_collection.find_one({'email': email}): # No changes
            logger.info(f"Company registration failed: Email {email} already exists")
            return jsonify({"msg": "Email already exists"}), 400

        password_hash = hash_password(password) # No changes
        user_data = { # No changes
            "email": email,
            "password_hash": password_hash,
            "role": 'company',
            "created_at": datetime.datetime.utcnow()
        }
        user_result = users_collection.insert_one(user_data) # No changes
        user_id = user_result.inserted_id # No changes

        company_data = { # No changes except image_filepath
            "user_id": user_id,
            "company_name": company_name,
            "email": email,
            "phone": phone,
            "br_number": br_number,
            "image": image_filepath, # Store potentially overwriting image_filepath
            "about": about
        }
        company_result = companies_collection.insert_one(company_data) # No changes

        if user_result.acknowledged and company_result.acknowledged: # No changes
            logger.info(f"Company with email {email} registered successfully")
            return jsonify({"msg": "Company registered successfully"}), 201
        else: # No changes
            logger.error(f"Company registration failed: Insert operation not fully acknowledged for email {email}")
            return jsonify({"msg": "Failed to register company"}), 500

    except errors.PyMongoError as e: # No changes
        logger.error(f"MongoDB error during company registration: {e}")
        return jsonify({"msg": f"Database error during company registration: {str(e)}"}), 500
    except Exception as e: # No changes
        logger.error(f"Unexpected error during company registration: {e}")
        return jsonify({"msg": "Company registration failed due to a server error"}), 500


__all__ = [
    'register_student_user',
    'register_company_user',
    'verify_password',
    'users_collection',
    'client',
    'students_collection',
    'companies_collection',
]