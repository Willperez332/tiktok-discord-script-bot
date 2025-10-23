import os
import re
import asyncio
import yt_dlp

# Deepgram: support environments where only DeepgramClient exists
from deepgram import DeepgramClient, PrerecordedOptions, FileSource


def format_script_chunks(script: str) -> str:
    """Formats script into HOOK + ~8s backend chunks, Veo 3 style."""
    MAX_WORDS = 35
    sentences = re.split(r'(?<=[.?!])\s+', script.strip())
    if not sentences or not sentences[0]:
        return ""

    # Hook: ensure it's not too short; append next sentence if needed
    hook = sentences[0]
    backend_sentences = sentences[1:]
    if len(hook.split()) < 15 and backend_sentences:
        hook += " " + backend_sentences[0]
        backend_sentences = backend_sentences[1:]

    backend_chunks = []
    current = []
    for s in backend_sentences:
        s = s.strip()
        if not s:
            continue
        next_len = len(" ".join(current).split()) + len(s.split())
        if current and next_len > MAX_WORDS:
            backend_chunks.append(" ".join(current))
            current = [s]
        else:
            current.append(s)
    if current:
        backend_chunks.append(" ".join(current))

    out = f'**HOOK:**\nNO CAPTIONS ON SCREEN. Make the avatar say: "{hook.strip()}"\n\n'
    for i, chunk in enumerate(backend_chunks, start=1):
        if chunk.strip():
            out += f'**Backend {i}:**\nNO CAPTIONS ON SCREEN. Make the avatar say: "{chunk.strip()}"\n\n'
    return out


def _download_audio_sync(url: str, out_mp3: str) -> None:
    """Blocking: download audio to MP3 using yt_dlp."""
    tmp_base = out_mp3.replace(".mp3", "")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": tmp_base,  # yt_dlp will append extension
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # normalize final filename to out_mp3
    candidate = tmp_base + ".mp3"
    if os.path.exists(candidate) and candidate != out_mp3:
        os.replace(candidate, out_mp3)


def _transcribe_sync(audio_bytes: bytes, client: DeepgramClient) -> dict:
    """Blocking: call Deepgram prerecorded (works on v3 and v4)."""
    payload: FileSource = {"buffer": audio_bytes}
    options = PrerecordedOptions(
        model="nova-3",
        smart_format=True,
        diarize=True,
    )
    # v3 and v4 both support this path:
    #   client.listen.prerecorded.v("1").transcribe_file(...)
    # (In v4 it's routed via REST; in v3 it’s the classic client)
    return client.listen.prerecorded.v("1").transcribe_file(payload, options)


async def process_tiktok_url(url: str, deepgram_client: DeepgramClient) -> str:
    """
    Async wrapper:
    - yt_dlp download runs in a thread,
    - Deepgram call runs in a thread,
    - extracts main speaker transcript.
    """
    final_audio_filename = "downloaded_audio.mp3"
    try:
        # 1) Download audio (thread)
        await asyncio.to_thread(_download_audio_sync, url, final_audio_filename)
        if not os.path.exists(final_audio_filename):
            raise RuntimeError("Audio download failed.")

        # 2) Read bytes
        with open(final_audio_filename, "rb") as f:
            audio_bytes = f.read()

        # 3) Transcribe (thread)
        response = await asyncio.to_thread(_transcribe_sync, audio_bytes, deepgram_client)

        results = response.get("results")
        if not results:
            raise RuntimeError("No results from Deepgram.")

        channels = results.get("channels", [])
        if not channels:
            raise RuntimeError("No channels in Deepgram results.")

        alt = channels[0]["alternatives"][0]
        paragraphs = alt.get("paragraphs", {}).get("paragraphs", [])
        if not paragraphs:
            # fallback: join words if paragraphs absent
            transcript = alt.get("transcript", "")
            return transcript.strip()

        # find main speaker by longest word count
        speaker_word_counts = {}
        for para in paragraphs:
            text = " ".join([s["text"] for s in para.get("sentences", [])])
            spk = para.get("speaker", "spk")
            speaker_word_counts[spk] = speaker_word_counts.get(spk, 0) + len(text.split())

        if not speaker_word_counts:
            # fallback to full alt transcript
            return alt.get("transcript", "").strip()

        main_speaker = max(speaker_word_counts, key=speaker_word_counts.get)
        parts = [
            " ".join([s["text"] for s in para.get("sentences", [])])
            for para in paragraphs
            if para.get("speaker") == main_speaker
        ]
        return " ".join(parts).strip()

    finally:
        try:
            if os.path.exists(final_audio_filename):
                os.remove(final_audio_filename)
        except Exception:
            pass
