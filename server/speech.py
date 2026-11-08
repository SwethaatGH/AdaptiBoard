"""
speech.py - text-to-speech and speech-to-text.

TTS: Microsoft Edge neural voices through the free `edge-tts` package (natural, accurate
pronunciation, needs internet). Audio is cached on disk, so a word is only fetched once.
If it fails, the board falls back to the browser's built-in voice.

STT (server side, optional - the board can also use Chrome's built-in recognition):
    STT_PROVIDER=auto|local|groq|openai|off
      local  -> faster-whisper running on this laptop (pip install faster-whisper)
      groq   -> GROQ_API_KEY,  whisper-large-v3-turbo (free tier)
      openai -> OPENAI_API_KEY, gpt-4o-mini-transcribe
    STT_MODEL  overrides the model (local default: base.en)
"""
import asyncio
import hashlib
import os
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parent / "data"
TTS_DIR = DATA / "tts"

VOICES = [
    ("en-US-AriaNeural", "Aria (US, female)"),
    ("en-US-JennyNeural", "Jenny (US, female)"),
    ("en-US-GuyNeural", "Guy (US, male)"),
    ("en-US-AndrewNeural", "Andrew (US, male)"),
    ("en-US-AnaNeural", "Ana (US, child)"),
    ("en-GB-SoniaNeural", "Sonia (UK, female)"),
    ("en-GB-RyanNeural", "Ryan (UK, male)"),
    ("en-IN-NeerjaNeural", "Neerja (India, female)"),
    ("en-IN-PrabhatNeural", "Prabhat (India, male)"),
    ("en-AU-NatashaNeural", "Natasha (Australia, female)"),
]
DEFAULT_VOICE = "en-US-AriaNeural"

try:
    import edge_tts  # noqa: F401
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False


async def tts(text: str, voice: str = DEFAULT_VOICE, rate: str = "+0%") -> bytes | None:
    if not TTS_AVAILABLE or not text.strip():
        return None
    import edge_tts

    if voice not in {v for v, _ in VOICES}:
        voice = DEFAULT_VOICE
    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode()).hexdigest()
    path = TTS_DIR / f"{key}.mp3"
    if path.exists():
        return path.read_bytes()
    audio = bytearray()
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate)
        async with asyncio.timeout(8) if hasattr(asyncio, "timeout") else _nullctx():
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
    except Exception as e:
        print(f"[tts] failed: {e}")
        return None
    if not audio:
        return None
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(audio))
    return bytes(audio)


class _nullctx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


# ---------------------------------------------------------------- speech to text
_whisper = None
# Whisper "hears" these in silence or noise - ignore them.
HALLUCINATIONS = {"thank you", "thanks for watching", "you", "bye", "thank you.",
                  "thanks for watching!", "please subscribe", ".", "okay", "so"}


def stt_provider():
    p = os.getenv("STT_PROVIDER", "auto").lower()
    if p != "auto":
        return None if p == "off" else p
    try:
        import faster_whisper  # noqa: F401
        return "local"
    except ImportError:
        pass
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return None


def _local_transcribe(audio: bytes) -> str:
    global _whisper
    import io

    from faster_whisper import WhisperModel

    if _whisper is None:
        name = os.getenv("STT_MODEL", "base.en")
        print(f"[stt] loading faster-whisper '{name}' (first time downloads the model)...")
        _whisper = WhisperModel(name, device="cpu", compute_type="int8")
    segments, _ = _whisper.transcribe(io.BytesIO(audio), vad_filter=True, beam_size=1,
                                      language="en")
    return " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6)


async def transcribe(audio: bytes, mime: str = "audio/webm") -> str:
    p = stt_provider()
    if not p:
        raise RuntimeError("no speech-to-text configured on the server")
    if p == "local":
        text = await asyncio.to_thread(_local_transcribe, audio)
    else:
        url, key, model = {
            "groq": ("https://api.groq.com/openai/v1/audio/transcriptions",
                     os.getenv("GROQ_API_KEY"), os.getenv("STT_MODEL", "whisper-large-v3-turbo")),
            "openai": ("https://api.openai.com/v1/audio/transcriptions",
                       os.getenv("OPENAI_API_KEY"), os.getenv("STT_MODEL", "gpt-4o-mini-transcribe")),
        }[p]
        mime = mime.split(";")[0].strip() or "audio/webm"  # drop ";codecs=opus"
        ext = "webm" if "webm" in mime else "ogg" if "ogg" in mime else "mp4" if "mp4" in mime else "wav"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, headers={"Authorization": f"Bearer {key}"},
                                  data={"model": model, "language": "en", "response_format": "json"},
                                  files={"file": (f"chunk.{ext}", audio, mime)})
            r.raise_for_status()
            text = r.json().get("text", "")
    text = text.strip()
    if text.lower().strip(" .!") in {h.strip(" .!") for h in HALLUCINATIONS}:
        return ""
    return text
