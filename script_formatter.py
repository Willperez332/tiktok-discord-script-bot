import yt_dlp
import os
import re

from deepgram import (
    AsyncDeepgramClient,
    PrerecordedOptions,
    FileSource,
)

def format_script_chunks(script: str) -> str:
    """Formats script into HOOK + backend chunks for ~8s pacing."""
    MAX_WORDS = 35
    sentences = re.split(r'(?<=[.?!])\s+', script.strip())
    if not sentences or not sentences[0]:
        return ""

    # Hook: ensure it’s not too short; append next sentence if needed
    hook = sentences[0]
    backend_sentences = sentences[1:]
    if len(hook.split()) < 15 and backend_sentences:
        hook += " " + backend_sentences[0]
        backend_sentences = backend_sentences[1:]

    backend_chunks = []
    current = []
    for s in backend_sentences:
        if not s.strip():
            continue
        if current and (len(" ".join(current).split()) + len(s.split()) > MAX_WORDS):
            backend_chunks.append(" ".join(current))
            current = [s]
        else:
            current.append(s)
    if current:
        backend_chunks.append(" ".join(current))

    # Format output
    out = f'**HOOK:**\nNO CAPTIONS ON SCREEN. Make the avatar say: "{hook.strip()}"\n\n'
    for i, chunk in enumerate(backend_chunks, start=1):
        if chunk.strip():
            out += f'**Backend {i}:**\nNO CAPTIONS ON SCREEN. Make the avatar say: "{chunk.strip()}"\n\n'
    return out

async def process_tiktok_url(url: str, deepgram_client: AsyncDeepgramClient) -> str:
    """
    Downloads audio via yt_dlp, sends to Deepgram v3 async prerecorded,
    extracts the main speaker paragraphs into a single clean transcript string.
    """
    final_audio_filename = "downloaded_audio.mp3"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": final_audio_filename.replace(".mp3", ""),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        # 1) Pull audio
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # yt-dlp often writes without .mp3 extension; normalize names
        candidate = final_audio_filename.replace(".mp3", "") + ".mp3"
        if os.path.exists(candidate):
            os.rename(candidate, final_audio_filename)

        if not os.path.exists(final_audio_filename):
            raise RuntimeError("Audio download failed.")

        # 2) Deepgram transcription
        with open(final_audio_filename, "rb") as f:
            buffer_data = f.read()

        payload: FileSource = {"buffer": buffer_data}
        options = PrerecordedOptions(
            model="nova-3",  # or "nova-2" if you prefer your previous model
            smart_format=True,
            diarize=True,
        )

        # v3 async prerecorded path
        response = await deepgram_client.listen.prerecorded.v("1").transcribe_file(
            payload, options
        )

        results = response.results
        if not results or not results.channels:
            raise RuntimeError("No speech detected.")

        # 3) Identify main speaker by total words
        paragraphs = results.channels[0].alternatives[0].paragraphs.paragraphs
        speaker_word_counts = {}
        for para in paragraphs:
            text = " ".join([s.text for s in para.sentences])
            speaker_word_counts[para.speaker] = speaker_word_counts.get(para.speaker, 0) + len(text.split())

        if not speaker_word_counts:
            raise RuntimeError("No speakers detected by diarization.")

        main_speaker = max(speaker_word_counts, key=speaker_word_counts.get)

        # 4) Build clean transcript for main speaker only
        parts = [
            " ".join([s.text for s in para.sentences])
            for para in paragraphs
            if para.speaker == main_speaker
        ]
        return " ".join(parts).strip()

    finally:
        if os.path.exists(final_audio_filename):
            try:
                os.remove(final_audio_filename)
            except Exception:
                pass