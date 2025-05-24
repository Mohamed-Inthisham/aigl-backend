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
from auth_utils import jds_collection, companies_collection, jds_cv_collection

# Configure logging
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def allowed_jd_pdf_file(filename):
    """Checks if the filename has a .pdf extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() == 'pdf'

# --- Logic Functions ---

def create_jd_logic():
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity() # This acts as the company identifier

    if user_role != 'company':
        return jsonify({"msg": "Companies only can upload job descriptions"}), 403

    if 'jd_pdf' not in request.files:
        return jsonify({"msg": "No PDF file part in the request"}), 400

    jd_pdf_file = request.files['jd_pdf']

    if jd_pdf_file.filename == '':
        return jsonify({"msg": "No PDF file selected"}), 400

    if not jd_pdf_file or not allowed_jd_pdf_file(jd_pdf_file.filename):
        return jsonify({"msg": "Invalid file type. Only PDF files are allowed."}), 400

    # Fetch company details for context (e.g., company_name for display)
    company_data = companies_collection.find_one({'email': current_user_email})
    if not company_data:
        # This should ideally not happen if the JWT token is valid and role is company
        logger.error(f"Company profile not found for email: {current_user_email} despite valid JWT.")
        return jsonify({"msg": "Company profile not found. Please ensure your company profile is complete."}), 404

    company_name = company_data.get('company_name', "Unknown Company") # Default if not found
    company_id = str(company_data.get('_id')) # Assuming your company doc has an _id

    jd_pdf_filepath = None
    original_filename = secure_filename(jd_pdf_file.filename) # Secure the original filename first

    try:
        # Ensure UPLOAD_JD_FOLDER is configured in your Flask app
        upload_folder = current_app.config.get('UPLOAD_JD_FOLDER') #, os.path.join(current_app.root_path, 'store', 'jd_pdfs')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True) # exist_ok=True handles concurrent creation

        # Create a unique filename to prevent overwrites and for better organization
        file_extension = os.path.splitext(original_filename)[1] # Should be .pdf
        unique_prefix = f"jd_{company_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # Use a secured version of the original filename in the unique name if desired, or just a generic name
        # Example: unique_filename = f"{unique_prefix}_{original_filename}"
        unique_filename = f"{unique_prefix}{file_extension}" # Simpler: jd_companyid_timestamp.pdf

        # Final filename should also be secured, though unique_prefix helps a lot
        final_filename = secure_filename(unique_filename)
        file_path = os.path.join(upload_folder, final_filename)
        jd_pdf_file.save(file_path)
        jd_pdf_filepath = f"/store/jd_pdfs/{final_filename}" # Relative path for serving/reference
        logger.info(f"JD PDF saved to: {file_path} for company_email: {current_user_email}")

    except Exception as e:
        logger.error(f"Error saving JD PDF for company_email {current_user_email}: {e}")
        return jsonify({"msg": "Error saving JD PDF document"}), 500

    try:
        jd_data = {
            'company_email': current_user_email, # Main identifier for the company posting
            'company_id': company_id, # The ObjectId of the company from companies_collection
            'company_name': company_name, # For easier display
            'jd_pdf_path': jd_pdf_filepath,
            'original_filename': original_filename, # Original name of the uploaded PDF
            'uploaded_date': datetime.utcnow(),
            #'status': 'active' # Default status, e.g., active, archived
        }
        result = jds_collection.insert_one(jd_data)
        logger.info(f"JD PDF record created with id: {result.inserted_id} by company_email: {current_user_email}")
        return jsonify({
            "msg": "Job Description PDF uploaded successfully",
            "jd_id": str(result.inserted_id),
            "file_path": jd_pdf_filepath,
            "original_filename": original_filename
        }), 201
    except errors.PyMongoError as e:
        logger.error(f"Database error creating JD PDF record: {e}")
        if jd_pdf_filepath and os.path.exists(file_path): # Rollback file save if DB insert fails
            try:
                os.remove(file_path)
                logger.info(f"Rolled back JD PDF file save: {file_path}")
            except OSError as ose:
                logger.error(f"Error rolling back file save: {ose}")
        return jsonify({"msg": f"Could not create JD PDF record due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error creating JD PDF record: {e}")
        if jd_pdf_filepath and os.path.exists(file_path): # Rollback file save
            try:
                os.remove(file_path)
                logger.info(f"Rolled back JD PDF file save: {file_path}")
            except OSError as ose:
                logger.error(f"Error rolling back file save: {ose}")
        return jsonify({"msg": "Error creating JD PDF record"}), 500


def get_jd_logic(jd_id):
    try:
        jd_object_id = ObjectId(jd_id)
        jd = jds_collection.find_one({"_id": jd_object_id})
        if jd:
            jd['_id'] = str(jd['_id'])
            if 'company_id' in jd and isinstance(jd['company_id'], ObjectId): # Ensure company_id is also string
                jd['company_id'] = str(jd['company_id'])
            return jsonify(jd), 200
        else:
            return jsonify({"msg": "Job Description not found"}), 404
    except errors.InvalidId:
        return jsonify({"msg": "Invalid JD ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching JD: {e}")
        return jsonify({"msg": f"Could not retrieve JD due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching JD: {e}")
        return jsonify({"msg": "Error fetching JD"}), 500


def delete_jd_logic(jd_id):
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company': # Or 'admin' if you have admin role
        return jsonify({"msg": "Only companies or administrators can delete job descriptions"}), 403

    try:
        jd_object_id = ObjectId(jd_id)
        existing_jd = jds_collection.find_one({"_id": jd_object_id})

        if not existing_jd:
            return jsonify({"msg": "Job Description not found"}), 404

        # Authorization check: company can only delete their own JDs
        if user_role == 'company' and existing_jd.get('company_email') != current_user_email:
            return jsonify({"msg": "You are not authorized to delete this Job Description"}), 403

        # Delete the associated PDF file from the filesystem
        jd_pdf_path_to_delete = existing_jd.get('jd_pdf_path')
        if jd_pdf_path_to_delete:
            try:
                # Construct absolute path from relative path stored in DB
                # current_app.root_path is the path to your application's root directory
                # Remove leading '/' if present to correctly join with root_path
                file_to_delete_abs = os.path.join(current_app.root_path, jd_pdf_path_to_delete.lstrip('/'))
                if os.path.exists(file_to_delete_abs):
                    os.remove(file_to_delete_abs)
                    logger.info(f"Deleted JD PDF file: {file_to_delete_abs}")
                else:
                    logger.warning(f"JD PDF file not found for deletion: {file_to_delete_abs} (DB path: {jd_pdf_path_to_delete})")
            except Exception as e:
                logger.error(f"Error deleting JD PDF file {jd_pdf_path_to_delete}: {e}")
                # Decide if you want to stop the DB deletion or just log and continue
                # For critical data, you might return an error here.

        result = jds_collection.delete_one({"_id": jd_object_id})

        if result.deleted_count > 0:
            logger.info(f"JD with id: {jd_id} deleted successfully by: {current_user_email}")
            return jsonify({"msg": "Job Description and associated PDF deleted successfully"}), 200
        else:
            return jsonify({"msg": "Job Description deletion failed or JD not found in DB (already deleted?)"}), 404

    except errors.InvalidId:
        return jsonify({"msg": "Invalid JD ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error deleting JD: {e}")
        return jsonify({"msg": f"Could not delete JD due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error deleting JD: {e}")
        return jsonify({"msg": "Error deleting JD"}), 500


def get_company_jds_logic(company_identifier):
    """
    Retrieves all JDs for a specific company.
    The identifier can be company_email or company_id (string version of ObjectId).
    """
    try:
        # Try to see if it's an ObjectId string first
        query = {}
        try:
            query = {"company_email": company_identifier} # Assuming company_identifier is the string _id
            # If you are passing company_email, then query = {"company_email": company_identifier}
        except errors.InvalidId: # If it's not a valid ObjectId format, assume it's an email
            query = {"company_id": company_identifier}


        # Or more simply, if you always pass company_email from the route:
        # query = {"company_email": company_email_from_route_param}

        jds_cursor = jds_collection.find(query).sort("uploaded_date", -1)
        jds_list = []
        for jd in jds_cursor:
            jd['_id'] = str(jd['_id'])
            if 'company_id' in jd and isinstance(jd['company_id'], ObjectId):
                jd['company_id'] = str(jd['company_id'])
            jds_list.append(jd)

        return jsonify(jds_list), 200
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching company JDs for '{company_identifier}': {e}")
        return jsonify({"msg": f"Could not retrieve company JDs: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching company JDs for '{company_identifier}': {e}")
        return jsonify({"msg": "Error fetching company JDs"}), 500


def get_all_jds_logic():
    """
    Retrieves all job descriptions from the database.
    Can be filtered by status, e.g., ?status=active
    """
    try:
        query = {}
        status_filter = request.args.get('status')
        if status_filter:
            query['status'] = status_filter.lower()

        all_jds_cursor = jds_collection.find(query).sort("uploaded_date", -1)
        jds_list = []
        for jd in all_jds_cursor:
            jd['_id'] = str(jd['_id'])
            if 'company_id' in jd and isinstance(jd['company_id'], ObjectId):
                jd['company_id'] = str(jd['company_id'])
            jds_list.append(jd)
        return jsonify(jds_list), 200
    except errors.PyMongoError as e:
        logger.error(f"Database error fetching all JDs: {e}")
        return jsonify({"msg": f"Could not retrieve JDs: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error fetching all JDs: {e}")
        return jsonify({"msg": "Error fetching JDs"}), 500


# Optional: Update JD logic - primarily for replacing the PDF or changing status
def update_jd_logic(jd_id):
    claims = get_jwt()
    user_role = claims.get('role')
    current_user_email = get_jwt_identity()

    if user_role != 'company':
        return jsonify({"msg": "Companies only can update job descriptions"}), 403

    try:
        jd_object_id = ObjectId(jd_id)
        existing_jd = jds_collection.find_one({"_id": jd_object_id})

        if not existing_jd:
            return jsonify({"msg": "Job Description not found"}), 404

        if existing_jd.get('company_email') != current_user_email:
            return jsonify({"msg": "You are not authorized to update this JD"}), 403

        updated_data = {}
        file_updated = False

        # Check for new PDF upload
        if 'jd_pdf' in request.files:
            new_jd_pdf_file = request.files['jd_pdf']
            if new_jd_pdf_file.filename != '':
                if not allowed_jd_pdf_file(new_jd_pdf_file.filename):
                    return jsonify({"msg": "Invalid file type. Only PDF files are allowed for update."}), 400

                original_new_filename = secure_filename(new_jd_pdf_file.filename)
                try:
                    upload_folder = current_app.config.get('UPLOAD_JD_FOLDER', os.path.join(current_app.root_path, 'store', 'jd_pdfs'))
                    if not os.path.exists(upload_folder):
                        os.makedirs(upload_folder, exist_ok=True)

                    # Delete old file
                    old_pdf_path = existing_jd.get('jd_pdf_path')
                    if old_pdf_path:
                        old_file_abs = os.path.join(current_app.root_path, old_pdf_path.lstrip('/'))
                        if os.path.exists(old_file_abs):
                            os.remove(old_file_abs)
                            logger.info(f"Deleted old JD PDF: {old_file_abs} during update")

                    # Save new file
                    company_id_str = str(existing_jd.get('company_id', 'unknown_company'))
                    file_extension = os.path.splitext(original_new_filename)[1]
                    unique_prefix = f"jd_{company_id_str}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    final_filename = secure_filename(f"{unique_prefix}{file_extension}")
                    new_file_path_abs = os.path.join(upload_folder, final_filename)
                    new_jd_pdf_file.save(new_file_path_abs)

                    updated_data['jd_pdf_path'] = f"/store/jd_pdfs/{final_filename}"
                    updated_data['original_filename'] = original_new_filename
                    file_updated = True
                    logger.info(f"JD PDF updated to: {updated_data['jd_pdf_path']} for JD id: {jd_id}")

                except Exception as e:
                    logger.error(f"Error updating JD PDF for JD id {jd_id}: {e}")
                    return jsonify({"msg": "Error updating JD PDF document"}), 500
            # else: no new file selected despite 'jd_pdf' part present

        # Check for status update (if you use request.form for this)
        if 'status' in request.form:
            updated_data['status'] = request.form['status'].lower()


        if not updated_data: # No file and no status change
            return jsonify({"msg": "No changes provided for update (no new PDF or status change)"}), 400

        updated_data['last_updated_date'] = datetime.utcnow()
        result = jds_collection.update_one({"_id": jd_object_id}, {"$set": updated_data})

        if result.modified_count > 0:
            msg = "Job Description PDF and/or status updated successfully" if file_updated else "Job Description status updated successfully"
            logger.info(f"JD with id: {jd_id} updated. Changes: {updated_data.keys()}")
            return jsonify({"msg": msg}), 200
        else:
            # This can happen if the data sent is the same as existing data or only file was "updated" but path was same
            return jsonify({"msg": "JD update processed, but no fields were different or no update occurred."}), 200

    except errors.InvalidId:
        return jsonify({"msg": "Invalid JD ID format"}), 400
    except errors.PyMongoError as e:
        logger.error(f"Database error updating JD: {e}")
        return jsonify({"msg": f"Could not update JD due to database error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error updating JD: {e}")
        return jsonify({"msg": f"Error updating JD: {str(e)}"}), 500
    


