# mcq.py
from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, get_jwt
from pymongo import errors
from bson.objectid import ObjectId
import logging

# Import database collections from auth_utils.py
from auth_utils import courses_collection, contents_collection, mcqs_collection

# Configure logging
logger = logging.getLogger(__name__)


def create_mcq_logic(content_id):
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can add MCQs to course contents"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided"}), 400

    required_fields = ['question_text', 'options', 'correct_answer']
    if not all(field in data for field in required_fields):
        return jsonify({"msg": "Missing required fields: question_text, options, correct_answer"}), 400

    # **VERY CAREFULLY CHECK THESE LINES FOR TYPOS - CASE SENSITIVITY MATTERS!**
    question_text = data.get('question_text')  # **Ensure 'question_text' is EXACTLY as in frontend payload**
    options = data.get('options')              # **Ensure 'options' is EXACTLY as in frontend payload**
    correct_answer = data.get('correct_answer') # **Ensure 'correct_answer' is EXACTLY as in frontend payload**

    if not isinstance(options, list):
        return jsonify({"msg": "'options' must be a list"}), 400
    if not isinstance(correct_answer, str):
        return jsonify({"msg": "'correct_answer' must be a string"}), 400


    try:
        content_object_id = ObjectId(content_id)
        content = contents_collection.find_one({"_id": content_object_id})
        if not content:
            return jsonify({"msg": "Course content not found"}), 404

        # Verify company owns the course to which this content belongs
        course_id_object = content['course_id']
        course = courses_collection.find_one({"_id": course_id_object, "company_email": current_user_email})
        if not course:
            return jsonify({"msg": "You are not authorized to add MCQs to this content"}), 403


        mcq_data = {
            'content_id': content_object_id, # Link to content
            'question_text': question_text,
            'options': options,
            'correct_answer': correct_answer
        }
        result = mcqs_collection.insert_one(mcq_data)
        logger.info(f"MCQ created with id: {result.inserted_id} for content id: {content_id}")
        return jsonify({"msg": "MCQ created successfully", "mcq_id": str(result.inserted_id)}), 201
    except errors.InvalidId:
        return jsonify({"msg": "Invalid content ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error creating MCQ: {e}")
        return jsonify({"msg": f"Could not create MCQ due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error creating MCQ: {e}")
        return jsonify({"msg": "Error creating MCQ"}), 500


def get_mcq_logic(mcq_id):
    try:
        mcq = mcqs_collection.find_one({"_id": ObjectId(mcq_id)})
        if mcq:
            mcq['_id'] = str(mcq['_id'])
            mcq['content_id'] = str(mcq['content_id']) # Convert content_id ObjectId to string
            return jsonify(mcq), 200
        else:
            return jsonify({"msg": "MCQ not found"}), 404
    except errors.InvalidId:
        return jsonify({"msg": "Invalid MCQ ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching MCQ: {e}")
        return jsonify({"msg": f"Could not retrieve MCQ due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching MCQ: {e}")
        return jsonify({"msg": "Error fetching MCQ"}), 500


def update_mcq_logic(mcq_id):
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can update MCQs"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided for update"}), 400

    try:
        mcq_object_id = ObjectId(mcq_id)
        existing_mcq = mcqs_collection.find_one({"_id": mcq_object_id})

        if not existing_mcq:
            return jsonify({"msg": "MCQ not found"}), 404

        content_id_object = existing_mcq['content_id'] # Get content_id ObjectId from MCQ
        content = contents_collection.find_one({"_id": content_id_object})
        if not content:
            return jsonify({"msg": "Associated course content not found"}), 404

        course_id_object = content['course_id'] # Get course_id from content
        course = courses_collection.find_one({"_id": course_id_object, "company_email": current_user_email}) # Verify company ownership via course
        if not course:
            return jsonify({"msg": "You are not authorized to update this MCQ"}), 403


        updated_data = {}
        allowed_fields = ['question_text', 'options', 'correct_answer']
        for field in allowed_fields:
            if field in data:
                updated_data[field] = data[field]

        if not updated_data:
            return jsonify({"msg": "No valid fields to update provided"}), 400


        result = mcqs_collection.update_one({"_id": mcq_object_id}, {"$set": updated_data})

        if result.modified_count > 0:
            logger.info(f"MCQ with id: {mcq_id} updated successfully by company: {current_user_email}")
            return jsonify({"msg": "MCQ updated successfully"}), 200
        else:
            return jsonify({"msg": "MCQ update failed or no changes were made"}), 200

    except errors.InvalidId:
        return jsonify({"msg": "Invalid MCQ ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error updating MCQ: {e}")
        return jsonify({"msg": f"Could not update MCQ due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error updating MCQ: {e}")
        return jsonify({"msg": "Error updating MCQ"}), 500


def delete_mcq_logic(mcq_id):
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can delete MCQs"}), 403

    try:
        mcq_object_id = ObjectId(mcq_id)
        existing_mcq = mcqs_collection.find_one({"_id": mcq_object_id})

        if not existing_mcq:
            return jsonify({"msg": "MCQ not found"}), 404

        content_id_object = existing_mcq['content_id'] # Get content_id ObjectId from MCQ
        content = contents_collection.find_one({"_id": content_id_object})
        if not content:
            return jsonify({"msg": "Associated course content not found"}), 404

        course_id_object = content['course_id'] # Get course_id from content
        course = courses_collection.find_one({"_id": course_id_object, "company_email": current_user_email}) # Verify company ownership via course
        if not course:
            return jsonify({"msg": "You are not authorized to delete this MCQ"}), 403


        result = mcqs_collection.delete_one({"_id": mcq_object_id})

        if result.deleted_count > 0:
            logger.info(f"MCQ with id: {mcq_id} deleted successfully by company: {current_user_email}")
            return jsonify({"msg": "MCQ deleted successfully"}), 200
        else:
            return jsonify({"msg": "MCQ deletion failed or MCQ not found"}), 404

    except errors.InvalidId:
        return jsonify({"msg": "Invalid MCQ ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error deleting MCQ: {e}")
        return jsonify({"msg": f"Could not delete MCQ due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error deleting MCQ: {e}")
        return jsonify({"msg": "Error deleting MCQ"}), 500


def check_mcq_answer_logic(mcq_id):
    data = request.get_json()
    if not data:
        return jsonify({"msg": "No data provided"}), 400

    student_answer = data.get('student_answer')
    if not student_answer:
        return jsonify({"msg": "Missing 'student_answer' in request body"}), 400

    try:
        mcq_object_id = ObjectId(mcq_id)
        mcq = mcqs_collection.find_one({"_id": mcq_object_id})
        if not mcq:
            return jsonify({"msg": "MCQ not found"}), 404

        correct_answer_letter = mcq.get('correct_answer') # Get correct answer letter ("A", "B", "C", "D")
        options = mcq.get('options') # Get the options list

        correct_option_text = ""
        if correct_answer_letter == "A":
            correct_option_text = options[0] if len(options) > 0 else ""
        elif correct_answer_letter == "B":
            correct_option_text = options[1] if len(options) > 1 else ""
        elif correct_answer_letter == "C":
            correct_option_text = options[2] if len(options) > 2 else ""
        elif correct_answer_letter == "D":
            correct_option_text = options[3] if len(options) > 3 else ""
        # Add more elif for more options if needed

        logger.debug(f"Correct answer letter from DB: {correct_answer_letter}") # Debugging log
        logger.debug(f"Correct option text (determined): {correct_option_text}") # Debugging log
        logger.debug(f"Received student_answer: {student_answer}") # Debugging log


        is_correct = student_answer.strip().lower() == correct_option_text.strip().lower() # Compare student answer with CORRECT OPTION TEXT

        logger.debug(f"Comparison result (before return): {is_correct}") # Debugging log


        return jsonify({
            "is_correct": is_correct,
            "correct_answer": correct_answer_letter, # Return the letter for frontend info
            "student_answer": student_answer,
            "mcq_id": mcq_id
        }), 200

    except errors.InvalidId:
        return jsonify({"msg": "Invalid MCQ ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error checking MCQ answer: {e}")
        return jsonify({"msg": f"Could not check MCQ answer due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error checking MCQ answer: {e}")
        return jsonify({"msg": "Error checking MCQ answer"}), 500


def get_content_mcqs_logic(content_id):
    try:
        content_object_id = ObjectId(content_id)
        mcqs = list(mcqs_collection.find({"content_id": content_object_id}))
        for mcq in mcqs:
            mcq['_id'] = str(mcq['_id'])
            mcq['content_id'] = str(mcq['content_id']) # Convert content_id ObjectId to string
        return jsonify(mcqs), 200
    except errors.InvalidId:
        return jsonify({"msg": "Invalid content ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching content MCQs: {e}")
        return jsonify({"msg": f"Could not retrieve content MCQs due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching content MCQs: {e}")
        return jsonify({"msg": "Error fetching content MCQs"}), 500