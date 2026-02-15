"""
Voice interview API — conversational AI triage interview.

The AI has a natural conversation with the operator, collecting
emergency data through adaptive dialogue rather than rigid Q&A.

Flow:
  POST /api/interview/start          → returns session_id + AI greeting
  POST /api/interview/{sid}/message  → sends user speech, returns AI response
  POST /api/interview/{sid}/end      → force-end a conversation
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel

from app.models.triage import AIModel, InputSource, SeverityLevel, TriageReport
from app.services.conversation_engine import (
    create_session,
    get_session,
    get_ai_response,
    remove_session,
)
from app.services.elevenlabs import text_to_speech, transcribe_audio
from app.services.events import event_manager
from app.services.report_store import store
from app.services.triage_engine import classify_intake

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interview", tags=["Voice Interview"])


# ── Request / Response Models ────────────────────────────────

class MessageRequest(BaseModel):
    message: str


class ConversationResponse(BaseModel):
    session_id: str
    ai_message: str
    turn_count: int
    is_complete: bool = False
    report: TriageReport | None = None


# ── Start Conversation ───────────────────────────────────────

@router.post("/start", response_model=ConversationResponse)
async def start_interview() -> ConversationResponse:
    """Start a new conversational triage interview. Returns the AI's opening."""
    session = create_session()

    # Get the AI's opening message
    ai_response = await get_ai_response(session)

    # Strip the [TRIAGE_COMPLETE] part if present (shouldn't be on first turn)
    display_text = ai_response.split("[TRIAGE_COMPLETE]")[0].strip()

    logger.info("Conversation started: %s", session.session_id)

    return ConversationResponse(
        session_id=session.session_id,
        ai_message=display_text,
        turn_count=0,
        is_complete=False,
    )


# ── Send Message ─────────────────────────────────────────────

@router.post("/{session_id}/message", response_model=ConversationResponse)
async def send_message(session_id: str, body: MessageRequest) -> ConversationResponse:
    """Send a message in an ongoing conversation. Returns the AI's response."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation session not found.")

    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Empty message.")

    # Add user's message and get AI response
    session.add_user_message(body.message.strip())
    ai_response = await get_ai_response(session)

    # Display text (without JSON block)
    display_text = ai_response.split("[TRIAGE_COMPLETE]")[0].strip()

    # If the interview is complete, build and store the report
    if session.is_complete:
        report = await _build_report(session)
        remove_session(session_id)
        return ConversationResponse(
            session_id=session_id,
            ai_message=display_text,
            turn_count=session.turn_count,
            is_complete=True,
            report=report,
        )

    return ConversationResponse(
        session_id=session_id,
        ai_message=display_text,
        turn_count=session.turn_count,
        is_complete=False,
    )


# ── Force End ────────────────────────────────────────────────

@router.post("/{session_id}/end", response_model=ConversationResponse)
async def end_interview(session_id: str) -> ConversationResponse:
    """Force-end a conversation and generate a report from collected data."""
    from app.services.conversation_engine import _fallback_complete, _parse_completion

    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation session not found.")

    # Try asking AI to wrap up first
    session.add_user_message(
        "[SYSTEM: The operator has ended the interview. Summarize the data you have and generate the [TRIAGE_COMPLETE] JSON classification now.]"
    )
    ai_response = await get_ai_response(session)
    display_text = ai_response.split("[TRIAGE_COMPLETE]")[0].strip()

    # If AI didn't produce a completion (fallback may not), force it
    if not session.is_complete:
        completion_response = _fallback_complete(session)
        _parse_completion(session, completion_response)
        display_text = completion_response.split("[TRIAGE_COMPLETE]")[0].strip()

    report = await _build_report(session)
    remove_session(session_id)

    return ConversationResponse(
        session_id=session_id,
        ai_message=display_text or "Interview ended. Case has been logged and classified.",
        turn_count=session.turn_count,
        is_complete=True,
        report=report,
    )


# ── Build Report from extracted data ─────────────────────────


# ── Text-to-Speech via ElevenLabs ────────────────────────────

# ── Speech-to-Text via ElevenLabs ────────────────────────────

@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """Transcribe audio to text using ElevenLabs STT."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    transcript = await transcribe_audio(audio_bytes, filename=audio.filename or "audio.webm")
    if transcript is None:
        raise HTTPException(status_code=503, detail="STT service unavailable.")

    return {"text": transcript}


class TTSRequest(BaseModel):
    text: str


@router.post("/tts")
async def generate_speech(body: TTSRequest):
    """Convert text to speech. Returns MP3 audio or JSON fallback indicator."""
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text.")

    audio = await text_to_speech(body.text.strip())
    if audio is None:
        # ElevenLabs unavailable — tell frontend to use browser TTS
        return {"fallback": True, "text": body.text.strip()}

    return FastAPIResponse(
        content=audio,
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=speech.mp3"},
    )


@router.post("/tts/stream")
async def generate_speech_streaming(body: TTSRequest):
    """
    Streaming TTS — returns audio chunks as they're generated.
    Used by the web call interface for minimal latency.
    Audio starts playing in the browser before the full response is ready.
    """
    from fastapi.responses import StreamingResponse
    from app.services.elevenlabs import text_to_speech_streaming

    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text.")

    async def stream_audio():
        has_chunks = False
        async for chunk in text_to_speech_streaming(body.text.strip()):
            has_chunks = True
            yield chunk
        if not has_chunks:
            # No streaming available — this shouldn't happen as frontend
            # checks content-type, but just in case
            logger.warning("Streaming TTS produced no audio.")

    return StreamingResponse(
        stream_audio(),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=speech.mp3",
            "Cache-Control": "no-cache",
            "Transfer-Encoding": "chunked",
        },
    )


async def _build_report(session) -> TriageReport:
    """Build a TriageReport from the AI's extracted data."""
    data = session.extracted_data or {}

    # If the AI extracted a full classification, use it directly
    severity = data.get("severity", "MODERATE")
    confidence = float(data.get("confidence", 0.5))
    risk_factors = data.get("detected_risk_factors", [])
    reasoning = data.get("reasoning", "")
    priority = int(data.get("estimated_response_priority", 5))
    needs_callback = data.get("needs_human_callback", True)

    # Determine AI model used
    provider = getattr(session, "ai_provider", "fallback")
    if provider == "groq":
        model = AIModel.GROQ
    elif provider == "minimax":
        model = AIModel.MINIMAX
    else:
        model = AIModel.FALLBACK_KEYWORD

    # Build better situation description from all user messages
    situation = data.get("situation_description")
    if not situation or situation in ("No description", "See transcript"):
        user_msgs = [m["content"] for m in session.messages if m["role"] == "user" and not m["content"].startswith("[SYSTEM")]
        situation = " | ".join(user_msgs) if user_msgs else "See transcript"

    # Geocode location
    from app.services.geocoding import geocode_location
    lat, lng = None, None
    loc = data.get("location")
    if loc:
        coords = await geocode_location(loc)
        if coords:
            lat, lng = coords

    report = TriageReport(
        input_source=InputSource.VOICE_UPLOAD,
        patient_name=data.get("patient_name"),
        age=_safe_int(data.get("age")),
        gender=data.get("gender"),
        is_conscious=data.get("is_conscious"),
        is_breathing=data.get("is_breathing"),
        has_heavy_bleeding=data.get("has_heavy_bleeding"),
        location=loc,
        latitude=lat,
        longitude=lng,
        is_trapped=data.get("is_trapped"),
        indoor_outdoor=data.get("indoor_outdoor"),
        situation_description=situation,
        disaster_type=data.get("disaster_type"),
        num_victims=_safe_int(data.get("num_victims")),
        environmental_dangers=data.get("environmental_dangers"),
        severity=SeverityLevel(severity),
        confidence=max(0.0, min(1.0, confidence)),
        detected_risk_factors=risk_factors if isinstance(risk_factors, list) else [],
        reasoning=reasoning,
        estimated_response_priority=max(1, min(10, priority)),
        needs_human_callback=needs_callback,
        conversation_transcript=session.get_transcript(),
        ai_model=model,
    )

    await store.add(report)
    await event_manager.broadcast("new_report", report)

    logger.info(
        "Conversation %s complete: %s P%d (%d turns)",
        session.session_id,
        report.severity.value,
        report.estimated_response_priority,
        session.turn_count,
    )

    return report


def _safe_int(val) -> int | None:
    """Safely convert to int."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _extract_situation_from_transcript(session) -> str:
    """Pull the first user message as the situation description."""
    for msg in session.messages:
        if msg["role"] == "user" and not msg["content"].startswith("[SYSTEM"):
            return msg["content"]
    return "Emergency case — see transcript for details."
