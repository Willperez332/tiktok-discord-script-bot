import yt_dlp
import os
import re

# These are the correct imports for deepgram-sdk v3+
from deepgram import (
    AsyncDeepgramClient,
    PrerecordedOptions,
    FileSource,
)

def format_script_chunks(script: str):
    """Formats a script into a HOOK and backend chunks."""
    MAX_WORDS = 35
    sentences = re.split(r'(?<=[.?!])\s+', script.strip())
    if not sentences or not sentences[0]: return ""

    hook = sentences.pop(0)
    if len(hook.split()) < 15 and sentences:
        hook += " " + sentences.pop(0)
    
    backend_chunks = []
    current_chunk_sentences = []
    for sentence in sentences:
        if not sentence.strip(): continue
        
        current_chunk_word_count = len(" ".join(current_chunk_sentences).split())
        if current_chunk_sentences and (current_chunk_word_count + len(sentence.split()) > MAX_WORDS):
            backend_chunks.append(" ".join(current_chunk_sentences))
            current_chunk_sentences = [sentence]
        else:
            current_chunk_sentences.append(sentence)
            
    if current_chunk_sentences:
        backend_chunks.append(" ".join(current_chunk_sentences))

    final_output = f'**HOOK:**\nNO CAPTIONS ON SCREEN. Make the avatar say: "{hook.strip()}"\n\n'
    for i, chunk in enumerate(backend_chunks):
        if chunk.strip():
            final_output += f'**Backend {i + 1}:**\nNO CAPTIONS ON SCREEN. Make the avatar say: "{chunk.strip()}"\n\n'

    return final_output

# The function signature now correctly expects an AsyncDeepgramClient
async def process_tiktok_url(url: str, deepgram_client: AsyncDeepgramClient):
    """Downloads audio, transcribes it, and returns the main speaker's script."""
    final_audio_filename = "downloaded_audio.mp3"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': final_audio_filename.replace('.mp3', ''),
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
        'quiet': True, 'no_warnings': True,
    }

    try:
        print(f"Starting download for URL: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Audio file created: {final_audio_filename}")

        with open(final_audio_filename, "rb") as audio_file:
            buffer_.data = audio_file.read()

        payload: FileSource = {"buffer": buffer_data}
        options = PrerecordedOptions(model="nova-2", smart_format=True, diarize=True)
        
        print("Starting transcription with Deepgram v3 Async Client...")
        # This is the correct API call for the v3 Async client
        response = await deepgram_client.listen.prerecorded.v("1").transcribe_file(payload, options)
        
        results = response.results
        if not results or not results.channels:
            raise Exception("No speech was detected in the audio.")

        # This is the correct way to parse the v3 response object
        paragraphs = results.channels[0].alternatives[0].paragraphs.paragraphs
        
        speaker_word_counts = {}
        for para in paragraphs:
            speaker = para.speaker
            paragraph_text = " ".join([sentence.text for sentence in para.sentences])
            word_count = len(paragraph_text.split())
            speaker_word_counts[speaker] = speaker_word_counts.get(speaker, 0) + word_count
        
        if not speaker_word_counts:
            raise Exception("Deepgram did not detect any speakers.")
            
        main_speaker_id = max(speaker_word_counts, key=speaker_word_counts.get)
        print(f"Identified main speaker: {main_speaker_id}")

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