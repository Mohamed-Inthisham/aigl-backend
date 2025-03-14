# enrollments.py
from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from pymongo import errors
from bson.objectid import ObjectId
from datetime import datetime
import logging

# Import database collections from auth_utils.py
from auth_utils import courses_collection, enrollments_collection

logger = logging.getLogger(__name__)

def enroll_in_course_logic(course_id):
    current_user_email = get_jwt_identity()  # Assuming students are also authenticated via JWT

    try:
        course_object_id = ObjectId(course_id)
        course = courses_collection.find_one({"_id": course_object_id})
        if not course:
            return jsonify({"msg": "Course not found"}), 404

        # Check if already enrolled
        existing_enrollment = enrollments_collection.find_one(
            {"student_email": current_user_email, "course_id": course_object_id}
        )
        if existing_enrollment:
            return jsonify({"msg": "Already enrolled in this course"}), 400

        enrollment_data = {
            "student_email": current_user_email,
            "course_id": course_object_id,
            "enrollment_date": datetime.utcnow(),
        }
        enrollments_collection.insert_one(enrollment_data)
        return jsonify({"msg": "Enrolled in course successfully"}), 201

    except errors.InvalidId:
        return jsonify({"msg": "Invalid course ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error during enrollment: {e}")
        return jsonify(
            {"msg": f"Could not enroll due to database error: {str(e)}"}
        ), 500
    except Exception as e:
        logger.error(f"Error during enrollment: {e}")
        return jsonify({"msg": "Error enrolling in course"}), 500


def get_student_enrolled_courses_logic():
    current_user_email = get_jwt_identity()  # Get student email from JWT

    try:
        enrollment_records = list(
            enrollments_collection.find({"student_email": current_user_email})
        )
        enrolled_courses = []
        for enrollment in enrollment_records:
            course_id = enrollment["course_id"]
            course = courses_collection.find_one({"_id": course_id})
            if course:
                course["_id"] = str(course["_id"])  # Convert ObjectId to string
                # Explicitly include course_name and other course details in the response
                enrolled_courses.append({
                    "_id": course["_id"], # Include _id as string
                    "course_name": course.get("course_name"), # Explicitly get course_name (and handle potential missing key)
                    "company_name": course.get("company_name"),
                    "company_email": course.get("company_email"),
                    "company_image": course.get("company_image"),
                    "course_image": course.get("course_image"),
                    "introduction": course.get("introduction"),
                    "level": course.get("level"),
                    "uploaded_date": course.get("uploaded_date")
                    # Add other course fields you want to include in the response
                })

        return jsonify(enrolled_courses), 200
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching enrolled courses: {e}")
        return jsonify(
            {
                "msg": f"Could not retrieve enrolled courses due to database error: {str(e)}"
            }
        ), 500
    except Exception as e:
        logger.error(f"Error fetching enrolled courses: {e}")
        return jsonify({"msg": "Error fetching enrolled courses"}), 500