import json
import pymongo
import re
import torch
import numpy as np
import pandas as pd
from pydub import AudioSegment
from transformers import T5Tokenizer, T5ForConditionalGeneration
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from pydub.silence import split_on_silence
# Assuming convert_AudioToText and end_to_end_audio_to_text are in src.data_conversion
from src.data_conversion import convert_AudioToText, end_to_end_audio_to_text
import os
import uuid # For unique temporary filenames
import datetime # For timestamp

# --- Filler Words ---
filler_words = [
    "um", "uh", "like", "you know", "well", "actually", "basically",
    "literally", "totally", "seriously", "definitely", "absolutely",
    "just", "so", "really", "very", "sort of", "kind of", "anyway",
    "meanwhile", "as I was saying", "in terms of", "in a sense",
    "more or less", "I guess", "I mean", "to be honest",
    "at the end of the day", "for example", "etcetera",
]

# --- Model Loading ---
model_path = 'models/grammar_error_detection' # Ensure this path is correct relative to where script runs
try:
    tokenizer_grammar = T5Tokenizer.from_pretrained(model_path)
    model_grammar = T5ForConditionalGeneration.from_pretrained(model_path)
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    model_grammar.to(device)
    print("Grammar Error Detection Model Loaded Successfully !!!")
except Exception as e:
    print(f"Error loading grammar model: {e}. Grammar checking will be impaired.")
    tokenizer_grammar = None
    model_grammar = None


# --- MongoDB Connection (USER REQUESTED FORMAT) ---
try:
    client = pymongo.MongoClient(os.environ.get("MONGO_DB_URI", "mongodb://localhost:27017/"))
    db = client['Elearning']
    flow_collection = db['flow']
    print("MongoDB connection successful.")
except Exception as e:
    print(f"MongoDB connection error: {e}")
    flow_collection = None # Important for graceful failure handling later in the script
# --- END OF MongoDB Connection ---


def do_correction(text):
    if not model_grammar or not tokenizer_grammar:
        print("Grammar model not loaded, skipping correction.")
        return text # Return original text if model isn't available

    input_text = f"rectify: {text}" # Ensure your T5 model is fine-tuned with this prefix
    try:
        inputs = tokenizer_grammar.encode(
            input_text,
            return_tensors='pt',
            max_length=256, # Consider if this is sufficient
            padding='max_length',
            truncation=True
        ).to(device)
        corrected_ids = model_grammar.generate(
            inputs,
            max_length=384, # Max length of the generated (corrected) sentence
            num_beams=5,    # Beam search for better quality
            early_stopping=True
        )
        corrected_sentence = tokenizer_grammar.decode(
            corrected_ids[0],
            skip_special_tokens=True
        )
        return corrected_sentence
    except Exception as e:
        print(f"Error during grammar correction for text '{text[:50]}...': {e}")
        return text # Return original text on error


def identifyPauseFillers(audio_path, silence_threshold=-30, min_silence_len=1000):
    try:
        audio_file = AudioSegment.from_file(audio_path) 
    except Exception as e:
        print(f"Error loading audio file {audio_path} with pydub: {e}")
        return 0.0, 0 

    total_duration_ms = len(audio_file)
    if total_duration_ms == 0:
        return 0.0, 0

    if audio_file.dBFS == float('-inf'): 
        print(f"Audio file {audio_path} is completely silent.")
        return 100.0, total_duration_ms

    try:
        chunks = split_on_silence(
            audio_file,
            min_silence_len=min_silence_len, 
            silence_thresh=silence_threshold, 
            keep_silence=100 
        )
    except Exception as e:
        print(f"Error in split_on_silence for {audio_path}: {e}")
        return 99.0, total_duration_ms 

    duration_with_speech = sum(len(chunk) for chunk in chunks)
    duration_of_silence = total_duration_ms - duration_with_speech
    pause_filler_percentage = (duration_of_silence / total_duration_ms) * 100 if total_duration_ms > 0 else 0
    return round(pause_filler_percentage, 2), total_duration_ms


def identifyFillerWords(audio_path):
    temp_wav_path = None 
    words_after_cleaning = []
    actual_filler_percentage = 0.0
    df_repetitive = pd.DataFrame(columns=['repetitive_word', 'word_count'])
    df_filler_identified = pd.DataFrame(columns=['filler_word', 'word_count'])

    try:
        temp_dir = os.path.join("data", "temp_dir")
        os.makedirs(temp_dir, exist_ok=True)
        temp_wav_filename = f"temp_{uuid.uuid4().hex}.wav"
        temp_wav_path = os.path.join(temp_dir, temp_wav_filename)

        audio_file = AudioSegment.from_file(audio_path) 
        audio_file.export(temp_wav_path, format="wav")
        text = convert_AudioToText(temp_wav_path)
    except Exception as e:
        print(f"Error during audio processing or STT in identifyFillerWords for {audio_path}: {e}")
        text = ""
    finally:
        if temp_wav_path and os.path.exists(temp_wav_path):
            try:
                os.remove(temp_wav_path)
            except Exception as e_rem:
                print(f"Error removing temp WAV file {temp_wav_path}: {e_rem}")

    if not text or not text.strip():
        return actual_filler_percentage, df_repetitive, df_filler_identified, 0

    text_cleaned = re.sub(r'[^\w\s]', '', text).lower() 
    text_cleaned = re.sub(r'\d+', '', text_cleaned)      
    text_cleaned = re.sub(r'\s+', ' ', text_cleaned).strip() 
    words_after_cleaning = [word for word in text_cleaned.split(" ") if word] 

    if not words_after_cleaning:
        return actual_filler_percentage, df_repetitive, df_filler_identified, 0

    identified_filler_count = 0
    identified_fillers_map = {} 

    for word in words_after_cleaning:
        if word in filler_words:
            identified_filler_count += 1
            identified_fillers_map[word] = identified_fillers_map.get(word, 0) + 1
    
    actual_filler_percentage = round((identified_filler_count / len(words_after_cleaning)) * 100, 2)

    if identified_fillers_map:
        df_filler_identified = pd.DataFrame(list(identified_fillers_map.items()), columns=['filler_word', 'word_count'])
        df_filler_identified = df_filler_identified.sort_values(by='word_count', ascending=False).reset_index(drop=True).head(10)

    word_counts = pd.Series(words_after_cleaning).value_counts()
    repetitive_words_map = {}
    repetition_threshold = 2 
    for word, count in word_counts.items():
        if count > repetition_threshold and word not in filler_words:
            repetitive_words_map[word] = count
    
    if repetitive_words_map:
        df_repetitive = pd.DataFrame(list(repetitive_words_map.items()), columns=['repetitive_word', 'word_count'])
        df_repetitive = df_repetitive.sort_values(by='word_count', ascending=False).reset_index(drop=True).head(10)

    return actual_filler_percentage, df_repetitive, df_filler_identified, len(words_after_cleaning)


def identifyGrammarErrors(audio_path):
    try:
        speech_text = end_to_end_audio_to_text(audio_path)
    except Exception as e:
        print(f"Error during STT in identifyGrammarErrors for {audio_path}: {e}")
        return "N/A", 100.0 

    if not speech_text or not speech_text.strip():
        return "0.00 %", 0.0 

    sentences = re.split(r'[.!?]+(?=\s|$)', speech_text)
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]

    if not sentences:
        return "0.00 %", 0.0

    try:
        corrected_sentences = [do_correction(sentence) for sentence in sentences]
    except Exception as e: 
        print(f"Error during batch grammar correction: {e}")
        return "N/A", 100.0
    
    vectorizer = TfidfVectorizer()
    try:
        vectorizer.fit(corrected_sentences + sentences)
        sentence_vectors = vectorizer.transform(sentences)
        corrected_sentence_vectors = vectorizer.transform(corrected_sentences)
    except ValueError as e: 
        print(f"TF-IDF Vectorizer error (e.g. empty vocabulary): {e}")
        return "0.00 %", 0.0 

    cosim_sims = []
    for i in range(len(sentences)):
        try:
            similarity_matrix = cosine_similarity(sentence_vectors[i], corrected_sentence_vectors[i])
            cosim_sims.append(similarity_matrix[0, 0])
        except Exception as e_sim: 
            print(f"Error calculating cosine similarity for sentence pair: {e_sim}")
            cosim_sims.append(0.0) 

    if not cosim_sims: 
        similarity = 1.0 
    else:
        similarity = np.mean(cosim_sims)
    
    distance = 1 - similarity 
    error_percentage_grammar = max(0, min(100, distance * 100))
    
    return f"{round(error_percentage_grammar, 2)} %", error_percentage_grammar


def identifyFillerWordsAndPauseFillers(audio_path, pause_silence_threshold=-30):
    pause_filler_percentage_val, total_audio_duration_ms = identifyPauseFillers(
        audio_path, silence_threshold=pause_silence_threshold
    )
    filler_percentage_val, df_repetitive, df_filler_identified, word_count = identifyFillerWords(audio_path)

    return {
        "filler_words_percentage": f"{filler_percentage_val} %",
        "pause_filler_percentage": f"{pause_filler_percentage_val} %",
        "repetitive_words": df_repetitive.to_dict(orient='records'),
        "filler_words": df_filler_identified.to_dict(orient='records') 
    }, filler_percentage_val, pause_filler_percentage_val, word_count, total_audio_duration_ms


def flowAnalyzerPipeline(audio_path,
                         user_id=None,
                         course_id=None,
                         student_email=None,
                         pause_detection_threshold=-30,
                         w_filler=1.0, w_pause=1.0, w_grammar=1.0,
                         empty_audio_fluency_score=0.0,
                         min_meaningful_duration_ms=2000): 
    
    filler_data_dict, raw_filler_percentage, raw_pause_percentage, actual_word_count, total_audio_duration_ms = \
        identifyFillerWordsAndPauseFillers(audio_path, pause_silence_threshold=pause_detection_threshold)
    
    grammar_error_str, error_percentage_grammar = identifyGrammarErrors(audio_path)

    is_effectively_empty = False
    if (raw_pause_percentage >= 98.0 and actual_word_count == 0) or \
       (actual_word_count == 0 and total_audio_duration_ms < min_meaningful_duration_ms) or \
       (total_audio_duration_ms == 0): 
        is_effectively_empty = True

    if is_effectively_empty:
        fluency_score = empty_audio_fluency_score
        calculated_total_error_percentage = 100.0 - fluency_score 
        print(f"Audio ({audio_path}) deemed effectively empty/short. Duration: {total_audio_duration_ms}ms, Words: {actual_word_count}, Pause: {raw_pause_percentage}%. Fluency: {fluency_score}%")
    else:
        weight_filler = max(0, w_filler)
        weight_pause = max(0, w_pause)
        weight_grammar = max(0, w_grammar)
        
        sum_of_weights = weight_filler + weight_pause + weight_grammar
        if sum_of_weights <= 0: 
            print("Warning: All fluency component weights are zero. Defaulting to simple average or 100% error.")
            if raw_filler_percentage > 0 or raw_pause_percentage > 0 or error_percentage_grammar > 0:
                 calculated_total_error_percentage = (raw_filler_percentage + raw_pause_percentage + error_percentage_grammar) / 3
            else:
                calculated_total_error_percentage = 0.0
        else: 
            weighted_sum_of_errors = (
                (raw_filler_percentage * weight_filler) +
                (raw_pause_percentage * weight_pause) +
                (error_percentage_grammar * weight_grammar)
            )
            calculated_total_error_percentage = weighted_sum_of_errors / sum_of_weights
        
        calculated_total_error_percentage = max(0, min(100, calculated_total_error_percentage)) 
        fluency_score = 100 - calculated_total_error_percentage
    
    fluency_score = round(fluency_score, 2)
    calculated_total_error_percentage = round(calculated_total_error_percentage, 2)

    response_payload = {
        "filler_words_and_pause_fillers": filler_data_dict,
        "grammar_errors": grammar_error_str,
        "fluency_score": f"{fluency_score} %"
    }

    if flow_collection is not None: 
        try:
            db_entry = response_payload.copy() 

            if user_id: db_entry['user_id'] = user_id
            if course_id: db_entry['course_id'] = course_id
            if student_email: db_entry['student_email'] = student_email
            
            db_entry['raw_filler_percentage'] = raw_filler_percentage
            db_entry['raw_pause_percentage'] = raw_pause_percentage
            db_entry['raw_grammar_error_percentage'] = error_percentage_grammar
            db_entry['actual_word_count'] = actual_word_count
            db_entry['total_audio_duration_ms'] = total_audio_duration_ms
            
            if not is_effectively_empty: 
                db_entry['weight_filler_used'] = w_filler 
                db_entry['weight_pause_used'] = w_pause
                db_entry['weight_grammar_used'] = w_grammar
            
            db_entry['calculated_total_error_percentage'] = calculated_total_error_percentage
            db_entry['is_effectively_empty'] = is_effectively_empty
            db_entry['analysis_timestamp'] = datetime.datetime.utcnow() 

            flow_collection.insert_one(db_entry)
            print(f"Successfully inserted flow analysis for {audio_path} (User: {user_id}) into MongoDB.")
        except Exception as e:
            print(f"Error inserting flow analysis data into MongoDB: {e}")
    else:
        print("MongoDB collection not available. Skipping database insert.")

    return response_payload