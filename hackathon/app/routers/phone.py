"""
Phone call webhook routes — Multi-turn structured interview.

Flow:
  1. Caller dials → /api/phone/incoming → AI greeting + first question
  2. Caller answers → /api/phone/gather?step=N → record answer, ask next question
  3. After all questions → classify severity, log report, push to dashboard
  4. AI tells caller: "A responder will contact you immediately."

The AI NEVER gives medical advice. It only collects data.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.config import BASE_URL
from app.models.triage import InputSource
from app.services.call_sessions import session_manager, QUESTIONS
from app.services.events import event_manager
from app.services.report_store import store
from app.services.triage_engine import classify_intake

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/phone", tags=["Phone"])


def twiml(xml: str) -> Response:
    """Return a TwiML XML response."""
    return Response(content=xml, media_type="text/xml")


def gather_twiml(question: str, step: int, call_sid: str) -> str:
    """Build TwiML that asks a question and listens for speech."""
    action_url = f"{BASE_URL}/api/phone/gather?step={step}&sid={call_sid}"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech"
            action="{action_url}"
            method="POST"
            speechTimeout="auto"
            speechModel="experimental_conversations"
            language="en-US"
            enhanced="true"
            timeout="8">
        <Say voice="Polly.Joanna">{question}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I did not hear a response. Let me ask again.</Say>
    <Redirect method="POST">{action_url}</Redirect>
</Response>"""


# ── Incoming Call ───────────────────────────────────────────

@router.post("/incoming")
async def incoming_call(request: Request):
    """
    Twilio webhook: called when someone dials the phone number.
    Creates a session and starts the structured interview.
    """
    form = await request.form()
    caller = form.get("From", "Unknown")
    call_sid = form.get("CallSid", "unknown")

    logger.info("📞 Incoming call from %s (CallSid: %s)", caller, call_sid[:8])

    # Create session
    session = await session_manager.get_or_create(call_sid, caller)

    # Greeting + first question
    first_q = QUESTIONS[0]["question"]
    action_url = f"{BASE_URL}/api/phone/gather?step=0&sid={call_sid}"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-US">
        2020 AI Agent. I will ask you a few short questions to assess the situation.
        Please answer each question clearly.
    </Say>
    <Gather input="speech"
            action="{action_url}"
            method="POST"
            speechTimeout="auto"
            speechModel="experimental_conversations"
            language="en-US"
            enhanced="true"
            timeout="10">
        <Say voice="Polly.Joanna">{first_q}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I did not hear a response. Let me ask again.</Say>
    <Redirect method="POST">{action_url}</Redirect>
</Response>"""

    return twiml(xml)


# ── Gather Callback (each question step) ───────────────────

@router.post("/gather")
async def gather_callback(request: Request):
    """
    Twilio webhook: called after caller answers each question.
    Records the answer, moves to next question or finishes.
    """
    form = await request.form()
    speech = form.get("SpeechResult", "")
    caller = form.get("From", "Unknown")
    call_sid = request.query_params.get("sid", form.get("CallSid", "unknown"))
    step = int(request.query_params.get("step", "0"))

    logger.info("📞 Step %d answer from %s: %s", step, caller, speech)

    session = await session_manager.get_or_create(call_sid, caller)

    # Record the answer for the current step
    if speech.strip():
        # Make sure session step matches the expected step
        session.step = step
        session.record_answer(speech)
    else:
        # No speech — skip and advance
        session.step = step + 1

    # Check if interview is complete
    if session.is_complete:
        return await _finish_interview(session)

    # Ask the next question
    next_q = session.current_question
    if next_q is None:
        return await _finish_interview(session)

    return twiml(gather_twiml(next_q["question"], session.step, call_sid))


async def _finish_interview(session) -> Response:
    """Classify the collected data and deliver the closing message."""
    data = session.get_structured_data()

    logger.info("📞 Interview complete for %s. Classifying...", session.caller)

    # Run triage classification
    report = await classify_intake(
        situation_description=data.get("situation_description", ""),
        input_source=InputSource.PHONE_CALL,
        patient_name=data.get("patient_name"),
        age=data.get("age"),
        is_conscious=data.get("is_conscious"),
        is_breathing=data.get("is_breathing"),
        has_heavy_bleeding=data.get("has_heavy_bleeding"),
        location=data.get("location"),
        is_trapped=data.get("is_trapped"),
        disaster_type=data.get("disaster_type"),
        num_victims=data.get("num_victims"),
        environmental_dangers=data.get("environmental_dangers"),
        conversation_transcript=session.full_transcript,
        caller_phone=session.caller,
    )

    # Store and broadcast
    await store.add(report)
    await event_manager.broadcast("new_report", report)

    logger.info(
        "📞 Call classified: %s severity=%s priority=%d id=%s",
        session.caller,
        report.severity.value,
        report.estimated_response_priority,
        report.report_id,
    )

    # Clean up session
    await session_manager.remove(session.call_sid)

    # Closing message — NO medical advice
    severity_msg = f"Your case has been classified as {report.severity.value} priority."
    callback_msg = (
        "A certified responder will contact you immediately. Please keep your phone available."
        if report.needs_human_callback
        else "Your case has been logged. A responder will follow up with you shortly."
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-US">
        Thank you for the information.
        {severity_msg}
        {callback_msg}
        Please stay safe and do not move the injured person unless they are in immediate danger.
        A responder will call you back at this number.
        Goodbye.
    </Say>
    <Hangup/>
</Response>"""

    return twiml(xml)


# ── Status Callback ─────────────────────────────────────────

@router.post("/status")
async def call_status(request: Request):
    """Twilio call status callback (logging only)."""
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")
    logger.info("📞 Call %s status: %s", call_sid[:8], status)
    return Response(content="OK", media_type="text/plain")
