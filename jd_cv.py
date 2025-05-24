# jd.py
from flask import jsonify, request, current_app
from flask_jwt_extended import get_jwt_identity, get_jwt
from pymongo import errors
from bson.objectid import ObjectId
from datetime import datetime
import logging
import os
from werkzeug.utils import secure_filename

# Import database collections from auth_utils.py
from auth_utils import jds_cv_collection, companies_collection

# Configure logging
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def allowed_jd_pdf_file(filename):
    """Checks if the filename has a .pdf extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() == 'pdf'

# --- Logic Functions ---
    #Logics for CV part
    # jd.py (add these new functions)
# ... (keep existing imports and functions) ...

# jd.py (add this new function)
# ... (keep existing imports and functions) ...

def create_cv_jd_match_logic():
    """
    Creates a new CV-JD match record in the database.
    Expects 'cv_path' (string) and 'matched_jd_paths' (list of strings) in the JSON request body.
    The record will be associated with the currently logged-in company.
    """
    claims = get_jwt()
    current_user_email = get_jwt_identity()
    user_role = claims.get('role')

    if user_role != 'company': # Or whatever role should be allowed to create these
        return jsonify({"msg": "Access restricted"}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({"msg": "Missing JSON in request"}), 400

        cv_path = data.get('cv_path')
        matched_jd_paths = data.get('matched_jd_paths')

        if not cv_path or not isinstance(cv_path, str):
            return jsonify({"msg": "Missing or invalid 'cv_path'"}), 400
        if not matched_jd_paths or not isinstance(matched_jd_paths, list):
            return jsonify({"msg": "Missing or invalid 'matched_jd_paths' (must be a list)"}), 400
        if not all(isinstance(p, str) for p in matched_jd_paths):
            return jsonify({"msg": "All items in 'matched_jd_paths' must be strings"}), 400
        
        # Potentially validate if the cv_path and jd_paths actually exist or are in a valid format/location
        # For now, we'll assume they are provided correctly by the calling process.

        # Fetch company_id if needed for consistency, though company_email is the primary link here
        company_doc = companies_collection.find_one({"email": current_user_email}, {"_id": 1})
        company_id_str = str(company_doc["_id"]) if company_doc else None


        cv_jd_match_record = {
            "company_email": current_user_email,
            "company_id": company_id_str, # Optional, but good for consistency if you use it elsewhere
            "CV": cv_path, # e.g., "store/cvs/Anoj_peiris_CV.pdf"
            "JDs": matched_jd_paths, # e.g., ["data/jobs/PERSONAs/JD36.json", ...]
            "processed_date": datetime.utcnow() # Timestamp of creation
            # You could add other metadata if needed, e.g., source_of_match
        }

        result = jds_cv_collection.insert_one(cv_jd_match_record)
        
        logger.info(f"CV-JD match record created with id: {result.inserted_id} by company: {current_user_email}")
        return jsonify({
            "msg": "CV-JD match record created successfully",
            "record_id": str(result.inserted_id)
        }), 201

    except errors.PyMongoError as e:
        logger.error(f"Database error creating CV-JD match record for company {current_user_email}: {e}")
        return jsonify({"msg": f"Could not create CV-JD match record due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error creating CV-JD match record for company {current_user_email}: {e}")
        return jsonify({"msg": "Error creating CV-JD match record"}), 500
    




    #--------------------------------------

def get_company_cv_jd_matches_logic():
    """
    Retrieves all CV-JD match records for the logged-in company.
    These records are identified by the presence of a 'CV' field and 'JDs' array.
    """
    claims = get_jwt()
    current_user_email = get_jwt_identity()
    user_role = claims.get('role')

    if user_role != 'company':
        return jsonify({"msg": "Access restricted to companies"}), 403

    try:
        # Query for documents that represent CV-JD matches and belong to the current company
        # We identify them by the presence of the 'CV' field (and 'JDs' field)
        # AND ensure they are associated with the current company's email.
        cv_jd_match_cursor = jds_cv_collection.find({
            "company_email": current_user_email,
            "CV": {"$exists": True},  # Document has a 'CV' field
            "JDs": {"$exists": True}   # Document has a 'JDs' field (array)
        }).sort("uploaded_date", -1) # Assuming you might add an 'uploaded_date' to these docs too

        cv_jd_matches_list = []
        for doc in cv_jd_match_cursor:
            # Prepare matched JDs - extract filename as title
            matched_jds_info = []
            if isinstance(doc.get("JDs"), list):
                for jd_path in doc.get("JDs", []):
                    if isinstance(jd_path, str):
                        # Extract filename from path to use as a title
                        jd_title = os.path.basename(jd_path)
                        # Remove .json extension if present for cleaner title
                        if jd_title.lower().endswith(".json"):
                            jd_title = jd_title[:-5]
                        matched_jds_info.append({
                            "id": jd_path, # Use the path as a unique ID for the sub-item
                            "title": jd_title,
                            # "match_score": doc.get("match_scores", {}).get(jd_path) # If you store scores
                        })
            
            # Extract CV filename from its path
            cv_filename = "Unknown CV"
            if isinstance(doc.get("CV"), str):
                cv_filename = os.path.basename(doc.get("CV"))


            cv_jd_matches_list.append({
                "_id": str(doc["_id"]),
                "cv_filename": cv_filename,
                # Add a date if your CV-JD match docs have one, otherwise use a placeholder or omit
                "cv_upload_date": doc.get("uploaded_date", datetime.utcnow()).isoformat(), # Or None if not always present
                "matched_jds": matched_jds_info,
                # "company_email": doc.get("company_email") # For verification if needed later
            })
        
        return jsonify(cv_jd_matches_list), 200

    except errors.PyMongoError as e:
        logger.error(f"Database error fetching CV-JD matches for company '{current_user_email}': {e}")
        return jsonify({"msg": f"Could not retrieve CV-JD matches: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching CV-JD matches for company '{current_user_email}': {e}")
        return jsonify({"msg": "Error fetching CV-JD matches"}), 500


def delete_company_cv_jd_match_logic(cv_match_id_str):
    """
    Deletes a specific CV-JD match record by its _id.
    Also attempts to delete the associated CV PDF file.
    """
    claims = get_jwt()
    current_user_email = get_jwt_identity()
    user_role = claims.get('role')

    if user_role != 'company':
        return jsonify({"msg": "Access restricted to companies"}), 403

    try:
        cv_match_object_id = ObjectId(cv_match_id_str)
    except errors.InvalidId:
        return jsonify({"msg": "Invalid CV Match ID format"}), 400

    try:
        # Find the CV-JD match document
        cv_jd_match_doc = jds_cv_collection.find_one({
            "_id": cv_match_object_id,
            "CV": {"$exists": True},
            "JDs": {"$exists": True}
        })

        if not cv_jd_match_doc:
            return jsonify({"msg": "CV-JD match record not found"}), 404

        # Authorization check: Ensure the record belongs to the current company
        if cv_jd_match_doc.get("company_email") != current_user_email:
            logger.warning(f"Unauthorized attempt to delete CV-JD match ID {cv_match_id_str} by {current_user_email}")
            return jsonify({"msg": "You are not authorized to delete this record"}), 403

        # Attempt to delete the physical CV file
        cv_file_path_relative = cv_jd_match_doc.get("CV") # e.g., "store/cvs/Chamindu-CV_1.pdf"
        if cv_file_path_relative and isinstance(cv_file_path_relative, str):
            try:
                # Construct absolute path. current_app.root_path is your app's root.
                # The path in DB "store/cvs/..." assumes 'store' is at the root level of your app.
                # Adjust if your UPLOAD_CV_FOLDER or structure is different.
                # For safety, ensure UPLOAD_CV_FOLDER is configured and used.
                # Here, we derive from the structure "store/cvs/"
                base_upload_dir = os.path.join(current_app.root_path) # if 'store' is directly in app root
                # cv_file_path_abs = os.path.join(base_upload_dir, cv_file_path_relative.lstrip('/\\'))
                
                # A safer way if you have UPLOAD_CV_FOLDER configured:
                # cv_upload_folder = current_app.config.get('UPLOAD_CV_FOLDER', os.path.join(current_app.root_path, 'store', 'cvs'))
                # cv_filename_only = os.path.basename(cv_file_path_relative)
                # cv_file_path_abs = os.path.join(cv_upload_folder, cv_filename_only)
                
                # Simplified for now, assuming cv_file_path_relative is like "store/cvs/file.pdf"
                # and "store" is in the application root.
                cv_file_path_abs = os.path.join(current_app.root_path, *cv_file_path_relative.split('/'))


                if os.path.exists(cv_file_path_abs):
                    os.remove(cv_file_path_abs)
                    logger.info(f"Deleted CV PDF file: {cv_file_path_abs} for CV-JD match ID {cv_match_id_str}")
                else:
                    logger.warning(f"CV PDF file not found for deletion: {cv_file_path_abs} (DB path: {cv_file_path_relative})")
            except Exception as e:
                logger.error(f"Error deleting CV PDF file {cv_file_path_relative} for CV-JD match ID {cv_match_id_str}: {e}")
                # Decide if you want to stop DB deletion. For now, we log and continue.

        # Delete the CV-JD match record from the database
        result = jds_cv_collection.delete_one({"_id": cv_match_object_id})

        if result.deleted_count > 0:
            logger.info(f"CV-JD match record with id: {cv_match_id_str} deleted successfully by: {current_user_email}")
            return jsonify({"msg": "CV-JD match record and associated CV PDF (if found) deleted successfully"}), 200
        else:
            # Should not happen if find_one found it, but as a safeguard
            return jsonify({"msg": "CV-JD match record deletion failed or record not found (already deleted?)"}), 404

    except errors.PyMongoError as e:
        logger.error(f"Database error deleting CV-JD match record {cv_match_id_str}: {e}")
        return jsonify({"msg": f"Could not delete CV-JD match record due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error deleting CV-JD match record {cv_match_id_str}: {e}")
        return jsonify({"msg": "Error deleting CV-JD match record"}), 500