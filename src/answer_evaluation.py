# src/answer_evaluation.py
import torch
import pymongo
import yaml
import os
import numpy as np
import torch.nn.functional as F
from llama_index.core.prompts import (
    ChatMessage,
    MessageRole,
    ChatPromptTemplate,
)
from transformers import AutoTokenizer, AutoModel
from llama_index.llms.groq import Groq
import datetime # For timestamp
import re # For parsing LLM output

# --- Configuration & Model Loading ---

# Load secrets for GROQ API Key
SECRETS_FILE_PATH = 'secrets.yaml' # Define once
GROQ_API_KEY = None
try:
    with open(SECRETS_FILE_PATH) as f:
        secrets = yaml.load(f, Loader=yaml.FullLoader)
    GROQ_API_KEY = secrets.get('GROQ_API_KEY') # Use .get for safer access
    if GROQ_API_KEY:
        os.environ["GROQ_API_KEY"] = GROQ_API_KEY
    else:
        print(f"Warning: GROQ_API_KEY not found in {SECRETS_FILE_PATH}.")
except FileNotFoundError:
    print(f"Warning: {SECRETS_FILE_PATH} not found. GROQ LLM will not be available unless GROQ_API_KEY is set in environment.")
except Exception as e:
    print(f"Error loading {SECRETS_FILE_PATH}: {e}")

# Initialize GROQ LLM
completion_llm = None
if os.environ.get("GROQ_API_KEY"):
    try:
        completion_llm = Groq(
            model="llama3-70b-8192", # Consider making model name configurable
            api_key=os.environ["GROQ_API_KEY"],
            temperature=0.1 # Slightly higher for more nuanced rating, but still low
        )
        print("GROQ LLM (llama3-70b-8192) initialized successfully.")
    except Exception as e:
        print(f"Error initializing GROQ LLM: {e}. LLM-based evaluation will be impaired.")
else:
    print("GROQ_API_KEY not set or found. LLM-based evaluation will be skipped.")


# Load local sentence similarity model
MODEL_ANSWER_PATH = 'models/answer_evaluation' # Define once, ensure this path is correct
model_answer = None
tokenizer_answer = None
device = torch.device('cpu') # Default to CPU

try:
    if torch.cuda.is_available():
        device = torch.device('cuda:0')

    model_answer = AutoModel.from_pretrained(MODEL_ANSWER_PATH, trust_remote_code=True)
    tokenizer_answer = AutoTokenizer.from_pretrained(MODEL_ANSWER_PATH, trust_remote_code=True)
    
    model_answer.to(device)
    model_answer.eval()
    print(f"Answer Evaluation Sentence Similarity Model ({MODEL_ANSWER_PATH}) Loaded Successfully on {device}!!!")
except Exception as e:
    print(f"Error loading local answer evaluation model from {MODEL_ANSWER_PATH}: {e}. Similarity-based evaluation will be impaired.")
    model_answer = None # Ensure it's None if loading fails
    tokenizer_answer = None


# MongoDB Connection
qna_collection = None
try:
    mongo_uri = os.environ.get("MONGO_DB_URI", "mongodb://localhost:27017/")
    client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=5000) # Added timeout
    # Force connection on a request to ensure db is connected
    client.admin.command('ping') 
    db = client['Elearning'] # Or your specific database name
    qna_collection = db['qna']
    print(f"MongoDB connection for QnA successful to {mongo_uri}.")
except Exception as e:
    print(f"MongoDB (QnA) connection error: {e}. QnA results will not be saved to DB.")
    qna_collection = None # Important for graceful failure handling

# --- Helper Functions ---

def mean_pooling(model_output, attention_mask):
    """
    Performs mean pooling on token embeddings.
    model_output: Output from the HuggingFace model.
    attention_mask: Attention mask for the input tokens.
    """
    token_embeddings = model_output[0] # First element of model_output contains all token embeddings
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9) # Clamp to avoid division by zero
    return sum_embeddings / sum_mask

# --- Main Evaluation Logic ---

def inference_answer_evaluation(
    question: str,
    answer01: str,  # Correct Answer
    answer02: str,  # Candidate/User Answer
    user_id: str = None,
    course_id: str = None,
    PRMT_TMPL: str = """
You are an expert AI evaluator for assessing answers to programming and technical questions.
You have been provided with a Question, the ideal Correct Answer, and the Candidate's Answer.

Your task is to:
1. Carefully understand the Question and the key concepts in the Correct Answer.
2. Evaluate the Candidate's Answer based on its accuracy, completeness, relevance to the question, and clarity, when compared against the Correct Answer.
3. Provide a rating for the Candidate's Answer on a scale of 0 to 5, where:
    - 0: Completely incorrect, irrelevant, or no meaningful answer.
    - 1: Mostly incorrect, very little relevance or understanding.
    - 2: Some correct points but significant inaccuracies or omissions, or poor understanding.
    - 3: Partially correct and addresses the main points but has notable omissions or minor inaccuracies.
    - 4: Mostly correct, addresses the question well with minor omissions or areas for improvement.
    - 5: Fully correct, comprehensive, clear, and accurately addresses all aspects of the question like the Correct Answer.

Question: {question}
Correct Answer: {correct_answer}
Candidate Answer: {candidate_answer}

Based on your evaluation, provide only the integer rating (0-5) for the Candidate's Answer.
Rating (0-5):"""
) -> str:
    """
    Evaluates a user's answer against a correct answer for a given question.
    Uses an LLM (if available) or a sentence similarity model as a fallback.
    Saves the evaluation details to MongoDB.
    Returns the rating score as a percentage string (e.g., "80 %").
    """
    rating_score_str = "0 %"  # Default display score string
    final_percentage_score = 0.0 # Default numeric score
    evaluation_method_used = "Unavailable"

    # Ensure answers are strings, handle None by converting to empty string
    question_str = str(question) if question is not None else ""
    correct_answer_str = str(answer01) if answer01 is not None else ""
    user_answer_str = str(answer02) if answer02 is not None else ""

    # Attempt LLM-based evaluation first
    llm_evaluation_successful = False
    if completion_llm:
        try:
            if not user_answer_str.strip(): # If user answer is empty, LLM might not give a good rating
                print("User answer is empty. LLM evaluation might be unreliable. Assigning 0 score from LLM perspective.")
                raw_output_rating = 0
            else:
                sys_template = ChatPromptTemplate(
                    message_templates=[
                        ChatMessage(role=MessageRole.SYSTEM, content=PRMT_TMPL)
                    ]
                )
                fmt_messages = sys_template.format_messages(
                    question=question_str,
                    correct_answer=correct_answer_str,
                    candidate_answer=user_answer_str
                )
                chat_response = completion_llm.chat(fmt_messages)
                raw_output_llm_str = chat_response.message.content.strip()
                
                # Try to extract the first number from the LLM response string
                match = re.search(r'\d+', raw_output_llm_str)
                if match:
                    raw_output_rating = int(match.group(0))
                    if not (0 <= raw_output_rating <= 5):
                        print(f"Warning: LLM returned rating {raw_output_rating} outside 0-5 range. Clamping. Response: '{raw_output_llm_str}'")
                        raw_output_rating = max(0, min(5, raw_output_rating)) # Clamp to 0-5
                else:
                    # If no number, try to see if it's a word like "zero", "one", etc. (basic)
                    # This is a very simple attempt, more robust NLP might be needed for complex non-numeric responses
                    word_to_num = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
                    found_word_rating = False
                    for word, num_val in word_to_num.items():
                        if word in raw_output_llm_str.lower():
                            raw_output_rating = num_val
                            found_word_rating = True
                            break
                    if not found_word_rating:
                         raise ValueError(f"LLM did not return a parsable integer rating. Response: '{raw_output_llm_str}'")
            
            # Convert 0-5 scale to 0-100 percentage (deterministic)
            final_percentage_score = min(100.0, max(0.0, float(raw_output_rating * 20)))
            rating_score_str = f"{round(final_percentage_score, 2)} %"
            llm_evaluation_successful = True
            evaluation_method_used = "LLM"
            print(f"LLM Eval: Q: '{question_str[:30]}...' UserA: '{user_answer_str[:30]}...' -> LLM Rate: {raw_output_rating}/5, Score: {rating_score_str}")

        except Exception as e_llm:
            print(f"LLM-based answer evaluation failed: {e_llm}. Falling back to similarity model if available.")
            llm_evaluation_successful = False # Ensure fallback occurs

    # Fallback to sentence similarity model if LLM failed or not available
    if not llm_evaluation_successful:
        if model_answer and tokenizer_answer:
            try:
                # Handle empty strings for similarity model to avoid errors
                ans1_proc = correct_answer_str if correct_answer_str.strip() else "no reference answer"
                ans2_proc = user_answer_str if user_answer_str.strip() else "no candidate answer"

                # If both answers are effectively empty after processing, assign 0 score
                if ans1_proc == "no reference answer" and ans2_proc == "no candidate answer":
                     final_percentage_score = 0.0
                elif ans2_proc == "no candidate answer": # If only user answer is empty
                    final_percentage_score = 0.0
                else:
                    inputs_01 = tokenizer_answer(
                        ans1_proc, padding=True, truncation=True, max_length=128, return_tensors='pt'
                    ).to(device)
                    inputs_02 = tokenizer_answer(
                        ans2_proc, padding=True, truncation=True, max_length=128, return_tensors='pt'
                    ).to(device)

                    with torch.no_grad():
                        outputs_01 = model_answer(**inputs_01)
                        outputs_02 = model_answer(**inputs_02)

                    embeddings_01 = mean_pooling(outputs_01, inputs_01['attention_mask'])
                    embeddings_02 = mean_pooling(outputs_02, inputs_02['attention_mask'])

                    embeddings_01_norm = F.normalize(embeddings_01, p=2, dim=1)
                    embeddings_02_norm = F.normalize(embeddings_02, p=2, dim=1)
                    
                    cosine_sim = F.cosine_similarity(embeddings_01_norm, embeddings_02_norm).cpu().numpy().squeeze()
                    
                    # Scale cosine similarity (-1 to 1) to 0-100 percentage
                    # (cosine_sim + 1) / 2 maps it to 0-1 range, then * 100
                    final_percentage_score = max(0.0, min(100.0, float(((cosine_sim + 1) / 2) * 100)))
                
                rating_score_str = f"{round(final_percentage_score, 2)} %"
                evaluation_method_used = "SimilarityModel"
                print(f"SimModel Eval: Q: '{question_str[:30]}...' UserA: '{user_answer_str[:30]}...' -> CosSim: {cosine_sim if 'cosine_sim' in locals() else 'N/A'}, Score: {rating_score_str}")

            except Exception as e_sim:
                print(f"Sentence similarity evaluation failed: {e_sim}. Defaulting score.")
                # Keep default score (0%) if similarity also fails
                final_percentage_score = 0.0
                rating_score_str = "0 %"
                evaluation_method_used = "SimilarityModel_Error"
        else:
            print("Neither LLM nor local similarity model is available for evaluation. Defaulting score to 0%.")
            final_percentage_score = 0.0 # Default if no model available
            rating_score_str = "0 %"
            evaluation_method_used = "Unavailable"

    # Prepare document for MongoDB
    db_document = {
        "question": question_str,
        "correct_answer": correct_answer_str,
        "user_answer": user_answer_str,
        "rating_score_percentage": final_percentage_score,
        "rating_score_display": rating_score_str,
        "evaluation_method": evaluation_method_used,
        "evaluation_timestamp": datetime.datetime.utcnow()
    }

    if user_id:
        db_document['user_id'] = str(user_id)
    if course_id:
        db_document['course_id'] = str(course_id)

    if qna_collection is not None:
        try:
            qna_collection.insert_one(db_document)
            print(f"QnA evaluation for User: {user_id}, Course: {course_id} saved to MongoDB.")
        except Exception as e_db:
            print(f"Error saving QnA evaluation to MongoDB: {e_db}")
    else:
        print("MongoDB qna_collection not available. Skipping QnA database insert for this evaluation.")
        
    return rating_score_str