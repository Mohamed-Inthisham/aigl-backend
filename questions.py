# questions.py
from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from pymongo import errors
from bson.objectid import ObjectId
from datetime import datetime
import logging

# Import database collections from auth_utils.py
from auth_utils import essay_question_collection, courses_collection

# Configure logging
logger = logging.getLogger(__name__)


def create_essay_question_logic(course_id):
    """Logic to create a new essay question for a course, including correct answer."""
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can create essay questions"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided"}), 400

    question_text = data.get('question')
    correct_answer_text = data.get('correctAnswer') # Get correct answer from request

    if not question_text or not isinstance(question_text, str):
        return jsonify({"msg": "Question text is required and must be a string"}), 400

    if not correct_answer_text or not isinstance(correct_answer_text, str): # Validate correct answer
        return jsonify({"msg": "Correct answer is required and must be a string"}), 400


    try:
        course_object_id = ObjectId(course_id)
        if not courses_collection.find_one({"_id": course_object_id}):
            return jsonify({"msg": "Course not found"}), 404

        essay_question_data = {
            "course_id": course_object_id,
            "question": question_text,
            "correctAnswer": correct_answer_text, # Store correct answer
            "company_email": current_user_email,
            "created_at": datetime.utcnow()
        }
        result = essay_question_collection.insert_one(essay_question_data)
        logger.info(f"Essay question created with id: {result.inserted_id} for course: {course_id}")
        return jsonify({"msg": "Essay question created successfully", "essay_question_id": str(result.inserted_id)}), 201

    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error creating essay question: {e}")
        return jsonify({"msg": f"Could not create essay question due to database error: {str(e)}"}), 500

    except Exception as e:
        logger.error(f"Error creating essay question: {e}")
        return jsonify({"msg": "Error creating essay question"}), 500


def get_essay_question_logic(essay_question_id):
    """Logic to get a specific essay question by ID, including correct answer."""
    try:
        essay_question = essay_question_collection.find_one({"_id": ObjectId(essay_question_id)})
        if essay_question:
            essay_question['_id'] = str(essay_question['_id'])
            essay_question['course_id'] = str(essay_question['course_id']) # Convert course_id to string
            return jsonify(essay_question), 200
        else:
            return jsonify({"msg": "Essay question not found"}), 404
    except errors.InvalidId:
        return jsonify({"msg": "Invalid essay question ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching essay question: {e}")
        return jsonify({"msg": f"Could not retrieve essay question due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching essay question: {e}")
        return jsonify({"msg": "Error fetching essay question"}), 500


def update_essay_question_logic(essay_question_id):
    """Logic to update an existing essay question (question text only for now)."""
    # ... (update_essay_question_logic remains mostly the same, but you could extend it to update correctAnswer if needed in the future)
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can update essay questions"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided for update"}), 400

    question_text = data.get('question')
    if question_text is not None and not isinstance(question_text, str):
        return jsonify({"msg": "Question must be a string if provided for update"}), 400

    try:
        essay_question_object_id = ObjectId(essay_question_id)
        existing_question = essay_question_collection.find_one({"_id": essay_question_object_id})

        if not existing_question:
            return jsonify({"msg": "Essay question not found"}), 404

        if existing_question['company_email'] != current_user_email:
            return jsonify({"msg": "You are not authorized to update this essay question"}), 403

        updated_data = {}
        if question_text is not None:
            updated_data['question'] = question_text

        if not updated_data:
            return jsonify({"msg": "No valid fields to update provided"}), 400

        result = essay_question_collection.update_one({"_id": essay_question_object_id}, {"$set": updated_data})

        if result.modified_count > 0:
            logger.info(f"Essay question with id: {essay_question_id} updated successfully by company: {current_user_email}")
            return jsonify({"msg": "Essay question updated successfully"}), 200
        else:
            return jsonify({"msg": "Essay question update failed or no changes were made"}), 200

    except errors.InvalidId:
        return jsonify({"msg": "Invalid essay question ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error updating essay question: {e}")
        return jsonify({"msg": f"Could not update essay question due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error updating essay question: {e}")
        return jsonify({"msg": "Error updating essay question"}), 500


def delete_essay_question_logic(essay_question_id):
    """Logic to delete an essay question."""
    # ... (delete_essay_question_logic remains the same)
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can delete essay questions"}), 403

    try:
        essay_question_object_id = ObjectId(essay_question_id)
        existing_question = essay_question_collection.find_one({"_id": essay_question_object_id})

        if not existing_question:
            return jsonify({"msg": "Essay question not found"}), 404

        if existing_question['company_email'] != current_user_email:
            return jsonify({"msg": "You are not authorized to delete this essay question"}), 403

        result = essay_question_collection.delete_one({"_id": essay_question_object_id})

        if result.deleted_count > 0:
            logger.info(f"Essay question with id: {essay_question_id} deleted successfully by company: {current_user_email}")
            return jsonify({"msg": "Essay question deleted successfully"}), 200
        else:
            return jsonify({"msg": "Essay question deletion failed or essay question not found"}), 404

    except errors.InvalidId:
        return jsonify({"msg": "Invalid essay question ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error deleting essay question: {e}")
        return jsonify({"msg": f"Could not delete essay question due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error deleting essay question: {e}")
        return jsonify({"msg": "Error deleting essay question"}), 500


def get_course_essay_questions_logic(course_id):
    """Logic to get all essay questions for a specific course."""
    # ... (get_course_essay_questions_logic remains the same)
    try:
        course_object_id = ObjectId(course_id)
        essay_questions_cursor = essay_question_collection.find({"course_id": course_object_id})
        essay_questions_list = list(essay_questions_cursor)

        for question in essay_questions_list:
            question['_id'] = str(question['_id'])
            question['course_id'] = str(question['course_id']) # Convert course_id to string

        return jsonify(essay_questions_list), 200
    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching essay questions for course: {e}")
        return jsonify({"msg": f"Could not retrieve essay questions for course due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching essay questions for course: {e}")
        return jsonify({"msg": "Error fetching essay questions for course"}), 500


def get_course_essay_question_by_course_id_logic(course_id):
    """Logic to get an essay question for a specific course ID."""
    # ... (get_course_essay_question_by_course_id_logic remains the same)
    try:
        course_object_id = ObjectId(course_id)
        essay_question = essay_question_collection.find_one({"course_id": course_object_id}) # Find ONE based on course_id

        if essay_question:
            essay_question['_id'] = str(essay_question['_id'])
            essay_question['course_id'] = str(essay_question['course_id'])
            return jsonify(essay_question), 200 # Return the single essay question object
        else:
            return jsonify({"msg": "Essay question not found for this course"}), 404
    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching essay question by course ID: {e}")
        return jsonify({"msg": f"Database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching essay question by course ID: {e}")
        return jsonify({"msg": "Error fetching essay question"}), 500