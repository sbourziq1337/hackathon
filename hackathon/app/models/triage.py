"""
Pydantic models for the AI Disaster Call Intake & Triage System.

The AI is a DATA COLLECTOR only — no medical advice.
All medical decisions are made by human responders on the dashboard.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────

class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class InputSource(str, Enum):
    VOICE_CALL = "voice_call"
    TEXT = "text"
    PHONE_CALL = "phone_call"      # kept for Twilio phone flow
    VOICE_UPLOAD = "voice_upload"   # kept for backward compat
    TELEGRAM = "telegram"           # Telegram bot conversations


class AIModel(str, Enum):
    MINIMAX = "minimax"
    GROQ = "groq"
    FALLBACK_KEYWORD = "fallback_keyword"


class CallbackStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    COMPLETED = "completed"   # alias for backward compat


class ReportStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


# ── Request Models ──────────────────────────────────────────

class TextTriageRequest(BaseModel):
    """Body for POST /api/triage/text — spec format (simple message)."""
    message: str = Field(..., min_length=1, description="The emergency report text")
    location: Optional[str] = Field(None, description="Caller's location")
    disaster_type: Optional[str] = Field(None, description="earthquake, flood, etc.")
    num_victims: Optional[int] = Field(None, ge=0, description="Number of injured people")


class TextIntakeRequest(BaseModel):
    """Body for POST /api/triage/text — structured intake form (extended)."""
    # Immediate safety
    is_conscious: Optional[bool] = Field(None, description="Is the person conscious?")
    is_breathing: Optional[bool] = Field(None, description="Is the person breathing?")
    has_heavy_bleeding: Optional[bool] = Field(None, description="Is there heavy bleeding?")

    # Patient info
    patient_name: Optional[str] = Field(None, description="Patient full name")
    age: Optional[int] = Field(None, ge=0, le=150, description="Patient age")
    gender: Optional[str] = Field(None, description="Patient gender")

    # Location
    location: Optional[str] = Field(None, description="Exact location / address")
    is_trapped: Optional[bool] = Field(None, description="Is the person trapped?")
    indoor_outdoor: Optional[str] = Field(None, description="Indoor or outdoor?")

    # Situation
    situation_description: str = Field(..., min_length=1, description="What happened?")
    disaster_type: Optional[str] = Field(None, description="Type of disaster")
    num_victims: Optional[int] = Field(None, ge=0, description="Number of victims")
    environmental_dangers: Optional[str] = Field(None, description="Fire, water, collapse, etc.")


class ChatRequest(BaseModel):
    """Body for POST /api/triage/chat — multi-turn conversation."""
    session_id: Optional[str] = Field(None, description="UUID to continue existing conversation")
    message: str = Field(..., min_length=1, description="The caller's latest message")


# ── Triage Report (output) ──────────────────────────────────

class TriageReport(BaseModel):
    """Full structured triage report — NO medical advice, data collection only."""
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    input_source: InputSource
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Patient Information
    patient_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None

    # Safety Assessment
    is_conscious: Optional[bool] = None
    is_breathing: Optional[bool] = None
    has_heavy_bleeding: Optional[bool] = None

    # Location
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_trapped: Optional[bool] = None
    indoor_outdoor: Optional[str] = None

    # Situation
    situation_description: str = ""
    disaster_type: Optional[str] = None
    num_victims: Optional[int] = None
    environmental_dangers: Optional[str] = None

    # Classification (AI output)
    severity: SeverityLevel = SeverityLevel.MODERATE
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    detected_risk_factors: list[str] = Field(default_factory=list)
    reasoning: str = ""

    # Vital signs reported (spec format)
    vital_signs_reported: dict = Field(default_factory=lambda: {
        "breathing": "unknown",
        "conscious": "unknown",
        "bleeding": "unknown",
    })

    # Conversation
    conversation_transcript: str = ""
    caller_phone: Optional[str] = None

    # Responder workflow
    needs_human_callback: bool = True
    callback_status: CallbackStatus = CallbackStatus.PENDING
    status: ReportStatus = ReportStatus.PENDING
    estimated_response_priority: int = Field(ge=1, le=10, default=5)

    # System
    ai_model: AIModel = AIModel.MINIMAX


# ── History helpers ─────────────────────────────────────────

class ReportHistoryQuery(BaseModel):
    """Query parameters for filtering report history."""
    severity: Optional[SeverityLevel] = None
    input_source: Optional[InputSource] = None
    callback_status: Optional[CallbackStatus] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
