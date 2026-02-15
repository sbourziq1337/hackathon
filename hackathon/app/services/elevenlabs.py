"""
Speech services — STT and TTS with automatic fallbacks.

Primary:  ElevenLabs (STT + TTS with streaming)
Fallback: Groq Whisper (STT) / Edge-TTS (TTS) / Browser Web Speech API (TTS)

Chain:
  STT: ElevenLabs → Groq Whisper
  TTS: ElevenLabs (streaming) → Edge-TTS (Microsoft, free) → Browser Web Speech API

Optimized for low-latency web calls:
  - Uses ElevenLabs flash models (fastest available)
  - Streaming TTS endpoint returns audio as it's generated
  - Non-streaming endpoint returns full audio for Telegram/compatibility
"""

from __future__ import annotations

import io
import logging
from typing import AsyncGenerator

import edge_tts
import httpx

from app.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_STT_URL,
    ELEVENLABS_TTS_URL,
    ELEVENLABS_VOICE_ID,
    GROQ_API_KEY,
)

logger = logging.getLogger(__name__)

# Track whether ElevenLabs is available (skip retries after first block)
_elevenlabs_blocked = False

# Edge-TTS voice — calm, natural female voice (matches emergency operator tone)
EDGE_TTS_VOICE = "en-US-JennyNeural"

# ── ElevenLabs Model Selection ────────────────────────────────
# Flash models are 2-3x faster than turbo (critical for real-time web calls)
# Fallback chain: flash → turbo → base
ELEVENLABS_TTS_MODEL = "eleven_flash_v2_5"
ELEVENLABS_TTS_MODEL_FALLBACK = "eleven_turbo_v2_5"

# Voice settings tuned for emergency operator:
# - Higher stability = more consistent, professional tone (less variation)
# - Moderate similarity_boost = natural but clear
# - Style = 0 for neutral professional delivery
ELEVENLABS_VOICE_SETTINGS = {
    "stability": 0.65,
    "similarity_boost": 0.80,
    "style": 0.0,
    "use_speaker_boost": True,
}


# ═════════════════════════════════════════════════════════════
#  STT (Speech-to-Text)
# ═════════════════════════════════════════════════════════════

async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.wav") -> str | None:
    """
    Transcribe audio to text. Tries ElevenLabs first, then Groq Whisper.
    """
    global _elevenlabs_blocked

    # Try ElevenLabs STT first (if not known to be blocked)
    if ELEVENLABS_API_KEY and not _elevenlabs_blocked:
        result = await _elevenlabs_stt(audio_bytes, filename)
        if result is not None:
            return result
        # If it failed, it might be blocked — try Groq

    # Fallback: Groq Whisper STT
    if GROQ_API_KEY:
        result = await _groq_whisper_stt(audio_bytes, filename)
        if result is not None:
            return result

    logger.error("All STT providers failed.")
    return None


# ═════════════════════════════════════════════════════════════
#  TTS (Text-to-Speech)
# ═════════════════════════════════════════════════════════════

async def text_to_speech(text: str) -> bytes | None:
    """
    Convert text to speech (full audio, non-streaming).
    Used by Telegram bot and as fallback.
    Chain: ElevenLabs → Edge-TTS → None (browser fallback).
    Returns MP3 audio bytes, or None if all server-side TTS fail.
    """
    global _elevenlabs_blocked

    # 1) Try ElevenLabs (if not blocked)
    if not _elevenlabs_blocked and ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID:
        result = await _elevenlabs_tts(text)
        if result is not None:
            return result

    # 2) Edge-TTS fallback (Microsoft, free, no API key required)
    result = await _edge_tts(text)
    if result is not None:
        return result

    # 3) All server TTS failed — frontend will use browser Web Speech API
    logger.warning("All server-side TTS failed — deferring to browser TTS.")
    return None


async def text_to_speech_streaming(text: str) -> AsyncGenerator[bytes, None]:
    """
    Stream TTS audio chunks as they're generated.
    Used by the web call interface for minimal latency — audio starts
    playing in the browser before the full response is ready.

    Chain: ElevenLabs streaming → Edge-TTS streaming → empty (browser fallback).
    Yields MP3 audio chunks.
    """
    global _elevenlabs_blocked

    # 1) Try ElevenLabs streaming
    if not _elevenlabs_blocked and ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID:
        chunk_count = 0
        async for chunk in _elevenlabs_tts_stream(text):
            chunk_count += 1
            yield chunk
        if chunk_count > 0:
            return

    # 2) Edge-TTS streaming fallback
    chunk_count = 0
    async for chunk in _edge_tts_stream(text):
        chunk_count += 1
        yield chunk
    if chunk_count > 0:
        return

    # 3) No streaming available — frontend will use browser TTS
    logger.warning("All streaming TTS failed.")


# ═════════════════════════════════════════════════════════════
#  ElevenLabs TTS Implementation
# ═════════════════════════════════════════════════════════════

async def _elevenlabs_tts(text: str) -> bytes | None:
    """ElevenLabs TTS — non-streaming, returns full audio."""
    global _elevenlabs_blocked

    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "model_id": ELEVENLABS_TTS_MODEL,
        "voice_settings": ELEVENLABS_VOICE_SETTINGS,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try flash model first
            resp = await client.post(tts_url, headers=headers, json=payload)

            # If flash model not available for this voice, fall back to turbo
            if resp.status_code == 422 or resp.status_code == 400:
                logger.info("Flash model not available, trying turbo fallback...")
                payload["model_id"] = ELEVENLABS_TTS_MODEL_FALLBACK
                resp = await client.post(tts_url, headers=headers, json=payload)

            resp.raise_for_status()
            audio_bytes = resp.content
            logger.info("ElevenLabs TTS successful (%d bytes, model=%s).", len(audio_bytes), payload["model_id"])
            return audio_bytes

    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        if "unusual_activity" in body or exc.response.status_code == 401:
            _elevenlabs_blocked = True
            logger.warning("ElevenLabs blocked — switching to Edge-TTS.")
        else:
            logger.error("ElevenLabs TTS HTTP error %s: %s", exc.response.status_code, body[:300])
    except httpx.RequestError as exc:
        logger.error("ElevenLabs TTS request error: %s", exc)

    return None


async def _elevenlabs_tts_stream(text: str) -> AsyncGenerator[bytes, None]:
    """
    ElevenLabs streaming TTS — yields audio chunks as they're generated.
    Uses the /stream endpoint for minimal time-to-first-byte.
    """
    global _elevenlabs_blocked

    if _elevenlabs_blocked:
        return

    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "model_id": ELEVENLABS_TTS_MODEL,
        "voice_settings": ELEVENLABS_VOICE_SETTINGS,
        "output_format": "mp3_44100_128",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", tts_url, headers=headers, json=payload) as resp:
                # If flash model not available, retry with turbo (non-streaming for simplicity)
                if resp.status_code in (422, 400):
                    logger.info("Flash model not available for streaming, trying turbo...")
                    # Fall through to non-streaming fallback below
                    return

                if resp.status_code == 401 or resp.status_code == 403:
                    body = await resp.aread()
                    if b"unusual_activity" in body:
                        _elevenlabs_blocked = True
                        logger.warning("ElevenLabs blocked during streaming.")
                    return

                resp.raise_for_status()

                total_bytes = 0
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    if chunk:
                        total_bytes += len(chunk)
                        yield chunk

                logger.info("ElevenLabs streaming TTS complete (%d bytes).", total_bytes)

    except httpx.HTTPStatusError as exc:
        body = exc.response.text if hasattr(exc.response, 'text') else str(exc)
        if "unusual_activity" in str(body) or exc.response.status_code == 401:
            _elevenlabs_blocked = True
            logger.warning("ElevenLabs blocked during streaming.")
        else:
            logger.error("ElevenLabs streaming TTS error %s: %s", exc.response.status_code, str(body)[:200])
    except httpx.RequestError as exc:
        logger.error("ElevenLabs streaming TTS request error: %s", exc)
    except Exception as exc:
        logger.error("ElevenLabs streaming TTS unexpected error: %s", exc)


# ═════════════════════════════════════════════════════════════
#  Edge-TTS Implementation
# ═════════════════════════════════════════════════════════════

async def _edge_tts(text: str) -> bytes | None:
    """Microsoft Edge TTS — free, no API key, high quality neural voices."""
    try:
        communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        audio_bytes = buffer.getvalue()
        if audio_bytes:
            logger.info("Edge-TTS successful (%d bytes).", len(audio_bytes))
            return audio_bytes
        return None
    except Exception as exc:
        logger.error("Edge-TTS error: %s", exc)
        return None


async def _edge_tts_stream(text: str) -> AsyncGenerator[bytes, None]:
    """Stream Edge-TTS audio chunks."""
    try:
        communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
        total_bytes = 0
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and chunk["data"]:
                total_bytes += len(chunk["data"])
                yield chunk["data"]
        if total_bytes > 0:
            logger.info("Edge-TTS streaming complete (%d bytes).", total_bytes)
    except Exception as exc:
        logger.error("Edge-TTS streaming error: %s", exc)


# ═════════════════════════════════════════════════════════════
#  ElevenLabs STT Implementation
# ═════════════════════════════════════════════════════════════

async def _elevenlabs_stt(audio_bytes: bytes, filename: str) -> str | None:
    """ElevenLabs Speech-to-Text."""
    global _elevenlabs_blocked

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
    mime_map = {
        "wav": "audio/wav", "mp3": "audio/mpeg", "webm": "audio/webm",
        "ogg": "audio/ogg", "oga": "audio/ogg", "opus": "audio/ogg",
        "m4a": "audio/mp4", "flac": "audio/flac",
    }
    mime_type = mime_map.get(ext, "audio/ogg")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                ELEVENLABS_STT_URL,
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                files={"file": (filename, audio_bytes, mime_type)},
                data={"model_id": "scribe_v1"},
            )
            resp.raise_for_status()
            transcript = resp.json().get("text", "")
            if transcript:
                logger.info("ElevenLabs STT successful (%d chars).", len(transcript))
                return transcript
            return None

    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        if "unusual_activity" in body or exc.response.status_code == 401:
            _elevenlabs_blocked = True
            logger.warning("ElevenLabs STT blocked — falling back to Groq Whisper.")
        else:
            logger.error("ElevenLabs STT HTTP %s: %s", exc.response.status_code, body)
    except httpx.RequestError as exc:
        logger.error("ElevenLabs STT request error: %s", exc)
    return None


# ═════════════════════════════════════════════════════════════
#  Groq Whisper STT (free fallback)
# ═════════════════════════════════════════════════════════════

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

async def _groq_whisper_stt(audio_bytes: bytes, filename: str) -> str | None:
    """Groq Whisper STT — free, fast, no restrictions."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
    mime_map = {
        "wav": "audio/wav", "mp3": "audio/mpeg", "webm": "audio/webm",
        "ogg": "audio/ogg", "oga": "audio/ogg", "opus": "audio/ogg",
        "m4a": "audio/mp4", "flac": "audio/flac",
    }
    mime_type = mime_map.get(ext, "audio/ogg")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GROQ_STT_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (filename, audio_bytes, mime_type)},
                data={
                    "model": "whisper-large-v3-turbo",
                    "response_format": "json",
                    "language": "en",
                },
            )
            resp.raise_for_status()
            result = resp.json()
            transcript = result.get("text", "")
            if transcript:
                logger.info("Groq Whisper STT successful (%d chars).", len(transcript))
                return transcript
            return None

    except httpx.HTTPStatusError as exc:
        logger.error("Groq Whisper STT HTTP %s: %s", exc.response.status_code, exc.response.text)
    except httpx.RequestError as exc:
        logger.error("Groq Whisper STT request error: %s", exc)
    return None
