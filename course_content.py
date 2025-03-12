# course_content.py
from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, get_jwt
from pymongo import errors
from bson.objectid import ObjectId
import logging

# Import database collections from auth_utils.py
from auth_utils import courses_collection, contents_collection

# Configure logging
logger = logging.getLogger(__name__)


def create_content_logic(course_id):
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can add content to courses"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided"}), 400

    required_fields = ['lesson_name', 'link']
    if not all(field in data for field in required_fields):
        return jsonify({"msg": "Missing required fields: lesson_name, link"}), 400

    lesson_name = data.get('lesson_name')
    link = data.get('link')

    try:
        course_object_id = ObjectId(course_id)
        course = courses_collection.find_one({"_id": course_object_id, "company_email": current_user_email}) # Verify company owns the course
        if not course:
            return jsonify({"msg": "Course not found or you are not authorized"}), 404


        content_data = {
            'course_id': course_object_id, # Store ObjectId as course_id
            'lesson_name': lesson_name,
            'link': link
        }
        result = contents_collection.insert_one(content_data)
        logger.info(f"Content created with id: {result.inserted_id} for course id: {course_id}")
        return jsonify({"msg": "Course content created successfully", "content_id": str(result.inserted_id)}), 201
    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error creating course content: {e}")
        return jsonify({"msg": f"Could not create course content due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error creating course content: {e}")
        return jsonify({"msg": "Error creating course content"}), 500


def get_content_logic(content_id):
    try:
        content = contents_collection.find_one({"_id": ObjectId(content_id)})
        if content:
            content['_id'] = str(content['_id'])
            content['course_id'] = str(content['course_id']) # Convert course_id ObjectId to string
            return jsonify(content), 200
        else:
            return jsonify({"msg": "Course content not found"}), 404
    except errors.InvalidId:
        return jsonify({"msg": "Invalid content ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching course content: {e}")
        return jsonify({"msg": f"Could not retrieve course content due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching course content: {e}")
        return jsonify({"msg": "Error fetching course content"}), 500


def update_content_logic(content_id):
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can update course contents"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided for update"}), 400

    try:
        content_object_id = ObjectId(content_id)
        existing_content = contents_collection.find_one({"_id": content_object_id})

        if not existing_content:
            return jsonify({"msg": "Course content not found"}), 404

        course_id_object = existing_content['course_id'] # Get course_id ObjectId from content
        course = courses_collection.find_one({"_id": course_id_object, "company_email": current_user_email}) # Verify company owns the course via course_id in content
        if not course:
            return jsonify({"msg": "You are not authorized to update this content"}), 403


        updated_data = {}
        allowed_fields = ['lesson_name', 'link']
        for field in allowed_fields:
            if field in data:
                updated_data[field] = data[field]

        if not updated_data:
            return jsonify({"msg": "No valid fields to update provided"}), 400


        result = contents_collection.update_one({"_id": content_object_id}, {"$set": updated_data})

        if result.modified_count > 0:
            logger.info(f"Course content with id: {content_id} updated successfully by company: {current_user_email}")
            return jsonify({"msg": "Course content updated successfully"}), 200
        else:
            return jsonify({"msg": "Course content update failed or no changes were made"}), 200

    except errors.InvalidId:
        return jsonify({"msg": "Invalid content ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error updating course content: {e}")
        return jsonify({"msg": f"Could not update course content due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error updating course content: {e}")
        return jsonify({"msg": "Error updating course content"}), 500


def delete_content_logic(content_id):
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can delete course contents"}), 403

    try:
        content_object_id = ObjectId(content_id)
        existing_content = contents_collection.find_one({"_id": content_object_id})

        if not existing_content:
            return jsonify({"msg": "Course content not found"}), 404

        course_id_object = existing_content['course_id'] # Get course_id ObjectId from content
        course = courses_collection.find_one({"_id": course_id_object, "company_email": current_user_email}) # Verify company owns the course via course_id in content
        if not course:
            return jsonify({"msg": "You are not authorized to delete this content"}), 403


        result = contents_collection.delete_one({"_id": content_object_id})

        if result.deleted_count > 0:
            logger.info(f"Course content with id: {content_id} deleted successfully by company: {current_user_email}")
            return jsonify({"msg": "Course content deleted successfully"}), 200
        else:
            return jsonify({"msg": "Course content deletion failed or content not found"}), 404

    except errors.InvalidId:
        return jsonify({"msg": "Invalid content ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error deleting course content: {e}")
        return jsonify({"msg": f"Could not delete course content due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error deleting course content: {e}")
        return jsonify({"msg": "Error deleting course content"}), 500


def get_course_contents_logic(course_id):
    try:
        course_object_id = ObjectId(course_id)
        contents = list(contents_collection.find({"course_id": course_object_id}))
        for content in contents:
            content['_id'] = str(content['_id'])
            content['course_id'] = str(content['course_id']) # Convert course_id ObjectId to string
        return jsonify(contents), 200
    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching course contents: {e}")
        return jsonify({"msg": f"Could not retrieve course contents due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching course contents: {e}")
        return jsonify({"msg": "Error fetching course contents"}), 500