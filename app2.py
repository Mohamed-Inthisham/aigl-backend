# app2.py
from flask import Flask, request, jsonify, send_from_directory
from flask_jwt_extended import create_access_token, jwt_required, JWTManager, get_jwt_identity, get_jwt
from pymongo import errors, MongoClient # Added MongoClient for completeness if not already there
from bson.objectid import ObjectId
from datetime import datetime
import os
import logging
import yaml
from werkzeug.utils import secure_filename
from flask_cors import CORS

# Import auth_utils, course logic, content logic, mcq logic, etc.
# Ensure all necessary collections are exported from auth_utils
from auth_utils import (
    register_student_user,
    register_company_user,
    verify_password,
    users_collection,
    client, # Assuming client is your MongoClient instance from auth_utils
    students_collection, # CRITICAL: Ensure this is available
    companies_collection,
    courses_collection,
    contents_collection,
    mcqs_collection,
    enrollments_collection, # Make sure this is available
    fluency_test_collection,
    essay_question_collection
)
from courses import create_course_logic, get_course_logic, update_course_logic, delete_course_logic, get_company_courses_logic, get_all_courses_logic
from course_content import create_content_logic, get_content_logic, update_content_logic, delete_content_logic, get_course_contents_logic
from mcq import create_mcq_logic, get_mcq_logic, update_mcq_logic, delete_mcq_logic, get_content_mcqs_logic, check_mcq_answer_logic
import enrollments  # Import the enrollments module
import fluency # Import fluency logic
import questions # Import questions logic

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins="http://localhost:5173") # Your frontend origin

# --- Configure Upload Folders ---
app.config['UPLOAD_IMAGE_FOLDER'] = 'store/images'
app.config['UPLOAD_COURSE_IMAGE_FOLDER'] = r'C:\Users\moham\OneDrive\Desktop\SkillNet\AIGL\store\images\course' # Course image folder
os.makedirs(app.config['UPLOAD_IMAGE_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_COURSE_IMAGE_FOLDER'], exist_ok=True)

# Set a strong JWT secret key
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "your-jwt-secret-key-change-me-in-production") # IMPORTANT: Change this for production
if app.config["JWT_SECRET_KEY"] == "your-jwt-secret-key-change-me-in-production":
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

    try:
        # Ping the database to ensure connection (optional, client init in auth_utils should handle this)
        # client.admin.command('ping') 

        user = users_collection.find_one({'email': email}) # Fetches the user document which now includes 'username'

        if not user:
            logger.info(f"Login failed: User with email {email} not found")
            return jsonify({"msg": "Invalid email or password"}), 401

        if verify_password(password, user['password_hash']):
            user_role = user['role']
            # Get the username directly from the user document
            username_from_users_collection = user.get('username') # <--- GET USERNAME HERE

            profile_data = None
            company_name_claim = None

            if user_role == 'student':
                student_profile = students_collection.find_one({'user_id': user['_id']})
                if student_profile:
                    profile_data = student_profile
                else:
                    logger.warning(f"Student profile not found for user_id: {user['_id']} with email: {email}")
            elif user_role == 'company':
                company_profile = companies_collection.find_one({'user_id': user['_id']})
                if company_profile:
                    profile_data = company_profile
                else:
                    logger.warning(f"Company profile not found for user_id: {user['_id']} with email: {email}")

            profile_image_url = profile_data.get('image') if profile_data else None

            # --- CONSTRUCT ADDITIONAL CLAIMS ---
            access_token_claims = {
                'role': user_role,
                'profile_image_url': profile_image_url,
                'username': username_from_users_collection # <--- ADDING THE USERNAME FROM USERS COLLECTION
            }

            # Add role-specific claims (firstname/lastname for student, company_name for company)
            if user_role == 'student' and profile_data:
                access_token_claims['firstname'] = profile_data.get('firstname')
                access_token_claims['lastname'] = profile_data.get('lastname')
                logger.info(f"Student specific claims: firstname={profile_data.get('firstname')}, lastname={profile_data.get('lastname')}")
            elif user_role == 'company' and profile_data:
                access_token_claims['company_name'] = profile_data.get('company_name')
                logger.info(f"Company specific claim: company_name={profile_data.get('company_name')}")
            # --- END OF CONSTRUCTING ADDITIONAL CLAIMS ---

            access_token = create_access_token(
                identity=email,
                additional_claims=access_token_claims
            )
            logger.info(f"User with email {email} logged in successfully. JWT Claims being sent: {access_token_claims}")
            return jsonify(access_token=access_token), 200
        else:
            logger.info(f"Login failed: Incorrect password for email {email}")
            return jsonify({"msg": "Invalid email or password"}), 401

    except errors.PyMongoError as e:
        logger.error(f"MongoDB error during login: {e}")
        return jsonify({"msg": f"Login failed due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error during login: {e}", exc_info=True)
        return jsonify({"msg": "Login failed due to a server error"}), 500

@app.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    current_user_email = get_jwt_identity()
    claims = get_jwt()
    user_role = claims.get('role')
    company_name = claims.get('company_name') # Example of getting company_name

    return jsonify(
        message=f"Hello, user with email {current_user_email}! You are a {user_role}.",
        user_identity=current_user_email,
        user_role=user_role,
        company_name=company_name
    ), 200

@app.route('/health', methods=['GET'])
def health_check():
    # mongo_client = client
    try:
        client.admin.command('ping') # Use the client imported from auth_utils
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 500


@app.route('/store/images/<filename>')
def serve_images(filename):
    return send_from_directory(app.config['UPLOAD_IMAGE_FOLDER'], filename)

@app.route('/store/course_images/<filename>') # Corrected path
def serve_course_images(filename):
    return send_from_directory(app.config['UPLOAD_COURSE_IMAGE_FOLDER'], filename)


# --- Course Routes ---
@app.route('/courses', methods=['POST'])
@jwt_required()
def create_course():
    return create_course_logic()

@app.route('/courses/<course_id>', methods=['GET'])
def get_course(course_id):
    return get_course_logic(course_id)

@app.route('/courses/<course_id>', methods=['PUT'])
@jwt_required()
def update_course(course_id):
    return update_course_logic(course_id)

@app.route('/courses/<course_id>', methods=['DELETE'])
@jwt_required()
def delete_course(course_id):
    return delete_course_logic(course_id)

@app.route('/companies/<company_name>/courses', methods=['GET'])
def get_company_courses(company_name):
    return get_company_courses_logic(company_name)

@app.route('/courses', methods=['GET'])
def get_all_courses():
    return get_all_courses_logic()


# --- Course Content Routes ---
@app.route('/courses/<course_id>/contents', methods=['POST'])
@jwt_required()
def create_content(course_id):
    return create_content_logic(course_id)

@app.route('/contents/<content_id>', methods=['GET'])
def get_content(content_id):
    return get_content_logic(content_id)

@app.route('/contents/<content_id>', methods=['PUT'])
@jwt_required()
def update_content(content_id):
    return update_content_logic(content_id)

@app.route('/contents/<content_id>', methods=['DELETE'])
@jwt_required()
def delete_content(content_id):
    return delete_content_logic(content_id)

@app.route('/courses/<course_id>/contents', methods=['GET'])
def get_course_contents(course_id):
    return get_course_contents_logic(course_id)


# --- MCQ Routes ---
@app.route('/contents/<content_id>/mcqs', methods=['POST'])
@jwt_required()
def create_mcq(content_id):
    return create_mcq_logic(content_id)

@app.route('/mcqs/<mcq_id>', methods=['GET'])
def get_mcq(mcq_id):
    return get_mcq_logic(mcq_id)

@app.route('/mcqs/<mcq_id>', methods=['PUT'])
@jwt_required()
def update_mcq(mcq_id):
    return update_mcq_logic(mcq_id)

@app.route('/mcqs/<mcq_id>', methods=['DELETE'])
@jwt_required()
def delete_mcq(mcq_id):
    return delete_mcq_logic(mcq_id)

@app.route('/contents/<content_id>/mcqs', methods=['GET'])
def get_content_mcqs(content_id):
    return get_content_mcqs_logic(content_id)

@app.route('/mcqs/<mcq_id>/checkAnswer', methods=['POST'])
def check_answer(mcq_id):
    return check_mcq_answer_logic(mcq_id)


# --- Enrollment Routes ---
@app.route('/courses/<course_id>/enroll', methods=['POST'])
@jwt_required()
def enroll_in_course(course_id):
    return enrollments.enroll_in_course_logic(course_id)

@app.route('/me/enrolled-courses', methods=['GET'])
@jwt_required()
def get_student_enrolled_courses():
    return enrollments.get_student_enrolled_courses_logic()

# --- NEW ENDPOINT: Get Enrolled Students for a Company ---
@app.route('/companies/<company_name_param>/enrolled-students', methods=['GET'])
@jwt_required()
def get_company_enrolled_students(company_name_param):
    claims = get_jwt()
    requesting_user_role = claims.get('role')
    requesting_company_name_from_token = claims.get('company_name')

    # Security check: Only allow the company itself or an admin (if you implement admin role)
    if requesting_user_role == 'company':
        if requesting_company_name_from_token != company_name_param:
            logger.warning(f"Unauthorized access attempt by company '{requesting_company_name_from_token}' for company '{company_name_param}' enrollments.")
            return jsonify({"msg": "Unauthorized to view enrollments for this company"}), 403
    elif requesting_user_role != 'admin': # Example: if you had an 'admin' role
        logger.warning(f"Unauthorized access attempt by role '{requesting_user_role}' for company enrollments.")
        return jsonify({"msg": "Unauthorized"}), 403
    # If role is admin, it would proceed. If not company and not admin, it's unauthorized.

    try:
        # Step 1: Find all courses for the given company_name_param
        company_courses = list(courses_collection.find({"company_name": company_name_param}, {"_id": 1, "course_name": 1}))
        
        if not company_courses:
            logger.info(f"No courses found for company '{company_name_param}', so no enrollments to display.")
            return jsonify([]), 200 

        company_course_ids = [course["_id"] for course in company_courses]
        # Create a map of course_id to course_name for easy lookup later
        course_id_to_name_map = {course["_id"]: course["course_name"] for course in company_courses}

        # Step 2: Find all enrollments for these course_ids using MongoDB aggregation
        pipeline = [
            {
                "$match": {"course_id": {"$in": company_course_ids}} 
            },
            {
                "$lookup": {
                    "from": "students", # The name of your students collection in MongoDB
                    "localField": "student_email",
                    "foreignField": "email",
                    "as": "studentDetails"
                }
            },
            {
                "$unwind": {
                    "path": "$studentDetails",
                    "preserveNullAndEmptyArrays": True # Keep enrollment even if student somehow not found
                }
            },
            {
                "$project": {
                    "_id": 0, 
                    "student_name": { 
                        "$concat": [
                            { "$ifNull": ["$studentDetails.firstname", ""] }, 
                            " ", 
                            { "$ifNull": ["$studentDetails.lastname", ""] }
                        ]
                    },
                    "student_email": "$student_email",
                    "course_id": "$course_id", 
                    "enrollment_date": "$enrollment_date" # Keep original enrollment_date
                }
            }
        ]
        
        enrolled_students_aggregated = list(enrollments_collection.aggregate(pipeline))
        
        # Format data for the frontend
        results = []
        for record in enrolled_students_aggregated:
            course_name = course_id_to_name_map.get(record.get("course_id"), "Unknown Course")
            enrolled_date_str = "N/A"
            if record.get("enrollment_date") and isinstance(record["enrollment_date"], datetime):
                enrolled_date_str = record["enrollment_date"].strftime("%b %d, %Y") # Format date
            
            results.append({
                "student_name": record.get("student_name", "").strip(), # Ensure name is a string and trim
                "student_email": record.get("student_email"),
                "course_name": course_name,
                "enrolled_date": enrolled_date_str
            })
            
        logger.info(f"Successfully fetched {len(results)} enrollments for company '{company_name_param}'.")
        return jsonify(results), 200

    except errors.PyMongoError as e:
        logger.error(f"Database error fetching enrolled students for '{company_name_param}': {e}")
        return jsonify({"msg": f"Database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error fetching enrolled students for '{company_name_param}': {e}")
        return jsonify({"msg": "An unexpected error occurred"}), 500


# --- Fluency Test Routes ---
@app.route('/courses/<course_id>/fluency_tests', methods=['POST'])
@jwt_required()
def create_fluency_test(course_id):
    return fluency.create_fluency_test_logic(course_id)

@app.route('/fluency_tests/<fluency_test_id>', methods=['GET'])
def get_fluency_test(fluency_test_id):
    return fluency.get_fluency_test_logic(fluency_test_id)

@app.route('/fluency_tests/<fluency_test_id>', methods=['PUT'])
@jwt_required()
def update_fluency_test(fluency_test_id):
    return fluency.update_fluency_test_logic(fluency_test_id)

@app.route('/fluency_tests/<fluency_test_id>', methods=['DELETE'])
@jwt_required()
def delete_fluency_test(fluency_test_id):
    return fluency.delete_fluency_test_logic(fluency_test_id)

@app.route('/courses/<course_id>/fluency_tests', methods=['GET'])
def get_course_fluency_tests(course_id):
    return fluency.get_course_fluency_tests_logic(course_id)

@app.route('/courses/<course_id>/fluency_test', methods=['GET'])
def get_course_fluency_test(course_id):
    return fluency.get_fluency_test_by_course_id_logic(course_id)


# --- Essay Question Routes ---
@app.route('/courses/<course_id>/essay_questions', methods=['POST'])
@jwt_required()
def create_essay_question(course_id):
    return questions.create_essay_question_logic(course_id)

@app.route('/essay_questions/<essay_question_id>', methods=['GET'])
def get_essay_question(essay_question_id):
    return questions.get_essay_question_logic(essay_question_id)

@app.route('/essay_questions/<essay_question_id>', methods=['PUT'])
@jwt_required()
def update_essay_question(essay_question_id):
    return questions.update_essay_question_logic(essay_question_id)

@app.route('/essay_questions/<essay_question_id>', methods=['DELETE'])
@jwt_required()
def delete_essay_question(essay_question_id):
    return questions.delete_essay_question_logic(essay_question_id)

@app.route('/courses/<course_id>/essay_questions', methods=['GET'])
def get_course_essay_questions(course_id):
    return questions.get_course_essay_questions_logic(course_id)

@app.route('/courses/<course_id>/essay_question', methods=['GET'])
def get_course_essay_question(course_id):
    return questions.get_course_essay_question_by_course_id_logic(course_id)


if __name__ == '__main__':
    logger.info("Starting Flask application...")
    # Consider adding host='0.0.0.0' if running in Docker or want to access from other devices on network
    app.run(debug=True, port=5001)