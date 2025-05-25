from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from pymongo import errors
from bson.objectid import ObjectId
from datetime import datetime
import logging

from auth_utils import fluency_test_collection, courses_collection

logger = logging.getLogger(__name__)


def create_fluency_test_logic(course_id):
    """Logic to create a new fluency test for a course with a single oral question."""
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can create fluency tests"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided"}), 400

    oral_question_text = data.get('oral_question') # Get single oral_question
    if not oral_question_text or not isinstance(oral_question_text, str):
        return jsonify({"msg": "Oral question is required and must be a string"}), 400

    try:
        course_object_id = ObjectId(course_id)
        if not courses_collection.find_one({"_id": course_object_id}):
            return jsonify({"msg": "Course not found"}), 404

        fluency_test_data = {
            "course_id": course_object_id,
            "oral_question": oral_question_text, # Store single oral question string
            "company_email": current_user_email, # For authorization later
            "created_at": datetime.utcnow()
        }
        result = fluency_test_collection.insert_one(fluency_test_data)
        logger.info(f"Fluency test created with id: {result.inserted_id} for course: {course_id}")
        return jsonify({"msg": "Fluency test created successfully", "fluency_test_id": str(result.inserted_id)}), 201

    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error creating fluency test: {e}")
        return jsonify({"msg": f"Could not create fluency test due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error creating fluency test: {e}")
        return jsonify({"msg": "Error creating fluency test"}), 500


def get_fluency_test_logic(fluency_test_id):
    """Logic to get a specific fluency test by ID."""
    try:
        fluency_test = fluency_test_collection.find_one({"_id": ObjectId(fluency_test_id)})
        if fluency_test:
            fluency_test['_id'] = str(fluency_test['_id'])
            fluency_test['course_id'] = str(fluency_test['course_id']) # Convert course_id to string
            return jsonify(fluency_test), 200
        else:
            return jsonify({"msg": "Fluency test not found"}), 404
    except errors.InvalidId:
        return jsonify({"msg": "Invalid fluency test ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching fluency test: {e}")
        return jsonify({"msg": f"Could not retrieve fluency test due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching fluency test: {e}")
        return jsonify({"msg": "Error fetching fluency test"}), 500


def update_fluency_test_logic(fluency_test_id):
    """Logic to update an existing fluency test."""
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can update fluency tests"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided for update"}), 400

    oral_question_text = data.get('oral_question') # Get single oral_question for update
    if oral_question_text is not None and not isinstance(oral_question_text, str):
        return jsonify({"msg": "Oral question must be a string if provided for update"}), 400

    try:
        fluency_test_object_id = ObjectId(fluency_test_id)
        existing_test = fluency_test_collection.find_one({"_id": fluency_test_object_id})

        if not existing_test:
            return jsonify({"msg": "Fluency test not found"}), 404

        if existing_test['company_email'] != current_user_email:
            return jsonify({"msg": "You are not authorized to update this fluency test"}), 403

        updated_data = {}
        if oral_question_text is not None:
            updated_data['oral_question'] = oral_question_text # Update single oral question

        if not updated_data:
            return jsonify({"msg": "No valid fields to update provided"}), 400

        result = fluency_test_collection.update_one({"_id": fluency_test_object_id}, {"$set": updated_data})

        if result.modified_count > 0:
            logger.info(f"Fluency test with id: {fluency_test_id} updated successfully by company: {current_user_email}")
            return jsonify({"msg": "Fluency test updated successfully"}), 200
        else:
            return jsonify({"msg": "Fluency test update failed or no changes were made"}), 200

    except errors.InvalidId:
        return jsonify({"msg": "Invalid fluency test ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error updating fluency test: {e}")
        return jsonify({"msg": f"Could not update fluency test due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error updating fluency test: {e}")
        return jsonify({"msg": "Error updating fluency test"}), 500


def delete_fluency_test_logic(fluency_test_id):
    """Logic to delete a fluency test."""
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can delete fluency tests"}), 403

    try:
        fluency_test_object_id = ObjectId(fluency_test_id)
        existing_test = fluency_test_collection.find_one({"_id": fluency_test_object_id})

        if not existing_test:
            return jsonify({"msg": "Fluency test not found"}), 404

        if existing_test['company_email'] != current_user_email:
            return jsonify({"msg": "You are not authorized to delete this fluency test"}), 403

        result = fluency_test_collection.delete_one({"_id": fluency_test_object_id})

        if result.deleted_count > 0:
            logger.info(f"Fluency test with id: {fluency_test_id} deleted successfully by company: {current_user_email}")
            return jsonify({"msg": "Fluency test deleted successfully"}), 200
        else:
            return jsonify({"msg": "Fluency test deletion failed or fluency test not found"}), 404

    except errors.InvalidId:
        return jsonify({"msg": "Invalid fluency test ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error deleting fluency test: {e}")
        return jsonify({"msg": f"Could not delete fluency test due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error deleting fluency test: {e}")
        return jsonify({"msg": "Error deleting fluency test"}), 500


def get_course_fluency_tests_logic(course_id):
    """Logic to get all fluency tests for a specific course."""
    try:
        course_object_id = ObjectId(course_id)
        fluency_tests_cursor = fluency_test_collection.find({"course_id": course_object_id})
        fluency_tests_list = list(fluency_tests_cursor)

        for test in fluency_tests_list:
            test['_id'] = str(test['_id'])
            test['course_id'] = str(test['course_id']) # Convert course_id to string

        return jsonify(fluency_tests_list), 200
    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching fluency tests for course: {e}")
        return jsonify({"msg": f"Could not retrieve fluency tests for course due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching fluency tests for course: {e}")
        return jsonify({"msg": "Error fetching fluency tests for course"}), 500


def get_fluency_test_by_course_id_logic(course_id):
    """Logic to get a fluency test for a specific course ID."""
    try:
        course_object_id = ObjectId(course_id)
        fluency_test = fluency_test_collection.find_one({"course_id": course_object_id}) # Find ONE based on course_id

        if fluency_test:
            fluency_test['_id'] = str(fluency_test['_id'])
            fluency_test['course_id'] = str(fluency_test['course_id'])
            return jsonify(fluency_test), 200 # Return the single fluency test object
        else:
            return jsonify({"msg": "Fluency test not found for this course"}), 404
    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching fluency test by course ID: {e}")
        return jsonify({"msg": f"Database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching fluency test by course ID: {e}")
        return jsonify({"msg": "Error fetching fluency test"}), 500
