import yt_dlp
import os
import re
from deepgram import DeepgramClient, PrerecordedOptions, FileSource

# This is the final, smarter formatting function (no changes needed here)
def format_script_chunks(script: str):
    TARGET_WORDS = 27
    MAX_WORDS = 35
    sentences = re.split(r'(?<=[.?!])\s+', script)
    if not sentences: return ""

    hook = sentences[0]
    backend_sentences = sentences[1:]
    if len(hook.split()) < 15 and len(backend_sentences) > 0:
        hook += " " + backend_sentences[0]
        backend_sentences = backend_sentences[1:]
    
    backend_chunks = []
    current_chunk_sentences = []
    for sentence in backend_sentences:
        if not sentence.strip(): continue
        current_chunk_word_count = len(" ".join(current_chunk_sentences).split())
        sentence_word_count = len(sentence.split())
        if current_chunk_sentences and (current_chunk_word_count + sentence_word_count > MAX_WORDS):
            backend_chunks.append(" ".join(current_chunk_sentences))
            current_chunk_sentences = [sentence]
        else:
            current_chunk_sentences.append(sentence)
    if current_chunk_sentences:
        backend_chunks.append(" ".join(current_chunk_sentences))

    # --- THIS IS THE ONLY PART THAT CHANGES ---
    # We now add the prefix to the hook and each backend chunk.
    
    # Format the hook
    final_output = f"**HOOK:**\nNO CAPTIONS ON SCREEN. [Avatar says] {hook.strip()}\n\n"
    
    # Format the backends
    for i, chunk in enumerate(backend_chunks):
        if chunk.strip():
            final_output += f"**Backend {i + 1}:**\nNO CAPTIONS ON SCREEN. [Avatar says] {chunk.strip()}\n\n"

    return final_output

# --- THE CORRECTED DEEPGRAM LOGIC ---
async def process_tiktok_url(url: str, deepgram_client: DeepgramClient):
    final_audio_filename = "downloaded_audio.mp3"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': final_audio_filename.replace('.mp3', ''),
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
        'quiet': True,
    }

    try:
        print(f"Starting download for URL: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Audio file created: {final_audio_filename}")
        
        with open(final_audio_filename, "rb") as audio_file:
            buffer_data = audio_file.read()

        payload: FileSource = {"buffer": buffer_data}

        options = PrerecordedOptions(model="nova-2", smart_format=True, diarize=True)
        print("Starting transcription with Deepgram...")
        response = await deepgram_client.listen.asyncprerecorded.v("1").transcribe_file(payload, options)
        
        # --- Step 3: Isolate the Main Speaker (Corrected Logic) ---
        paragraphs = response.results.channels[0].alternatives[0].paragraphs.paragraphs
        
        speaker_word_counts = {}
        for para in paragraphs:
            speaker = para.speaker
            # THE FIX IS HERE: We get the text by joining the sentences inside the paragraph.
            paragraph_text = " ".join([sentence.text for sentence in para.sentences])
            word_count = len(paragraph_text.split())
            speaker_word_counts[speaker] = speaker_word_counts.get(speaker, 0) + word_count
        
        if not speaker_word_counts:
            raise Exception("No speech was detected by Deepgram.")
            
        main_speaker_id = max(speaker_word_counts, key=speaker_word_counts.get)
        print(f"Identified main speaker: {main_speaker_id}")

        # --- Step 4: Combine the main speaker's text (Corrected Logic) ---
        # AND THE FIX IS HERE: We do the same thing to get the final script.
        creator_script_parts = [
            " ".join([sentence.text for sentence in para.sentences]) 
            for para in paragraphs if para.speaker == main_speaker_id
        ]
        clean_transcript = " ".join(creator_script_parts)

        print("Transcription finished.")
        return clean_transcript

    finally:
        if os.path.exists(final_audio_filename):
            os.remove(final_audio_filename)
            print(f"Cleaned up temporary audio file.")