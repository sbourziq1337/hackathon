"""
Triage API routes:
  POST /api/triage/text     — text report intake (simple message or structured)
  POST /api/triage/voice    — voice upload intake
  POST /api/triage/chat     — multi-turn conversational intake
  PATCH /api/triage/{id}/callback — update callback status
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.models.triage import (
    CallbackStatus,
    ChatRequest,
    InputSource,
    ReportStatus,
    TextIntakeRequest,
    TextTriageRequest,
    TriageReport,
)
from app.services.elevenlabs import transcribe_audio
from app.services.events import event_manager
from app.services.report_store import store
from app.services.triage_engine import classify_intake
from app.services.conversation_engine import (
    create_session,
    get_session,
    get_ai_response,
    remove_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/triage", tags=["Triage"])


# ── Text Intake (simple message format — spec) ─────────────

@router.post("/text", response_model=TriageReport)
async def triage_text(request: dict) -> TriageReport:
    """
    Accept a text report and classify severity.
    Accepts either simple format: {"message": "..."} or structured intake form with situation_description.
    NO medical advice is returned — data collection and classification only.
    """
    # Determine which format was used
    if "message" in request:
        # Simple spec format
        message = request["message"]
        if not message or not str(message).strip():
            raise HTTPException(status_code=422, detail="message must not be empty")
        report = await classify_intake(
            situation_description=str(message).strip(),
            input_source=InputSource.TEXT,
            location=request.get("location"),
            disaster_type=request.get("disaster_type"),
            num_victims=int(request["num_victims"]) if request.get("num_victims") is not None else None,
        )
    elif "situation_description" in request:
        # Structured intake format
        situation = request["situation_description"]
        if not situation or not str(situation).strip():
            raise HTTPException(status_code=422, detail="situation_description must not be empty")

        age_val = request.get("age")
        if age_val is not None:
            age_val = int(age_val)
        num_victims_val = request.get("num_victims")
        if num_victims_val is not None:
            num_victims_val = int(num_victims_val)

        report = await classify_intake(
            situation_description=str(situation).strip(),
            input_source=InputSource.TEXT,
            patient_name=request.get("patient_name"),
            age=age_val,
            gender=request.get("gender"),
            is_conscious=request.get("is_conscious"),
            is_breathing=request.get("is_breathing"),
            has_heavy_bleeding=request.get("has_heavy_bleeding"),
            location=request.get("location"),
            is_trapped=request.get("is_trapped"),
            indoor_outdoor=request.get("indoor_outdoor"),
            disaster_type=request.get("disaster_type"),
            num_victims=num_victims_val,
            environmental_dangers=request.get("environmental_dangers"),
        )
    else:
        raise HTTPException(status_code=422, detail="Request must include either 'message' or 'situation_description'")

    await store.add(report)
    await event_manager.broadcast("new_report", report)
    logger.info(
        "Text intake: severity=%s priority=%d id=%s",
        report.severity.value,
        report.estimated_response_priority,
        report.report_id,
    )
    return report


# ── Voice Upload Intake ────────────────────────────────────

ALLOWED_EXTENSIONS = {"wav", "mp3", "webm", "ogg", "m4a"}
ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave",
    "audio/mpeg", "audio/mp3", "audio/webm",
    "audio/ogg", "audio/mp4", "audio/x-m4a",
}


@router.post("/voice", response_model=TriageReport)
async def triage_voice(
    audio: UploadFile = File(..., description="Audio file"),
    location: Optional[str] = Form(None),
    disaster_type: Optional[str] = Form(None),
    num_victims: Optional[int] = Form(None),
) -> TriageReport:
    """
    Accept an audio file, transcribe, and classify.
    """
    filename = audio.filename or "audio.wav"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_type = audio.content_type or ""

    if ext not in ALLOWED_EXTENSIONS and content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    transcript = await transcribe_audio(audio_bytes, filename)
    if transcript is None:
        raise HTTPException(status_code=502, detail="Transcription failed.")

    report = await classify_intake(
        situation_description=transcript,
        input_source=InputSource.VOICE_CALL,
        location=location,
        disaster_type=disaster_type,
        num_victims=int(num_victims) if num_victims is not None else None,
        conversation_transcript=f"Audio transcript: {transcript}",
    )
    await store.add(report)
    await event_manager.broadcast("new_report", report)
    return report


# ── Chat / Conversational Intake (spec endpoint) ──────────

class ChatResponse(BaseModel):
    session_id: str
    ai_response: str
    is_complete: bool = False
    report: Optional[TriageReport] = None


@router.post("/chat", response_model=ChatResponse)
async def triage_chat(request: ChatRequest) -> ChatResponse:
    """
    Multi-turn conversational intake.
    - If no session_id: start new conversation, AI asks first question.
    - If session_id exists: continue conversation.
    - When enough data collected: generate final triage report.
    """
    from app.services.conversation_engine import _fallback_complete, _parse_completion

    if request.session_id:
        # Continue existing conversation
        session = get_session(request.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found.")

        session.add_user_message(request.message.strip())
        ai_response = await get_ai_response(session)
        display_text = ai_response.split("[TRIAGE_COMPLETE]")[0].strip()

        if session.is_complete:
            report = await _build_chat_report(session)
            remove_session(request.session_id)
            return ChatResponse(
                session_id=request.session_id,
                ai_response=display_text,
                is_complete=True,
                report=report,
            )

        return ChatResponse(
            session_id=request.session_id,
            ai_response=display_text,
            is_complete=False,
        )
    else:
        # Start a new conversation
        session = create_session()

        # Add the user's first message
        session.add_user_message(request.message.strip())
        ai_response = await get_ai_response(session)
        display_text = ai_response.split("[TRIAGE_COMPLETE]")[0].strip()

        if session.is_complete:
            report = await _build_chat_report(session)
            remove_session(session.session_id)
            return ChatResponse(
                session_id=session.session_id,
                ai_response=display_text,
                is_complete=True,
                report=report,
            )

        return ChatResponse(
            session_id=session.session_id,
            ai_response=display_text,
            is_complete=False,
        )


async def _build_chat_report(session) -> TriageReport:
    """Build a TriageReport from conversation session extracted data."""
    from app.models.triage import AIModel, SeverityLevel
    from app.services.geocoding import geocode_location

    data = session.extracted_data or {}
    severity = data.get("severity", "MODERATE")
    confidence = float(data.get("confidence", 0.5))
    risk_factors = data.get("detected_risk_factors", [])
    reasoning = data.get("reasoning", "")
    priority = int(data.get("estimated_response_priority", 5))

    provider = getattr(session, "ai_provider", "fallback")
    if provider == "groq":
        model = AIModel.GROQ
    elif provider == "minimax":
        model = AIModel.MINIMAX
    else:
        model = AIModel.FALLBACK_KEYWORD

    situation = data.get("situation_description")
    if not situation or situation in ("No description", "See transcript"):
        user_msgs = [m["content"] for m in session.messages if m["role"] == "user" and not m["content"].startswith("[SYSTEM")]
        situation = " | ".join(user_msgs) if user_msgs else "See transcript"

    # Build vital signs from extracted data
    is_breathing = data.get("is_breathing")
    is_conscious = data.get("is_conscious")
    has_bleeding = data.get("has_heavy_bleeding")

    vital_signs = {
        "breathing": "yes" if is_breathing is True else ("no" if is_breathing is False else "unknown"),
        "conscious": "yes" if is_conscious is True else ("no" if is_conscious is False else "unknown"),
        "bleeding": "severe" if has_bleeding is True else ("none" if has_bleeding is False else "unknown"),
    }

    def _safe_int(val):
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    # Geocode location
    loc = data.get("location")
    lat, lng = None, None
    if loc and loc != "unknown":
        coords = await geocode_location(loc)
        if coords:
            lat, lng = coords

    report = TriageReport(
        input_source=InputSource.TEXT,
        patient_name=data.get("patient_name") or "unknown",
        age=_safe_int(data.get("age")),
        gender=data.get("gender"),
        is_conscious=is_conscious,
        is_breathing=is_breathing,
        has_heavy_bleeding=has_bleeding,
        location=data.get("location") or "unknown",
        latitude=lat,
        longitude=lng,
        is_trapped=data.get("is_trapped"),
        situation_description=situation,
        disaster_type=data.get("disaster_type") or "unknown",
        num_victims=_safe_int(data.get("num_victims")),
        environmental_dangers=data.get("environmental_dangers"),
        severity=SeverityLevel(severity),
        confidence=max(0.0, min(1.0, confidence)),
        detected_risk_factors=risk_factors if isinstance(risk_factors, list) else [],
        reasoning=reasoning,
        estimated_response_priority=max(1, min(10, priority)),
        needs_human_callback=True,
        vital_signs_reported=vital_signs,
        conversation_transcript=session.get_transcript(),
        ai_model=model,
    )

    await store.add(report)
    await event_manager.broadcast("new_report", report)
    return report


# ── Callback Status Update ─────────────────────────────────

@router.patch("/{report_id}/callback")
async def update_callback_status(report_id: str, status: CallbackStatus) -> dict:
    """
    Update a report's callback status (used by human responders).
    """
    report = await store.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    report.callback_status = status
    await event_manager.broadcast("callback_update", report)
    logger.info("Callback status updated: %s → %s", report_id[:8], status.value)
    return {"report_id": report_id, "callback_status": status.value}
