import json
import pymongo
import re, torch
import numpy as np
import pandas as pd
from pydub import AudioSegment
from transformers import (
                        T5Tokenizer,
                        T5ForConditionalGeneration
                        )
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from pydub.silence import split_on_silence
from src.data_conversion import * # Assuming convert_AudioToText and end_to_end_audio_to_text are here
import os

# --- (filler_words, model loading, MongoDB connection - same as before) ---
filler_words = [
                "um", "uh", "like", "you know", "well", "actually", "basically",
                "literally", "totally", "seriously", "definitely", "absolutely",
                "just", "so", "really", "very", "sort of", "kind of", "anyway",
                "meanwhile", "as I was saying", "in terms of", "in a sense",
                "more or less", "I guess", "I mean", "to be honest",
                "at the end of the day", "for example", "etcetera",
                ]

model_path = 'models/grammar_error_detection'
tokenizer_grammar = T5Tokenizer.from_pretrained(model_path)
model_grammar = T5ForConditionalGeneration.from_pretrained(model_path)
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
model_grammar.to(device)
print("Grammar Error Detection App Model Loaded Successfully !!!")
try:
    client = pymongo.MongoClient(os.environ.get("MONGO_DB_URI", "mongodb://localhost:27017/"))
    db = client['Elearning']
    flow_collection = db['flow']
    print("MongoDB connection successful.")
except Exception as e:
    print(f"MongoDB connection error: {e}")

def do_correction(text):
    input_text = f"rectify: {text}"
    inputs = tokenizer_grammar.encode(
                                    input_text,
                                    return_tensors='pt',
                                    max_length=256,
                                    padding='max_length',
                                    truncation=True
                                    ).to(device)
    corrected_ids = model_grammar.generate(
                                        inputs,
                                        max_length=384,
                                        num_beams=5,
                                        early_stopping=True
                                        )
    corrected_sentence = tokenizer_grammar.decode(
                                                corrected_ids[0],
                                                skip_special_tokens=True
                                                )
    return corrected_sentence

def identifyPauseFillers(
                        audio_path,
                        silence_threshold = -30,
                        min_silence_len = 1000
                        ):
    try:
        audio_file = AudioSegment.from_file(audio_path, format="mp3")
    except Exception as e:
        print(f"Error loading audio file {audio_path}: {e}")
        return 0.0, 0 # Return pause_percentage, total_duration

    total_duration_ms = len(audio_file)
    if total_duration_ms == 0:
        return 0.0, 0

    chunks = split_on_silence(
                            audio_file,
                            min_silence_len=min_silence_len,
                            silence_thresh=silence_threshold,
                            keep_silence=100
                            )
    duration_with_speech = sum(len(chunk) for chunk in chunks)
    duration_of_silence = total_duration_ms - duration_with_speech
    pause_filler_percentage = (duration_of_silence / total_duration_ms) * 100
    return round(pause_filler_percentage, 2), total_duration_ms

def identifyFillerWords(audio_path):
    # ... (rest of the function logic as before) ...
    # At the end of identifyFillerWords, before returning:
    # ... (after df_filler_non_repetitive calculation)
    word_count_after_cleaning = len(words) if 'words' in locals() and words else 0 # Get count of cleaned words
    # Ensure actual_filler_percentage is defined even if no words
    if word_count_after_cleaning == 0 :
        actual_filler_percentage = 0.0
    else:
        # Recalculate actual_filler_percentage if not done or to be sure
        current_filler_word_count = 0
        for word in words: # Assuming 'words' is the list of cleaned words
            if word in filler_words:
                current_filler_word_count +=1
        actual_filler_percentage = (current_filler_word_count / word_count_after_cleaning) * 100 if word_count_after_cleaning > 0 else 0.0
        actual_filler_percentage = round(actual_filler_percentage,2)


    return actual_filler_percentage, df_repetitive, df_filler_non_repetitive, word_count_after_cleaning
    # Make sure the rest of the function (STT, cleaning, df creation) handles empty cases gracefully
    # to get to this point. The version from previous response should mostly do this.
    # For brevity, I'm not pasting the whole identifyFillerWords again, just the return signature change.
    # Please refer to the previous full code for the body of identifyFillerWords.
    # The key is to reliably get `word_count_after_cleaning`.
    # Simplified version for demonstration of return:
    # ... (STT, cleaning, df creation)
    # if 'words' not in locals() or not words: # Ensure words list exists
    #     words = []
    #     actual_filler_percentage = 0.0
    # return actual_filler_percentage, df_repetitive, df_filler_non_repetitive, len(words)

# --- PASTE THE FULL identifyFillerWords FUNCTION FROM THE PREVIOUS RESPONSE HERE,
# --- THEN MODIFY ITS RETURN STATEMENT AS SHOWN ABOVE TO INCLUDE len(words) ---

# For now, let's use a placeholder for identifyFillerWords to show the structure.
# REPLACE THIS WITH THE ACTUAL FULL FUNCTION FROM PREVIOUS RESPONSE, MODIFIED.
def identifyFillerWords(audio_path):
    filler_word_count = 0
    temp_wav_path = "data/temp_dir/temp.wav"
    os.makedirs(os.path.dirname(temp_wav_path), exist_ok=True)
    words_list = [] # To store words after STT and cleaning

    try:
        audio_file = AudioSegment.from_file(audio_path, format="mp3")
        audio_file.export(temp_wav_path, format="wav")
        text = convert_AudioToText(temp_wav_path)
    except Exception as e:
        print(f"Error during audio processing or STT in identifyFillerWords: {e}")
        text = "" # Ensure text is defined
    finally:
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)

    if not text:
        actual_filler_percentage = 0.0
        df_repetitive = pd.DataFrame(columns=['repetitive_word', 'word_count'])
        df_filler_non_repetitive = pd.DataFrame(columns=['filler_word', 'word_count'])
        return actual_filler_percentage, df_repetitive, df_filler_non_repetitive, 0 # 0 words

    text_cleaned = re.sub(r'[^\w\s]', '', text)
    text_cleaned = re.sub(r'[0-9]', '', text_cleaned)
    text_cleaned = re.sub(r' +', ' ', text_cleaned).lower().strip()
    words_list = text_cleaned.split(" ")
    words_list = [w for w in words_list if w]

    if not words_list:
        actual_filler_percentage = 0.0
        df_repetitive = pd.DataFrame(columns=['repetitive_word', 'word_count'])
        df_filler_non_repetitive = pd.DataFrame(columns=['filler_word', 'word_count'])
        return actual_filler_percentage, df_repetitive, df_filler_non_repetitive, 0

    for word in words_list:
        if word in filler_words:
            filler_word_count += 1

    actual_filler_percentage = (filler_word_count / len(words_list)) * 100
    actual_filler_percentage = round(actual_filler_percentage, 2)

    # ... (rest of df_repetitive, df_filler_non_repetitive creation logic from previous full code)
    # For brevity, assuming they are created.
    filler_word_dict = {} # Placeholder
    repetitive_word_dict = {} # Placeholder
    # This part needs the full logic for creating df_repetitive and df_filler_non_repetitive
    # from the previous response.
    # Example:
    data_dict_repetitive = {'repetitive_word': [], 'word_count': []} # ... populate ...
    df_repetitive = pd.DataFrame(data_dict_repetitive)
    if not df_repetitive.empty:
        df_repetitive = df_repetitive.sort_values(by=['word_count'], ascending=False).reset_index(drop=True).head(10)
    else:
        df_repetitive = pd.DataFrame(columns=['repetitive_word', 'word_count'])

    df_filler_non_repetitive = pd.DataFrame(filler_word_dict.items(), columns=['filler_word', 'word_count'])
    if not df_filler_non_repetitive.empty: # ... filter and sort ...
        df_filler_non_repetitive = df_filler_non_repetitive.sort_values(by=['word_count'], ascending=False).reset_index(drop=True).head(10)
    else:
        df_filler_non_repetitive = pd.DataFrame(columns=['filler_word', 'word_count'])
    # END OF PLACEHOLDER SECTION FOR DF CREATION

    return actual_filler_percentage, df_repetitive, df_filler_non_repetitive, len(words_list)


def identifyGrammarErrors(audio_path):
    # ... (same as before) ...
    try:
        speech_text = end_to_end_audio_to_text(audio_path)
    except Exception as e:
        print(f"Error during STT in identifyGrammarErrors: {e}")
        return "N/A", 100.0
    if not speech_text: return "0.00 %", 0.0
    sentences = re.split(r'[.!?]+', speech_text)
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    if not sentences: return "0.00 %", 0.0
    try:
        corrected_sentences = [do_correction(sentence) for sentence in sentences]
    except Exception as e:
        print(f"Error during grammar correction: {e}")
        return "N/A", 100.0
    vectorizer = TfidfVectorizer()
    try:
        vectorizer.fit(corrected_sentences + sentences)
        sentence_vectors = vectorizer.transform(sentences)
        corrected_sentence_vectors = vectorizer.transform(corrected_sentences)
    except ValueError: return "0.00 %", 0.0
    cosim_sims = []
    for i in range(len(sentences)):
        try:
            similarity_matrix = cosine_similarity(sentence_vectors[i], corrected_sentence_vectors[i])
            cosim_sims.append(similarity_matrix[0, 0])
        except: cosim_sims.append(0.0)
    if not cosim_sims: similarity = 1.0
    else: similarity = np.mean(cosim_sims)
    distance = 1 - similarity
    error_percentage_grammar = max(0, min(100, distance * 100))
    return f"{round(error_percentage_grammar, 2)} %", error_percentage_grammar


def identifyFillerWordsAndPauseFillers(audio_path, pause_silence_threshold=-30):
    pause_filler_percentage_val, total_audio_duration_ms = identifyPauseFillers(audio_path, silence_threshold=pause_silence_threshold)
    filler_percentage_val, df_repetitive, df_filler_non_repetitive_val, word_count = identifyFillerWords(audio_path)

    return {
            "filler_words_percentage": f"{filler_percentage_val} %",
            "pause_filler_percentage": f"{pause_filler_percentage_val} %",
            "repetitive_words": df_repetitive.to_dict(orient='records'),
            "filler_words": df_filler_non_repetitive_val.to_dict(orient='records')
            }, filler_percentage_val, pause_filler_percentage_val, word_count, total_audio_duration_ms

def flowAnalyzerPipeline(audio_path, pause_detection_threshold=-30,
                         w_filler=1.0, w_pause=1.0, w_grammar=1.0,
                         empty_audio_fluency_score=0.0,
                         min_meaningful_duration_ms=2000): # Min duration in ms to be considered not empty
    temp_json_path = "data/temp_dir/temp.json"
    os.makedirs(os.path.dirname(temp_json_path), exist_ok=True)

    filler_data_dict, raw_filler_percentage, raw_pause_percentage, actual_word_count, total_audio_duration_ms = \
        identifyFillerWordsAndPauseFillers(audio_path, pause_silence_threshold=pause_detection_threshold)
    
    grammar_error_str, error_percentage_grammar = identifyGrammarErrors(audio_path)

    is_effectively_empty = False
    # Condition for empty: high pause, no words, AND audio duration is very short (or no words regardless of duration)
    if (raw_pause_percentage >= 98.0 and actual_word_count == 0) or \
       (actual_word_count == 0 and total_audio_duration_ms < min_meaningful_duration_ms) or \
       (total_audio_duration_ms == 0): # Explicitly handle 0 duration audio
        is_effectively_empty = True

    if is_effectively_empty:
        fluency_score = empty_audio_fluency_score
        total_error_percentage = 100.0 - fluency_score
        print(f"Detected effectively empty/short audio (duration: {total_audio_duration_ms}ms, words: {actual_word_count}, pause: {raw_pause_percentage}%). Assigning fluency score: {fluency_score}%")
    else:
        weight_filler = w_filler
        weight_pause = w_pause
        weight_grammar = w_grammar
        sum_of_weights = weight_filler + weight_pause + weight_grammar
        if sum_of_weights == 0: sum_of_weights = 1 
        weighted_sum_of_errors = (
            (raw_filler_percentage * weight_filler) +
            (raw_pause_percentage * weight_pause) +
            (error_percentage_grammar * weight_grammar)
        )
        total_error_percentage = weighted_sum_of_errors / sum_of_weights
        total_error_percentage = max(0, min(100, total_error_percentage))
        fluency_score = 100 - total_error_percentage
    
    fluency_score = round(fluency_score, 2)

    response = { # ... same as before ...
            "filler_words_and_pause_fillers": filler_data_dict,
            "grammar_errors": grammar_error_str,
            "fluency_score": f"{fluency_score} %"
            }
    try: # ... DB saving with 'is_effectively_empty' flag ...
        with open(temp_json_path, "w") as file: json.dump(response, file, indent=4)
    except Exception as e: print(f"Error writing/reading temp JSON: {e}")
    try:
        db_entry = response.copy()
        db_entry['raw_filler_percentage'] = raw_filler_percentage
        db_entry['raw_pause_percentage'] = raw_pause_percentage
        db_entry['raw_grammar_error_percentage'] = error_percentage_grammar
        db_entry['actual_word_count'] = actual_word_count
        db_entry['total_audio_duration_ms'] = total_audio_duration_ms
        if not is_effectively_empty:
            db_entry['weight_filler'] = weight_filler
            db_entry['weight_pause'] = weight_pause
            db_entry['weight_grammar'] = weight_grammar
        db_entry['calculated_total_error_percentage'] = total_error_percentage
        db_entry['is_effectively_empty'] = is_effectively_empty
        flow_collection.insert_one(db_entry)
        print("Successfully inserted data into MongoDB.")
    except Exception as e: print(f"Error inserting data into MongoDB: {e}")
    return response