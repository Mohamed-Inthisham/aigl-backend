# courses.py
from flask import jsonify, request, current_app
from flask_jwt_extended import get_jwt_identity, get_jwt
from pymongo import errors
from bson.objectid import ObjectId
from datetime import datetime
import logging
import os
from werkzeug.utils import secure_filename

# Import database collections and client from auth_utils.py
from auth_utils import courses_collection, companies_collection, contents_collection  # Import contents_collection

# Configure logging
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def allowed_file(filename, allowed_extensions={'png', 'jpg', 'jpeg', 'gif'}):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def create_course_logic():
    claims = get_jwt()
    user_role = claims.get_role()
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can create courses"}), 403

    data = request.form  # Use request.form for file uploads
    if not data:
        return jsonify({"msg": "No data provided"}), 400

    required_fields = ['course_name', 'introduction', 'level']
    if not all(field in data for field in required_fields):
        return jsonify({"msg": "Missing required fields"}), 400

    course_name = data.get('course_name')
    introduction = data.get('introduction')
    level = data.get('level')
    course_image_file = request.files.get('course_image')  # Get uploaded file

    company_data = companies_collection.find_one({'email': current_user_email})
    if not company_data:
        return jsonify({"msg": "Company profile not found"}), 404

    company_name = company_data.get('company_name')
    company_image = company_data.get('image')  # Get company image path from DB

    course_image_filepath = None

    if course_image_file and course_image_file.filename != '':
        try:
            upload_folder = current_app.config['UPLOAD_COURSE_IMAGE_FOLDER']  # Get course image upload folder
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)

            if allowed_file(course_image_file.filename):
                file_extension = os.path.splitext(course_image_file.filename)[1]
                unique_filename = f"course_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(os.path.basename(course_image_file.filename))}{file_extension}"
                filename = secure_filename(unique_filename)
                image_path = os.path.join(upload_folder, filename)
                course_image_file.save(image_path)
                course_image_filepath = "/store/course_images/" + filename  # Relative path to serve images
                logger.info(f"Course image saved to: {course_image_filepath} for course: {course_name}")
            else:
                return jsonify({"msg": "Invalid file type for course image"}), 400

        except Exception as e:
            logger.error(f"Error saving course image for course {course_name}: {e}")
            return jsonify({"msg": "Error saving course image"}), 500

    try:
        course_data = {
            'course_name': course_name,
            'company_name': company_name,  # Get from company profile
            'company_email': current_user_email,
            'company_image': company_image,  # Get from company profile
            'course_image': course_image_filepath,  # Store relative path
            'introduction': introduction,
            'level': level,
            'uploaded_date': datetime.utcnow()
        }
        result = courses_collection.insert_one(course_data)
        logger.info(f"Course created with id: {result.inserted_id}")
        return jsonify({"msg": "Course created successfully", "course_id": str(result.inserted_id)}), 201
    except errors.PyMongoError as e:
        logger.error(f"Database error creating course: {e}")
        return jsonify({"msg": f"Could not create course due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error creating course: {e}")
        return jsonify({"msg": "Error creating course"}), 500


def get_course_logic(course_id):
    try:
        course = courses_collection.find_one({"_id": ObjectId(course_id)})
        if course:
            course['_id'] = str(course['_id'])
            return jsonify(course), 200
        else:
            return jsonify({"msg": "Course not found"}), 404
    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching course: {e}")
        return jsonify({"msg": f"Could not retrieve course due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching course: {e}")
        return jsonify({"msg": "Error fetching course"}), 500


def update_course_logic(course_id):
    claims = get_jwt()
    user_role = claims.get_role()
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can update courses"}), 403

    data = request.form  # Use request.form for file upload
    if not data:
        return jsonify({"msg": "No data provided for update"}), 400

    try:
        course_object_id = ObjectId(course_id)
        existing_course = courses_collection.find_one({"_id": course_object_id})

        if not existing_course:
            return jsonify({"msg": "Course not found"}), 404

        if existing_course['company_email'] != current_user_email:
            return jsonify({"msg": "You are not authorized to update this course"}), 403

        updated_data = {}
        allowed_fields = ['course_name', 'introduction', 'level']  # Allowed text fields
        for field in allowed_fields:
            if field in data:
                updated_data[field] = data[field]

        course_image_file = request.files.get('course_image')  # Check for new image upload
        if course_image_file and course_image_file.filename != '':
            try:
                upload_folder = current_app.config['UPLOAD_COURSE_IMAGE_FOLDER']
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)

                if allowed_file(course_image_file.filename):
                    file_extension = os.path.splitext(course_image_file.filename)[1]
                    unique_filename = f"course_image_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(os.path.basename(course_image_file.filename))}{file_extension}"
                    filename = secure_filename(unique_filename)
                    image_path = os.path.join(upload_folder, filename)
                    course_image_file.save(image_path)
                    course_image_filepath = "/store/course_images/" + filename
                    updated_data['course_image'] = course_image_filepath  # Update course image path
                    logger.info(f"Course image updated to: {course_image_filepath} for course id: {course_id}")
                else:
                    return jsonify({"msg": "Invalid file type for course image"}), 400

            except Exception as e:
                logger.error(f"Error updating course image for course id {course_id}: {e}")
                return jsonify({"msg": "Error updating course image"}), 500

        if not updated_data and not course_image_file:  # Check if any updates to text fields or image
            return jsonify({"msg": "No valid fields to update provided"}), 400

        result = courses_collection.update_one({"_id": course_object_id}, {"$set": updated_data})

        if result.modified_count > 0:
            logger.info(f"Course with id: {course_id} updated successfully by company: {current_user_email}")
            return jsonify({"msg": "Course updated successfully"}), 200
        else:
            return jsonify({"msg": "Course update failed or no changes were made"}), 200

    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error updating course: {e}")
        return jsonify({"msg": f"Could not update course due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error updating course: {e}")
        return jsonify({"msg": "Error updating course"}), 500


def delete_course_logic(course_id):
    claims = get_jwt()
    user_role = claims.get_role()
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can delete courses"}), 403

    try:
        course_object_id = ObjectId(course_id)
        existing_course = courses_collection.find_one({"_id": course_object_id})

        if not existing_course:
            return jsonify({"msg": "Course not found"}), 404

        if existing_course['company_email'] != current_user_email:
            return jsonify({"msg": "You are not authorized to delete this course"}), 403

        result = courses_collection.delete_one({"_id": course_object_id})

        if result.deleted_count > 0:
            logger.info(f"Course with id: {course_id} deleted successfully by company: {current_user_email}")
            return jsonify({"msg": "Course deleted successfully"}), 200
        else:
            return jsonify({"msg": "Course deletion failed or course not found"}), 404

    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error deleting course: {e}")
        return jsonify({"msg": f"Could not delete course due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error deleting course: {e}")
        return jsonify({"msg": "Error deleting course"}), 500


def get_company_courses_logic(company_name):
    try:
        courses_cursor = courses_collection.find({"company_name": company_name})  # Get a cursor, not a list yet
        courses_list = list(courses_cursor)  # Convert cursor to list to iterate and modify

        for course in courses_list:
            course['_id'] = str(course['_id'])  # Convert ObjectId to string

            # **Fetch and count lessons for each course**
            lesson_count = contents_collection.count_documents({"course_id": ObjectId(course['_id'])})
            course['lesson_count'] = lesson_count  # Add lesson_count to course data

        return jsonify(courses_list), 200  # Return the modified list
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching company courses: {e}")
        return jsonify({"msg": f"Could not retrieve company courses due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching company courses: {e}")
        return jsonify({"msg": "Error fetching company courses"}), 500


def get_all_courses_logic():
    try:
        all_courses = list(courses_collection.find())
        for course in all_courses:
            course['_id'] = str(course['_id'])
        return jsonify(all_courses), 200
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching all courses: {e}")
        return jsonify({"msg": f"Could not retrieve courses due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching all courses: {e}")
        return jsonify({"msg": "Error fetching courses"}), 500