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
import bson.errors # <<< --- ADD THIS IMPORT

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
    essay_question_collection,
    fluency_test_collection,
    essay_question_collection,
    marks_collection,
    jds_collection,
    jds_cv_collection,
    
)
from courses import create_course_logic, get_course_logic, update_course_logic, delete_course_logic, get_company_courses_logic, get_all_courses_logic
from course_content import create_content_logic, get_content_logic, update_content_logic, delete_content_logic, get_course_contents_logic
from mcq import create_mcq_logic, get_mcq_logic, update_mcq_logic, delete_mcq_logic, get_content_mcqs_logic, check_mcq_answer_logic
import enrollments  # Import the enrollments module
import fluency # Import fluency logic
import questions # Import questions logic
import marks
import jd 
import jd_cv 

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins="http://localhost:5173") # Your frontend origin

# --- Configure Upload Folders ---
app.config['UPLOAD_IMAGE_FOLDER'] = 'store/images'
app.config['UPLOAD_COURSE_IMAGE_FOLDER'] = r'C:\Users\moham\OneDrive\Desktop\SkillNet\AIGL\store\images\course' # Course image folder
app.config['UPLOAD_JD_FOLDER'] = r'C:\Users\moham\OneDrive\Desktop\SkillNet\AIGL\store\images\jd'#os.path.join(app.root_path, 'store', 'jd_pdfs') # Or your preferred path
os.makedirs(app.config['UPLOAD_IMAGE_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_COURSE_IMAGE_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_JD_FOLDER'], exist_ok=True)

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
        user = users_collection.find_one({'email': email})

        if not user:
            logger.info(f"Login failed: User with email {email} not found")
            return jsonify({"msg": "Invalid email or password"}), 401

        if verify_password(password, user['password_hash']):
            user_role = user['role']
            username_from_users_collection = user.get('username') # This is the generated username
            user_mongodb_id_str = str(user['_id']) # <<< --- GET THE MONGODB _id AS STRING

            profile_data = None
            # ... (your existing profile_data fetching logic) ...
            if user_role == 'student':
                student_profile = students_collection.find_one({'user_id': user['_id']})
                if student_profile:
                    profile_data = student_profile
                # ...
            elif user_role == 'company':
                company_profile = companies_collection.find_one({'user_id': user['_id']})
                if company_profile:
                    profile_data = company_profile
                # ...

            profile_image_url = profile_data.get('image') if profile_data else None

            access_token_claims = {
                'role': user_role,
                'profile_image_url': profile_image_url,
                'username_claim': username_from_users_collection, # Keep this if frontend uses it from token
                # It's often better to send user details in login response body than pack too much in JWT
            }
            if user_role == 'student' and profile_data:
                access_token_claims['firstname'] = profile_data.get('firstname')
                access_token_claims['lastname'] = profile_data.get('lastname')
            elif user_role == 'company' and profile_data:
                access_token_claims['company_name'] = profile_data.get('company_name')

            access_token = create_access_token(
                identity=email, # 'sub' claim will be the email
                additional_claims=access_token_claims
            )
            logger.info(f"User {email} logged in. Role: {user_role}. MongoDB ID: {user_mongodb_id_str}")

            # --- MODIFIED RESPONSE ---
            response_data = {
                "access_token": access_token,
                "userId": user_mongodb_id_str,      # <<< --- ADD THE MONGODB _id HERE
                "role": user_role,
                "email": email, # Already in token 'sub', but can be explicit
                "username": username_from_users_collection, # The generated username
                "profile_image_url": profile_image_url
            }
            if user_role == 'student' and profile_data:
                response_data['firstname'] = profile_data.get('firstname')
                response_data['lastname'] = profile_data.get('lastname')
            elif user_role == 'company' and profile_data:
                response_data['company_name'] = profile_data.get('company_name')
            # --- END MODIFIED RESPONSE ---

            return jsonify(response_data), 200
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


# --------------JD Routes---------------
@app.route('/jds', methods=['POST'])
@jwt_required()
def create_jd_route():
    """
    Endpoint to create a new Job Description by uploading a PDF.
    Requires JWT authentication. Company role is checked within the logic.
    Frontend should send 'jd_pdf' as a file in multipart/form-data.
    """
    return jd.create_jd_logic()

@app.route('/jds/<string:jd_id>', methods=['GET'])
def get_jd_route(jd_id):
    """
    Endpoint to retrieve a specific Job Description by its ID.
    This route is public by default.
    """
    return jd.get_jd_logic(jd_id)

@app.route('/jds/<string:jd_id>', methods=['PUT'])
@jwt_required()
def update_jd_route(jd_id):
    """
    Endpoint to update an existing Job Description.
    Allows replacing the PDF and/or updating its status.
    Requires JWT authentication. Company ownership is checked within the logic.
    Frontend should send 'jd_pdf' (optional file) and 'status' (optional form field)
    in multipart/form-data.
    """
    return jd.update_jd_logic(jd_id)

@app.route('/jds/<string:jd_id>', methods=['DELETE'])
@jwt_required()
def delete_jd_route(jd_id):
    """
    Endpoint to delete a specific Job Description by its ID.
    Requires JWT authentication. Company ownership is checked within the logic.
    Associated PDF file will also be deleted.
    """
    return jd.delete_jd_logic(jd_id)

@app.route('/jds/company/<string:company_identifier>', methods=['GET'])
def get_company_jds_route(company_identifier):
    """
    Endpoint to retrieve all Job Descriptions for a specific company.
    'company_identifier' can be the company's MongoDB _id (as a string) or email.
    Logic function (get_company_jds_logic) handles querying. Public by default.
    """
    return jd.get_company_jds_logic(company_identifier)

# Optional: Route for "my JDs" for the logged-in company
@app.route('/jds/my', methods=['GET'])
@jwt_required()
def get_my_company_jds_route():
    """
    Endpoint for a logged-in company to retrieve its own Job Descriptions.
    Uses the JWT identity (company_email) to fetch the JDs.
    """
    current_user_email = get_jwt_identity()
    return jd.get_company_jds_logic(current_user_email) # Assumes get_company_jds_logic can take email


@app.route('/jds', methods=['GET'])
def get_all_jds_route():
    """
    Endpoint to retrieve all Job Descriptions.
    Can be filtered by query parameters like ?status=active.
    This route is public by default.
    Note: This route has the same path as POST /jds. Flask handles this correctly
    based on the HTTP method.
    """
    return jd.get_all_jds_logic()



# --- CVs with Matched JDs Routes ---
@app.route('/cvs/matched', methods=['POST']) # New POST route
@jwt_required()
def add_cv_jd_match_route():
    """
    Endpoint for a logged-in company (or authorized service) to add
    a new CV-JD match record.
    Expects a JSON body with 'cv_path' and 'matched_jd_paths'.
    """
    return jd_cv.create_cv_jd_match_logic()

@app.route('/cvs', methods=['GET'])
@jwt_required()  # Ensures only authenticated users can access
def get_company_matched_cvs_route():
    """
    Endpoint for a logged-in company to retrieve its CVs 
    along with their matched Job Descriptions.
    The logic function handles identifying CV-JD match documents
    associated with the current company.
    """
    return jd_cv.get_company_cv_jd_matches_logic()

@app.route('/cvs/matched/<string:cv_match_id>', methods=['DELETE'])
@jwt_required()  # Ensures only authenticated users can access
def delete_company_matched_cv_route(cv_match_id):
    """
    Endpoint for a logged-in company to delete a specific CV-JD match record
    by its MongoDB _id.
    The logic function also handles deleting the associated CV PDF file.
    """
    return jd_cv.delete_company_cv_jd_match_logic(cv_match_id)



@app.route('/marks/user/<user_id_str>/course/<course_id_str>', methods=['POST'])
@jwt_required()
def save_user_course_marks(user_id_str, course_id_str):
    claims = get_jwt()
    requesting_user_email = get_jwt_identity()
    requesting_user_role = claims.get('role')
    
    # <<< --- EXTRACT FIRSTNAME AND LASTNAME FROM JWT CLAIMS --- >>>
    user_firstname_from_jwt = claims.get('firstname')
    user_lastname_from_jwt = claims.get('lastname')

    try:
        actor_user_doc = users_collection.find_one({"email": requesting_user_email})
        if not actor_user_doc:
            logger.warning(f"Marks save attempt by non-existent user (email from token): {requesting_user_email}")
            return jsonify({"msg": "Authenticated user not found"}), 403

        actor_user_id_str = str(actor_user_doc['_id'])

        if requesting_user_role == 'student':
            if actor_user_id_str != user_id_str:
                logger.warning(f"Auth fail: Student {requesting_user_email} (ID: {actor_user_id_str}) tried to save marks for different user {user_id_str}")
                return jsonify({"msg": "Unauthorized: You can only save your own marks."}), 403
        elif requesting_user_role != 'admin':
            logger.warning(f"Auth fail: Role {requesting_user_role} ({requesting_user_email}) tried to save marks.")
            return jsonify({"msg": "Unauthorized role for this action."}), 403
        
        logger.info(f"Marks save authorized for user {user_id_str}, course {course_id_str} by {requesting_user_email} ({requesting_user_role}).")
        
        # <<< --- PASS FIRSTNAME AND LASTNAME TO THE LOGIC FUNCTION --- >>>
        result_data, status_code = marks.save_specific_user_marks_logic(
            user_id_str, 
            course_id_str,
            user_firstname_from_jwt, # New argument
            user_lastname_from_jwt   # New argument
        )
        
        if isinstance(result_data, dict) and "error" in result_data:
            return jsonify(result_data), status_code 
            
        return jsonify(result_data), status_code

    except bson.errors.InvalidId: 
        logger.error(f"Invalid ID format for user_id '{user_id_str}' or course_id '{course_id_str}' during marks save route processing.")
        return jsonify({"msg": "Invalid user or course ID format provided."}), 400
    except Exception as e:
        logger.error(f"Unexpected error in save_user_course_marks route for user {user_id_str}: {e}", exc_info=True)
        return jsonify({"msg": "Server error during marks processing"}), 500
    
@app.route('/marks/user/<user_id_str>', methods=['GET'])
@jwt_required()
def get_marks_for_specific_user(user_id_str):
    # ... (claims, requesting_user_email, requesting_user_role, actor_user_doc, actor_user_id_str, authorization checks) ...
    try:
        logger.info(f"Marks retrieval authorized for user {user_id_str} by {requesting_user_email} ({requesting_user_role}).")
        # The ObjectId conversion happens inside marks.get_specific_user_marks_logic
        return marks.get_specific_user_marks_logic(user_id_str)

    except bson.errors.InvalidId: # <<< --- CORRECTED EXCEPTION
        logger.error(f"Invalid user ID format '{user_id_str}' for getting marks.")
        return jsonify({"msg": "Invalid user ID format in URL"}), 400
    except Exception as e:
        logger.error(f"Unexpected error during authorization or getting user marks for {user_id_str}: {e}", exc_info=True)
        return jsonify({"msg": "Server error during authorization or marks retrieval"}), 500


@app.route('/marks/all', methods=['GET']) # Changed route for clarity
@jwt_required()
def get_marks_for_all_students():
    """
    Endpoint to get all marks records for all students.
    Primarily for admin use.
    """
    claims = get_jwt()
    requesting_user_role = claims.get('role')

    if requesting_user_role not in ['admin']: # Strict check for admin role
        logger.warning(f"Auth fail: Role {requesting_user_role} tried to access all student marks.")
        return jsonify({"msg": "Unauthorized: This action requires admin privileges."}), 403
    
    logger.info(f"All marks retrieval authorized for admin user.")
    return marks.get_all_students_marks_logic()

if __name__ == '__main__':
    logger.info("Starting Flask application...")
    # Consider adding host='0.0.0.0' if running in Docker or want to access from other devices on network
    app.run(debug=True, port=5001)


