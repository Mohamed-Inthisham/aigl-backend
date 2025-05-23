import json
import os
import pymongo # Make sure this is imported if used by flow_analyzer globally
import uuid # For generating unique filenames (optional but good practice)
from flask import Flask, request, Response
from werkzeug.utils import secure_filename
from flask_cors import CORS

# Assuming your src modules are in the same directory or in PYTHONPATH
from src.document_rag import retrieve_documents # Assuming this function exists
from src.flow_analyzer import flowAnalyzerPipeline
from src.answer_evaluation import inference_answer_evaluation # Assuming this function exists
from src.face_monitoring_inference import face_image_inference, face_analysis # Assuming these exist

app = Flask(__name__)
app.config['UPLOAD_IMAGE_FOLDER'] = 'store/images'
app.config['UPLOAD_AUDIO_FOLDER'] = 'store/audios'
app.config['UPLOAD_CV_FOLDER'] = 'store/cvs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Example: 16MB upload limit

# Ensure upload directories exist
for folder_key in ['UPLOAD_IMAGE_FOLDER', 'UPLOAD_AUDIO_FOLDER', 'UPLOAD_CV_FOLDER']:
    if not os.path.exists(app.config[folder_key]):
        os.makedirs(app.config[folder_key])
        print(f"Created directory: {app.config[folder_key]}")

CORS(app, origins="http://localhost:5173") # Adjust origins for production


@app.route('/api/face_detection', methods=['POST'])
def api_face_detection():
    username = request.form.get('username')
    image_file = request.files.get('image_file')

    if not username or not image_file:
        return Response(
            response=json.dumps({"message": "Username or image_file missing"}),
            status=400,
            mimetype="application/json"
        )
    if image_file.filename == '':
        return Response(
            response=json.dumps({"message": "No selected image file"}),
            status=400,
            mimetype="application/json"
        )

    # Generate a unique filename
    original_filename = secure_filename(image_file.filename)
    filename_stem, file_ext = os.path.splitext(original_filename)
    unique_filename = f"{filename_stem}_{uuid.uuid4().hex}{file_ext}"
    save_path = os.path.join(app.config['UPLOAD_IMAGE_FOLDER'], unique_filename)
    
    try:
        image_file.save(save_path)
        head_pose_text, det_username = face_image_inference(username, save_path)
        return Response(
            response=json.dumps({"Head Pose": head_pose_text, "Username": det_username}),
            status=200,
            mimetype="application/json"
        )
    except Exception as e:
        app.logger.error(f"Face detection failed: {str(e)}", exc_info=True)
        return Response(
            response=json.dumps({"message": "Face detection failed", "error": str(e)}),
            status=500,
            mimetype="application/json"
        )
    finally:
        if os.path.exists(save_path): # Optional: clean up if image not needed after processing
             pass # os.remove(save_path) 


@app.route('/api/face_monitoring', methods=['POST'])
def api_face_monitoring():
    username = request.form.get('username')
    if not username:
        return Response(
            response=json.dumps({"message": "Username missing"}),
            status=400,
            mimetype="application/json"
        )
    try:
        response_data = face_analysis(username) # Renamed to avoid conflict with Response object
        return Response(
            response=json.dumps(response_data),
            status=200,
            mimetype="application/json"
        )
    except Exception as e:
        app.logger.error(f"Face monitoring failed: {str(e)}", exc_info=True)
        return Response(
            response=json.dumps({"message": "Face monitoring failed", "error": str(e)}),
            status=500,
            mimetype="application/json"
        )


@app.route('/api/flow_analyzer', methods=['POST'])
def api_flow_analyzer():
    user_id = request.form.get('userId')
    course_id = request.form.get('courseId')
    student_email = request.form.get('studentEmail')
    audio_file = request.files.get('audio_file')

    if not audio_file:
        return Response(
            response=json.dumps({"message": "No audio file part in the request"}),
            status=400,
            mimetype="application/json"
        )
    if audio_file.filename == '':
        return Response(
            response=json.dumps({"message": "No selected audio file"}),
            status=400,
            mimetype="application/json"
        )

    original_filename = secure_filename(audio_file.filename)
    # You might want to make filenames unique if storing them long-term
    # filename_stem, file_ext = os.path.splitext(original_filename)
    # unique_filename = f"{user_id or 'unknown'}_{filename_stem}_{uuid.uuid4().hex}{file_ext}"
    # save_path = os.path.join(app.config['UPLOAD_AUDIO_FOLDER'], unique_filename)
    save_path = os.path.join(app.config['UPLOAD_AUDIO_FOLDER'], original_filename) # Simpler for now

    try:
        audio_file.save(save_path)
        response_data = flowAnalyzerPipeline(
            audio_path=save_path,
            user_id=user_id,
            course_id=course_id,
            student_email=student_email
        )
        return Response(
            response=json.dumps(response_data),
            status=200,
            mimetype="application/json"
        )
    except Exception as e:
        app.logger.error(f"Flow analysis failed: {str(e)}", exc_info=True)
        return Response(
            response=json.dumps({"message": "Flow analysis failed", "error": str(e)}),
            status=500,
            mimetype="application/json"
        )
    finally:
        # Optional: Clean up the saved audio file if you don't need to keep it permanently
        if os.path.exists(save_path) and False: # Set to True to enable cleanup
             os.remove(save_path)


@app.route('/api/answer_evaluation', methods=['POST'])
def api_answer_evaluation():
    question = request.form.get('question')
    correct_answer = request.form.get('correct_answer')
    user_answer = request.form.get('user_answer')

    if not all([question, correct_answer, user_answer]):
        return Response(
            response=json.dumps({"message": "Missing question, correct_answer, or user_answer"}),
            status=400,
            mimetype="application/json"
        )
    try:
        score_response = inference_answer_evaluation(question, correct_answer, user_answer)
        return Response(
            response=json.dumps({"Score": score_response}),
            status=200,
            mimetype="application/json"
        )
    except Exception as e:
        app.logger.error(f"Answer evaluation failed: {str(e)}", exc_info=True)
        return Response(
            response=json.dumps({"message": "Answer evaluation failed", "error": str(e)}),
            status=500,
            mimetype="application/json"
        )


@app.route('/api/document_rag', methods=['POST'])
def api_document_rag():
    cv_file = request.files.get('cv') # Changed 'data' to 'cv_file' for clarity
    if not cv_file:
        return Response(
            response=json.dumps({"message": "No CV file part in the request"}),
            status=400,
            mimetype="application/json"
        )
    if cv_file.filename == '':
        return Response(
            response=json.dumps({"message": "No selected CV file"}),
            status=400,
            mimetype="application/json"
        )
    
    original_filename = secure_filename(cv_file.filename)
    # unique_filename = f"{original_filename.split('.')[0]}_{uuid.uuid4().hex}.{original_filename.split('.')[-1]}"
    # cv_path = os.path.join(app.config['UPLOAD_CV_FOLDER'], unique_filename)
    cv_path = os.path.join(app.config['UPLOAD_CV_FOLDER'], original_filename) # Simpler for now
    
    try:
        cv_file.save(cv_path)
        jd_response = retrieve_documents(cv_path)
        return Response(
            response=json.dumps({"JDs": jd_response}),
            status=200,
            mimetype="application/json"
        )
    except Exception as e:
        app.logger.error(f"Document RAG failed: {str(e)}", exc_info=True)
        return Response(
            response=json.dumps({"message": "Anomaly PDF Detected or processing failed. Please Upload a Valid CV.", "error": str(e)}),
            status=500, # Or 400 if it's a client-side file format error
            mimetype="application/json"
        )
    finally:
        if os.path.exists(cv_path) and False: # Set to True to enable cleanup
            os.remove(cv_path)

if __name__ == '__main__':
    # Setup logging
    if not app.debug: # More robust logging for production
        import logging
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler('elearning_api.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Elearning API startup')

    app.run(
        debug=True, # Set to False in production
        host='0.0.0.0',
        port=5000
    )