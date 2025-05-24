# marks.py
from flask import jsonify # Not directly used here for returning
from pymongo import errors as pymongo_errors
from bson.objectid import ObjectId
import bson.errors # Import for isinstance check in generic exception, if needed
import logging
from datetime import datetime

# Import database collections from auth_utils.py
from auth_utils import (
    # users_collection, # No longer needed here if username constructed from passed names
    courses_collection,
    flow_collection,
    qna_collection,
    marks_collection
)

logger = logging.getLogger(__name__)

def save_specific_user_marks_logic(
    user_id_str: str, 
    course_id_str: str, 
    user_firstname: str = None, # First name from JWT claims (passed by app2.py)
    user_lastname: str = None   # Last name from JWT claims (passed by app2.py)
):
    """
    Calculates and saves/updates marks for a specific user in a specific course.
    user_id_str: The MongoDB _id string of the user.
    course_id_str: The MongoDB _id string of the course.
    user_firstname: User's first name, intended to come from JWT.
    user_lastname: User's last name, intended to come from JWT.
    Raises bson.errors.InvalidId if IDs are malformed.
    Returns a tuple: (response_data_dict, http_status_code)
    """
    # Corrected check for collection initialization
    collections_to_check = [
        courses_collection, flow_collection, qna_collection, marks_collection
    ]
    if not all(collection is not None for collection in collections_to_check):
        uninitialized = [name for name, coll in {
            "courses": courses_collection, "flow": flow_collection,
            "qna": qna_collection, "marks": marks_collection
        }.items() if coll is None]
        logger.error(f"Server config error: Uninitialized collections: {', '.join(uninitialized)}")
        return {"error": "Server configuration error", "detail": "Essential database components unavailable."}, 500

    # These will raise bson.errors.InvalidId if strings are malformed,
    # which will be caught by app2.py
    user_object_id = ObjectId(user_id_str)
    course_object_id = ObjectId(course_id_str)

    try:
        # --- Construct username from passed firstname and lastname ---
        if user_firstname and user_lastname:
            username_for_marks = f"{user_firstname} {user_lastname}".strip()
        elif user_firstname:
            username_for_marks = user_firstname.strip()
        elif user_lastname:
            username_for_marks = user_lastname.strip()
        else:
            # Fallback if firstname/lastname are not available (e.g., not in JWT or not passed)
            logger.warning(f"Firstname or lastname not provided for user {user_id_str}. Falling back for username in marks.")
            username_for_marks = f"User_{user_id_str[:6]}" # Your original fallback
        
        logger.info(f"Using username: '{username_for_marks}' for marks entry of user {user_id_str}.")

        # 2. Fetch Course Details
        course = courses_collection.find_one(
            {"_id": course_object_id},
            {"course_name": 1, "company_name": 1, "level": 1}
        )
        if not course: # Check if course is None
            logger.warning(f"Course not found for ID: {course_id_str}")
            return {"error": "Course not found", "course_id": course_id_str}, 404
        course_name = course.get('course_name', 'Unknown Course')
        company_name = course.get('company_name', 'Unknown Company')
        level = course.get('level', 'Unknown Level')


        # 3. Fetch Fluency Score (from flow collection)
        # Assuming user_id in flow_collection is the MongoDB _id string of the user.
        fluency_record = flow_collection.find_one(
            {"user_id": user_id_str, "course_id": course_id_str},
            sort=[("analysis_timestamp", -1)]
        )
        fluency_score_percentage = 0.0
        if fluency_record and fluency_record.get('fluency_score'):
            try:
                fluency_score_str = fluency_record['fluency_score']
                fluency_score_percentage = float(fluency_score_str.replace('%', '').strip())
            except (ValueError, AttributeError) as e:
                logger.warning(f"Could not parse fluency_score '{fluency_record.get('fluency_score')}' for user {user_id_str}, course {course_id_str}. Error: {e}")
        else:
            logger.info(f"No fluency record/score for user {user_id_str}, course {course_id_str}.")

        # 4. Fetch Essay Rating Score (from qna collection)
        # Assuming user_id in qna_collection is the MongoDB _id string of the user.
        qna_record = qna_collection.find_one(
            {"user_id": user_id_str, "course_id": course_id_str},
            sort=[("evaluation_timestamp", -1)]
        )
        essay_rating_percentage = 0.0
        if qna_record and qna_record.get('rating_score_percentage') is not None:
            try:
                essay_rating_percentage = float(qna_record['rating_score_percentage'])
            except (ValueError, TypeError) as e:
                 logger.warning(f"Could not parse essay_rating_percentage '{qna_record.get('rating_score_percentage')}' for user {user_id_str}, course {course_id_str}. Error: {e}")
        else:
            logger.info(f"No QnA record/rating for user {user_id_str}, course {course_id_str}.")

        # 5. Calculate Overall Marks
        overall_marks = round((fluency_score_percentage + essay_rating_percentage) / 2.0, 2)

        # 6. Prepare marks document
        marks_data = {
            "user_id": user_object_id,
            "username": username_for_marks, # <<< --- USES THE CONSTRUCTED USERNAME
            "course_id": course_object_id,
            "course_name": course_name,
            "company_name": company_name,
            "level": level,
            "fluency_score_percentage": fluency_score_percentage,
            "essay_rating_percentage": essay_rating_percentage,
            "overall_marks_percentage": overall_marks,
            "calculation_timestamp": datetime.utcnow()
        }

        # 7. Save to 'marks' collection
        result = marks_collection.update_one(
            {"user_id": user_object_id, "course_id": course_object_id},
            {"$set": marks_data},
            upsert=True
        )

        status_msg = "Marks calculation initiated."
        http_status = 200
        marks_id_to_return = None
        
        if result.upserted_id:
            status_msg = "Marks calculated and saved successfully (new record created)."
            http_status = 201
            marks_id_to_return = str(result.upserted_id)
        elif result.modified_count > 0:
            status_msg = "Marks updated successfully."
            updated_doc = marks_collection.find_one({"user_id": user_object_id, "course_id": course_object_id})
            marks_id_to_return = str(updated_doc['_id']) if updated_doc else None
        else: 
            status_msg = "Marks already up-to-date or no effective change."
            existing_doc = marks_collection.find_one({"user_id": user_object_id, "course_id": course_object_id})
            marks_id_to_return = str(existing_doc['_id']) if existing_doc else None
        
        logger.info(f"{status_msg} for user_id: {user_id_str}, course_id: {course_id_str}.")
        return {
            "msg": status_msg,
            "marks_id": marks_id_to_return,
            "overall_marks_calculated": overall_marks
        }, http_status

    except pymongo_errors.PyMongoError as e:
        logger.error(f"Database error during marks calculation for user {user_id_str}, course {course_id_str}: {e}")
        return {"error": "Database operation failed", "detail": str(e)}, 500
    # Catching bson.errors.InvalidId here is fine if ObjectId conversion is done inside the try block
    # Or it can be allowed to propagate to app2.py if ObjectId conversion is done before the try block.
    # For ObjectId() calls at the top of the function, app2.py's handler is preferred.
    except Exception as e: 
        logger.error(f"Unexpected error during marks calculation for user {user_id_str}, course {course_id_str}: {e}", exc_info=True)
        if isinstance(e, bson.errors.InvalidId): # Specific check if it's an InvalidId
             return {"error": "Invalid ID format for user or course.", "detail": str(e)}, 400
        return {"error": "Unexpected server error during marks processing", "detail": str(e)}, 500


def get_specific_user_marks_logic(user_id_str: str):
    """
    Retrieves all marks records for a specific user.
    Raises bson.errors.InvalidId if user_id_str is malformed.
    Returns a tuple: (list_of_marks_or_error_dict, http_status_code)
    """
    if marks_collection is None:
        logger.error("Marks collection is not initialized for get_specific_user_marks_logic.")
        return {"error": "Server configuration error", "detail": "Marks collection not available."}, 500

    user_object_id = ObjectId(user_id_str) # Can raise bson.errors.InvalidId

    try:
        user_marks_cursor = marks_collection.find({"user_id": user_object_id})
        user_marks_list = []
        for mark in user_marks_cursor:
            mark['_id'] = str(mark['_id'])
            if isinstance(mark.get('user_id'), ObjectId): mark['user_id'] = str(mark['user_id'])
            if isinstance(mark.get('course_id'), ObjectId): mark['course_id'] = str(mark['course_id'])
            if 'calculation_timestamp' in mark and isinstance(mark['calculation_timestamp'], datetime):
                 mark['calculation_timestamp'] = mark['calculation_timestamp'].isoformat()
            user_marks_list.append(mark)

        logger.info(f"Retrieved {len(user_marks_list)} marks records for user_id: {user_id_str}")
        return user_marks_list, 200
        
    except pymongo_errors.PyMongoError as e:
        logger.error(f"Database error fetching marks for user {user_id_str}: {e}")
        return {"error": "Database error fetching marks", "detail": str(e)}, 500
    except Exception as e:
        logger.error(f"Error fetching marks for user {user_id_str}: {e}", exc_info=True)
        if isinstance(e, bson.errors.InvalidId): # Specific check
             return {"error": "Invalid user ID format.", "detail": str(e)}, 400
        return {"error": "Error fetching user marks", "detail": str(e)}, 500


def get_all_students_marks_logic():
    """
    Retrieves all marks records for all students.
    Returns a tuple: (list_of_marks_or_error_dict, http_status_code)
    """
    if marks_collection is None:
        logger.error("Marks collection is not initialized for get_all_students_marks_logic.")
        return {"error": "Server configuration error", "detail": "Marks collection not available."}, 500
    try:
        all_marks_cursor = marks_collection.find({})
        all_marks_list = []
        for mark in all_marks_cursor:
            mark['_id'] = str(mark['_id'])
            if isinstance(mark.get('user_id'), ObjectId): mark['user_id'] = str(mark['user_id'])
            if isinstance(mark.get('course_id'), ObjectId): mark['course_id'] = str(mark['course_id'])
            if 'calculation_timestamp' in mark and isinstance(mark['calculation_timestamp'], datetime):
                 mark['calculation_timestamp'] = mark['calculation_timestamp'].isoformat()
            all_marks_list.append(mark)
        
        logger.info(f"Retrieved {len(all_marks_list)} total marks records.")
        return all_marks_list, 200
    except pymongo_errors.PyMongoError as e:
        logger.error(f"Database error fetching all students marks: {e}")
        return {"error": "Database error fetching all marks", "detail": str(e)}, 500
    except Exception as e:
        logger.error(f"Error fetching all students marks: {e}", exc_info=True)
        return {"error": "Error fetching all marks", "detail": str(e)}, 500