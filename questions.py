# questions.py
from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from pymongo import errors
from bson.objectid import ObjectId
from datetime import datetime
import logging

# Import database collections from auth_utils.py
# Ensure these are correctly defined and exported in auth_utils.py
# e.g., from .auth_utils import essay_question_collection, courses_collection
# If auth_utils.py is in the same directory:
from auth_utils import essay_question_collection, courses_collection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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

    if not question_text or not isinstance(question_text, str) or not question_text.strip():
        return jsonify({"msg": "Question text is required, must be a string, and cannot be empty"}), 400

    if not correct_answer_text or not isinstance(correct_answer_text, str) or not correct_answer_text.strip(): # Validate correct answer
        return jsonify({"msg": "Correct answer is required, must be a string, and cannot be empty"}), 400


    try:
        course_object_id = ObjectId(course_id)
        course = courses_collection.find_one({"_id": course_object_id})
        if not course:
            return jsonify({"msg": "Course not found"}), 404
        
        # Optional: Check if the company creating the question owns the course
        # if course.get('company_email') != current_user_email:
        #     return jsonify({"msg": "You are not authorized to add questions to this course"}), 403


        essay_question_data = {
            "course_id": course_object_id,
            "question": question_text.strip(),
            "correctAnswer": correct_answer_text.strip(), # Store correct answer
            "company_email": current_user_email, # Store the email of the company that created it
            "created_at": datetime.utcnow()
        }
        result = essay_question_collection.insert_one(essay_question_data)
        logger.info(f"Essay question created with id: {result.inserted_id} for course: {course_id} by company: {current_user_email}")
        return jsonify({"msg": "Essay question created successfully", "essay_question_id": str(result.inserted_id)}), 201

    except errors.InvalidId:
        logger.warning(f"Invalid course ID format for create_essay_question: {course_id}")
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error creating essay question: {e}")
        return jsonify({"msg": f"Could not create essay question due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error creating essay question: {e}", exc_info=True)
        return jsonify({"msg": "Error creating essay question"}), 500


def get_essay_question_logic(essay_question_id):
    """Logic to get a specific essay question by ID, including correct answer."""
    try:
        q_id_obj = ObjectId(essay_question_id)
        essay_question = essay_question_collection.find_one({"_id": q_id_obj})
        if essay_question:
            essay_question['_id'] = str(essay_question['_id'])
            if 'course_id' in essay_question and isinstance(essay_question['course_id'], ObjectId):
                essay_question['course_id'] = str(essay_question['course_id']) # Convert course_id to string
            return jsonify(essay_question), 200
        else:
            logger.info(f"Essay question not found with id: {essay_question_id}")
            return jsonify({"msg": "Essay question not found"}), 404
    except errors.InvalidId:
        logger.warning(f"Invalid essay question ID format for get_essay_question: {essay_question_id}")
        return jsonify({"msg": "Invalid essay question ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching essay question: {e}")
        return jsonify({"msg": f"Could not retrieve essay question due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching essay question: {e}", exc_info=True)
        return jsonify({"msg": "Error fetching essay question"}), 500


def update_essay_question_logic(essay_question_id):
    """Logic to update an existing essay question (question text and/or correct answer)."""
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can update essay questions"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided for update"}), 400

    logger.debug(f"Update request data for essay_question_id {essay_question_id}: {data}")

    updated_data = {}
    
    # Handle question update
    if 'question' in data:
        question_text = data.get('question')
        if not isinstance(question_text, str): 
            return jsonify({"msg": "Question text must be a string if provided for update"}), 400
        if not question_text.strip(): # Require question to be non-empty
             return jsonify({"msg": "Question text cannot be empty"}), 400
        updated_data['question'] = question_text.strip()

    # Handle correctAnswer update
    if 'correctAnswer' in data:
        correct_answer_text = data.get('correctAnswer')
        if not isinstance(correct_answer_text, str):
            return jsonify({"msg": "Correct answer must be a string if provided for update"}), 400
        if not correct_answer_text.strip(): # Require correct answer to be non-empty
            return jsonify({"msg": "Correct answer cannot be empty"}), 400
        updated_data['correctAnswer'] = correct_answer_text.strip()

    if not updated_data:
        return jsonify({"msg": "No valid fields ('question' or 'correctAnswer') provided for update, or fields were empty."}), 400

    try:
        essay_question_object_id = ObjectId(essay_question_id)
        existing_question = essay_question_collection.find_one({"_id": essay_question_object_id})

        if not existing_question:
            logger.info(f"Essay question not found for update with id: {essay_question_id}")
            return jsonify({"msg": "Essay question not found"}), 404

        # Check ownership: only the company that created the question can update it.
        if existing_question.get('company_email') != current_user_email:
            logger.warning(f"Unauthorized attempt to update essay question {essay_question_id} by {current_user_email}. Owner: {existing_question.get('company_email')}")
            return jsonify({"msg": "You are not authorized to update this essay question"}), 403
        
        # Add an updated_at timestamp
        updated_data['updated_at'] = datetime.utcnow()

        logger.info(f"Attempting to update essay question {essay_question_id} with fields: {updated_data}")

        result = essay_question_collection.update_one(
            {"_id": essay_question_object_id},
            {"$set": updated_data}
        )

        if result.modified_count > 0:
            logger.info(f"Essay question with id: {essay_question_id} updated successfully by company: {current_user_email}")
            return jsonify({"msg": "Essay question updated successfully"}), 200
        elif result.matched_count > 0 and result.modified_count == 0:
             logger.info(f"Essay question with id: {essay_question_id} matched but no changes were made (data might be identical). Payload was: {updated_data}")
             return jsonify({"msg": "Essay question found, but no changes were made."}), 200 # Frontend might treat this as success
        else:
            logger.warning(f"Essay question update for id: {essay_question_id} failed to match. Matched: {result.matched_count}, Modified: {result.modified_count}")
            return jsonify({"msg": "Essay question update failed: not found or no changes specified"}), 400

    except errors.InvalidId:
        logger.warning(f"Invalid essay question ID format for update: {essay_question_id}")
        return jsonify({"msg": "Invalid essay question ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error updating essay question: {e}")
        return jsonify({"msg": f"Could not update essay question due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error updating essay question: {e}", exc_info=True)
        return jsonify({"msg": "Error updating essay question"}), 500


def delete_essay_question_logic(essay_question_id):
    """Logic to delete an essay question."""
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can delete essay questions"}), 403

    try:
        essay_question_object_id = ObjectId(essay_question_id)
        existing_question = essay_question_collection.find_one({"_id": essay_question_object_id})

        if not existing_question:
            logger.info(f"Essay question not found for deletion with id: {essay_question_id}")
            return jsonify({"msg": "Essay question not found"}), 404

        # Check ownership: only the company that created the question can delete it.
        if existing_question.get('company_email') != current_user_email:
            logger.warning(f"Unauthorized attempt to delete essay question {essay_question_id} by {current_user_email}. Owner: {existing_question.get('company_email')}")
            return jsonify({"msg": "You are not authorized to delete this essay question"}), 403

        result = essay_question_collection.delete_one({"_id": essay_question_object_id})

        if result.deleted_count > 0:
            logger.info(f"Essay question with id: {essay_question_id} deleted successfully by company: {current_user_email}")
            return jsonify({"msg": "Essay question deleted successfully"}), 200
        else:
            # This case should ideally not be reached if existing_question was found
            logger.warning(f"Essay question deletion failed for id: {essay_question_id}, or question not found during delete operation.")
            return jsonify({"msg": "Essay question deletion failed or essay question not found"}), 404 # Or 500 if unexpected

    except errors.InvalidId:
        logger.warning(f"Invalid essay question ID format for delete: {essay_question_id}")
        return jsonify({"msg": "Invalid essay question ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error deleting essay question: {e}")
        return jsonify({"msg": f"Could not delete essay question due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error deleting essay question: {e}", exc_info=True)
        return jsonify({"msg": "Error deleting essay question"}), 500


def get_course_essay_questions_logic(course_id):
    """Logic to get all essay questions for a specific course."""
    # No JWT required for this, assuming public or student access after enrollment
    try:
        course_object_id = ObjectId(course_id)
        
        # Optionally, verify the course exists
        if not courses_collection.find_one({"_id": course_object_id}):
             logger.info(f"Course not found when fetching essay questions for course_id: {course_id}")
             return jsonify({"msg": "Course not found"}), 404

        essay_questions_cursor = essay_question_collection.find({"course_id": course_object_id})
        essay_questions_list = []
        for question in essay_questions_cursor:
            question['_id'] = str(question['_id'])
            if 'course_id' in question and isinstance(question['course_id'], ObjectId):
                question['course_id'] = str(question['course_id'])
            essay_questions_list.append(question)

        logger.info(f"Retrieved {len(essay_questions_list)} essay questions for course_id: {course_id}")
        return jsonify(essay_questions_list), 200
    except errors.InvalidId:
        logger.warning(f"Invalid course ID format for get_course_essay_questions: {course_id}")
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching essay questions for course: {e}")
        return jsonify({"msg": f"Could not retrieve essay questions for course due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching essay questions for course: {e}", exc_info=True)
        return jsonify({"msg": "Error fetching essay questions for course"}), 500


def get_course_essay_question_by_course_id_logic(course_id):
    """
    Logic to get ONE essay question for a specific course ID.
    Typically, a course can have multiple essay questions.
    This function will return the first one found. If you need all, use get_course_essay_questions_logic.
    If a course is designed to have only ONE essay question, this is fine.
    """
    # No JWT required for this, assuming public or student access
    try:
        course_object_id = ObjectId(course_id)
        # Optionally, verify the course exists
        if not courses_collection.find_one({"_id": course_object_id}):
             logger.info(f"Course not found when fetching single essay question for course_id: {course_id}")
             return jsonify({"msg": "Course not found"}), 404

        essay_question = essay_question_collection.find_one({"course_id": course_object_id}) # Find ONE based on course_id

        if essay_question:
            essay_question['_id'] = str(essay_question['_id'])
            if 'course_id' in essay_question and isinstance(essay_question['course_id'], ObjectId):
                essay_question['course_id'] = str(essay_question['course_id'])
            logger.info(f"Retrieved single essay question for course_id: {course_id}, question_id: {essay_question['_id']}")
            return jsonify(essay_question), 200 # Return the single essay question object
        else:
            logger.info(f"No essay question found for course_id: {course_id}")
            return jsonify({"msg": "Essay question not found for this course"}), 404
    except errors.InvalidId:
        logger.warning(f"Invalid course ID format for get_course_essay_question_by_course_id: {course_id}")
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching essay question by course ID: {e}")
        return jsonify({"msg": f"Database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching essay question by course ID: {e}", exc_info=True)
        return jsonify({"msg": "Error fetching essay question"}), 500