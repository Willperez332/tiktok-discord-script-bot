import yt_dlp
import assemblyai as aai
import os
import re

# This is the final, balanced formatting function
def format_script_chunks(script: str):
    # Configuration
    WORDS_PER_SECOND = 2.5
    SECONDS_PER_CLIP = 8
    words_per_chunk = int(WORDS_PER_SECOND * SECONDS_PER_CLIP) # Approx. 20 words

    # --- Step 1: Split by full sentences to respect natural pauses ---
    sentences = re.split(r'(?<=[.?!])\s+', script)

    if not sentences:
        return "**HOOK:**\n\n**Backend 1:**\n"

    # --- Step 2: Define the Hook ---
    # The hook is still generally the first one or two sentences.
    hook = sentences[0]
    backend_sentences = sentences[1:]
    
    # If the first sentence is very short, grab the next one for the hook too.
    if len(hook.split()) < 12 and len(backend_sentences) > 0:
        hook += " " + backend_sentences[0]
        backend_sentences = backend_sentences[1:]
    
    # --- Step 3: Intelligently Group Sentences into Backend Chunks ---
    backend_chunks = []
    current_chunk_sentences = []
    
    for sentence in backend_sentences:
        if not sentence.strip(): continue
        
        # Add the next sentence to our current group
        current_chunk_sentences.append(sentence)
        
        # Check if the current group of sentences has reached our target length
        current_chunk_text = " ".join(current_chunk_sentences)
        if len(current_chunk_text.split()) >= words_per_chunk:
            # If it's long enough, finalize this chunk
            backend_chunks.append(current_chunk_text)
            # and reset for the next chunk
            current_chunk_sentences = []
    
    # After the loop, if there are any leftover sentences, make them the final chunk.
    if current_chunk_sentences:
        backend_chunks.append(" ".join(current_chunk_sentences))

    # --- Step 4: Assemble the Final Output ---
    final_output = f"**HOOK:**\n{hook.strip()}\n\n"
    for i, chunk in enumerate(backend_chunks):
        if chunk.strip():
            final_output += f"**Backend {i + 1}:**\n{chunk.strip()}\n\n"

    return final_output

async def process_tiktok_url(url: str):
    # We will use a fixed, predictable filename for the final audio.
    final_audio_filename = "downloaded_audio.mp3"

    # These settings will download the audio and force the final, converted file
    # to be named exactly as we specified above.
    ydl_opts = {
        'format': 'bestaudio/best',
        # Set the final output template. The postprocessor will ensure it becomes an .mp3
        'outtmpl': final_audio_filename.replace('.mp3', ''),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
        'quiet': True,
    }

    try:
        # --- Step 1: Download and Convert the Audio ---
        print(f"Starting download and conversion for URL: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Audio file created: {final_audio_filename}")
        
        # --- Step 2: Transcribe the Known File ---
        transcriber = aai.Transcriber()
        config = aai.TranscriptionConfig(speaker_labels=True, profanity_filtering=False)

        print("Starting transcription...")
        # We know the exact filename, so we can use it directly.
        transcript = transcriber.transcribe(final_audio_filename, config)

        if transcript.status == aai.TranscriptStatus.error:
            raise Exception(f"Transcription failed: {transcript.error}")
        
        print("Transcription finished.")

        # --- Step 3: Isolate the Main Speaker ---
        if not transcript.utterances:
            raise Exception("No speech was detected in the audio.")

        speaker_word_counts = {}
        for utterance in transcript.utterances:
            speaker = utterance.speaker
            word_count = len(utterance.text.split())
            speaker_word_counts[speaker] = speaker_word_counts.get(speaker, 0) + word_count
        
        main_speaker = max(speaker_word_counts, key=speaker_word_counts.get)
        print(f"Identified main speaker: {main_speaker}")

        # --- Step 4: Combine Their Text ---
        creator_script_parts = [utt.text for utt in transcript.utterances if utt.speaker == main_speaker]
        clean_transcript = " ".join(creator_script_parts)

        return clean_transcript

    finally:
        # --- Step 5: Clean Up ---
        # Always delete the file if it exists.
        if os.path.exists(final_audio_filename):
            os.remove(final_audio_filename)
            print(f"Cleaned up temporary audio file: {final_audio_filename}")