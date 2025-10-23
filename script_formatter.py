import os
import re
import asyncio
import yt_dlp
from typing import Any, Dict

from deepgram import DeepgramClient, PrerecordedOptions, FileSource


def format_script_chunks(script: str) -> str:
    MAX_WORDS = 35
    sentences = re.split(r'(?<=[.?!])\s+', script.strip())
    if not sentences or not sentences[0]:
        return ""

    hook = sentences[0]
    backend_sentences = sentences[1:]
    if len(hook.split()) < 15 and backend_sentences:
        hook += " " + backend_sentences[0]
        backend_sentences = backend_sentences[1:]

    backend_chunks, current = [], []
    for s in backend_sentences:
        s = s.strip()
        if not s:
            continue
        if current and (len(" ".join(current).split()) + len(s.split()) > MAX_WORDS):
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
    base = out_mp3.replace(".mp3", "")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": base,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    candidate = base + ".mp3"
    if os.path.exists(candidate) and candidate != out_mp3:
        os.replace(candidate, out_mp3)


def _transcribe_sync(audio_bytes: bytes, client: DeepgramClient) -> Any:
    payload: FileSource = {"buffer": audio_bytes}
    options = PrerecordedOptions(
        model="nova-3",
        smart_format=True,
        diarize=True,
    )
    # Works on v3 and v4 clients
    return client.listen.prerecorded.v("1").transcribe_file(payload, options)


def _dg_to_dict(resp: Any) -> Dict:
    """
    Normalize Deepgram SDK responses (object or dict) into a plain dict.
    """
    if isinstance(resp, dict):
        return resp
    # v3/v4 typed objects usually have to_dict()/to_json()
    for method in ("to_dict", "toJson", "to_json"):
        m = getattr(resp, method, None)
        if callable(m):
            out = m()
            # to_json may return a string
            if isinstance(out, str):
                import json
                return json.loads(out)
            return out
    # last resort: duck-type via __dict__
    if hasattr(resp, "__dict__"):
        return resp.__dict__
    raise TypeError(f"Unsupported Deepgram response type: {type(resp)}")


async def process_tiktok_url(url: str, deepgram_client: DeepgramClient) -> str:
    final_audio_filename = "downloaded_audio.mp3"
    try:
        # 1) Download in a thread
        await asyncio.to_thread(_download_audio_sync, url, final_audio_filename)
        if not os.path.exists(final_audio_filename):
            raise RuntimeError("Audio download failed.")

        # 2) Read bytes
        with open(final_audio_filename, "rb") as f:
            audio_bytes = f.read()

        # 3) Transcribe in a thread
        raw_resp = await asyncio.to_thread(_transcribe_sync, audio_bytes, deepgram_client)

        # 4) Normalize to dict regardless of SDK flavor
        dg = _dg_to_dict(raw_resp)

        # 5) Parse safely
        results = dg.get("results")
        if not results:
            # Some SDKs put it under data/results
            results = dg.get("data", {}).get("results")
        if not results:
            raise RuntimeError("No results from Deepgram.")

        channels = results.get("channels") or []
        if not channels:
            raise RuntimeError("No channels in Deepgram results.")

        alt = channels[0].get("alternatives", [{}])[0]
        # paragraphs may be absent depending on model/options
        paragraphs = alt.get("paragraphs", {}).get("paragraphs", [])
        transcript = (alt.get("transcript") or "").strip()

        if not paragraphs:
            # Fallback: just use full transcript
            return transcript

        # Count words per speaker
        speaker_wc = {}
        for para in paragraphs:
            sentences = para.get("sentences", [])
            text = " ".join([s.get("text", "") for s in sentences])
            spk = para.get("speaker", "spk")
            speaker_wc[spk] = speaker_wc.get(spk, 0) + len(text.split())

        if not speaker_wc:
            return transcript

        main = max(speaker_wc, key=speaker_wc.get)
        parts = [
            " ".join([s.get("text", "") for s in para.get("sentences", [])])
            for para in paragraphs
            if para.get("speaker") == main
        ]
        cleaned = " ".join(parts).strip()
        return cleaned or transcript

    finally:
        try:
            if os.path.exists(final_audio_filename):
                os.remove(final_audio_filename)
        except Exception:
            pass
