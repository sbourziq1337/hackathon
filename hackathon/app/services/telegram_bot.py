"""
Telegram Bot integration for emergency triage conversations.

Users can chat with the AI triage operator via Telegram.
Uses polling mode — works on localhost, no public URL needed.

Flow:
  /start → creates a conversation session
  Any message → AI responds naturally, collecting emergency data
  When enough data → AI completes triage, stores report, notifies dashboard
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import TELEGRAM_BOT_TOKEN
from app.models.triage import AIModel, InputSource, SeverityLevel, TriageReport, ReportStatus
from app.services.conversation_engine import (
    ConversationSession,
    create_session,
    detect_critical_instant,
    extract_live_data,
    get_ai_response,
    get_session,
    remove_session,
)
from app.services.events import event_manager
from app.services.geocoding import geocode_location
from app.services.report_store import store
from app.services.triage_engine import classify_intake

logger = logging.getLogger(__name__)


async def _convert_voice_for_stt(audio_bytes: bytes, ext: str) -> tuple[bytes, str]:
    """Convert Telegram voice (.oga OPUS) → WAV for reliable Whisper transcription.

    Groq Whisper works best with WAV/MP3. Telegram sends .oga (OPUS in OGG).
    Returns (converted_bytes, filename) or original if conversion fails.
    """
    import subprocess
    import tempfile
    import os

    if ext in ("wav", "mp3", "mp4", "m4a", "flac"):
        return audio_bytes, f"voice.{ext}"

    src_path = None
    wav_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as src_file:
            src_file.write(audio_bytes)
            src_path = src_file.name

        wav_path = src_path.rsplit(".", 1)[0] + ".wav"

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_path],
            capture_output=True,
            timeout=15,
        )

        if result.returncode == 0 and os.path.exists(wav_path):
            with open(wav_path, "rb") as f:
                wav_bytes = f.read()
            logger.info("Converted .%s → WAV for STT (%d → %d bytes)", ext, len(audio_bytes), len(wav_bytes))
            return wav_bytes, "voice.wav"
        else:
            logger.warning("ffmpeg STT conversion failed: %s", result.stderr.decode(errors="replace")[:200])
            return audio_bytes, f"voice.{ext}"
    except Exception as exc:
        logger.error("STT audio conversion error: %s", exc)
        return audio_bytes, f"voice.{ext}"
    finally:
        for path in [src_path, wav_path]:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


async def _convert_to_ogg_opus(mp3_bytes: bytes) -> bytes | None:
    """Convert MP3 audio to OGG/OPUS format for Telegram voice messages.

    Telegram voice messages require OGG encoded with OPUS codec.
    Edge-TTS produces MP3, so we convert via ffmpeg.
    """
    import subprocess
    import tempfile
    import os

    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_file:
            mp3_file.write(mp3_bytes)
            mp3_path = mp3_file.name

        ogg_path = mp3_path.replace(".mp3", ".ogg")

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "64k", "-ar", "48000", ogg_path],
            capture_output=True,
            timeout=15,
        )

        if result.returncode == 0 and os.path.exists(ogg_path):
            with open(ogg_path, "rb") as f:
                ogg_bytes = f.read()
            logger.info("Converted MP3 → OGG/OPUS (%d → %d bytes)", len(mp3_bytes), len(ogg_bytes))
            return ogg_bytes
        else:
            logger.warning("ffmpeg conversion failed: %s", result.stderr.decode(errors="replace")[:200])
            return None
    except Exception as exc:
        logger.error("Audio conversion error: %s", exc)
        return None
    finally:
        # Cleanup temp files
        for path in [mp3_path, ogg_path]:
            try:
                os.unlink(path)
            except OSError:
                pass

# Map Telegram chat_id → conversation session_id (during triage)
_chat_sessions: dict[int, str] = {}

# Map report_id → chat_id (for human operator → victim messaging after triage)
_report_chat_map: dict[str, int] = {}

# Map chat_id → report_id (for victim → dashboard replies after triage)
_chat_report_map: dict[int, str] = {}

# Map chat_id → live report_id during active conversation (for streaming updates)
_chat_live_report: dict[int, str] = {}

# The Telegram application instance
_app: Application | None = None


async def _send_voice_reply(chat_id: int, text: str, bot) -> None:
    """Send an AI text response as a voice note on Telegram.

    Generates TTS audio, converts MP3 → OGG/OPUS, sends as voice message.
    Falls back silently if TTS fails (text reply is always sent separately).
    """
    try:
        from app.services.elevenlabs import text_to_speech
        audio = await text_to_speech(text)
        if audio:
            import io
            ogg_audio = await _convert_to_ogg_opus(audio)
            if ogg_audio:
                await bot.send_voice(
                    chat_id=chat_id,
                    voice=io.BytesIO(ogg_audio),
                )
            else:
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=io.BytesIO(audio),
                    title="AI Response",
                    performer="2020 AI Agent",
                )
    except Exception as e:
        logger.debug("Voice reply failed: %s", e)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — create a new triage conversation and a live report."""
    chat_id = update.effective_chat.id

    # End existing session if any
    old_sid = _chat_sessions.pop(chat_id, None)
    if old_sid:
        remove_session(old_sid)

    # Create new conversation
    session = create_session()
    _chat_sessions[chat_id] = session.session_id

    # Create a LIVE report immediately so it appears on the dashboard
    report = TriageReport(
        input_source=InputSource.TELEGRAM,
        situation_description="🔴 LIVE — Conversation in progress...",
        severity=SeverityLevel.MODERATE,
        confidence=0.0,
        reasoning="AI is currently interviewing the caller. Data will stream in real-time.",
        estimated_response_priority=5,
        needs_human_callback=True,
        status=ReportStatus.IN_PROGRESS,
        caller_phone=f"telegram:{chat_id}",
        ai_model=AIModel.GROQ,
        conversation_transcript="",
    )
    await store.add(report)
    _chat_live_report[chat_id] = report.report_id
    _report_chat_map[report.report_id] = chat_id
    _chat_report_map[chat_id] = report.report_id

    # Broadcast the live report to dashboard
    await event_manager.broadcast("new_report", report)

    # Get AI opening message
    ai_response = await get_ai_response(session)
    display_text = ai_response.split("[TRIAGE_COMPLETE]")[0].strip()

    # Update transcript
    await store.update(report.report_id, conversation_transcript=session.get_transcript())

    await update.message.reply_text(
        f"🚨 *2020 AI Agent*\n\n{display_text}\n\n"
        f"_Type your messages or send voice notes. "
        f"Send /cancel to cancel, /end to finish early._",
        parse_mode="Markdown",
    )

    # Send AI greeting as voice — feels like a real 911 call
    await _send_voice_reply(chat_id, display_text, context.bot)

    logger.info("Telegram session started: chat=%s session=%s report=%s", chat_id, session.session_id, report.report_id)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cancel command — cancel current conversation."""
    chat_id = update.effective_chat.id
    sid = _chat_sessions.pop(chat_id, None)
    if sid:
        remove_session(sid)
        await update.message.reply_text("❌ Conversation cancelled. Send /start to begin a new one.")
    else:
        await update.message.reply_text("No active conversation. Send /start to begin.")


async def end_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /end command — force-end conversation and generate report."""
    from app.services.conversation_engine import _fallback_complete, _parse_completion

    chat_id = update.effective_chat.id
    sid = _chat_sessions.get(chat_id)
    if not sid:
        await update.message.reply_text("No active conversation. Send /start to begin.")
        return

    session = get_session(sid)
    if not session:
        _chat_sessions.pop(chat_id, None)
        await update.message.reply_text("Session expired. Send /start to begin a new one.")
        return

    # Ask AI to wrap up
    session.add_user_message(
        "[SYSTEM: The user has ended the interview. Summarize and generate the [TRIAGE_COMPLETE] JSON now.]"
    )
    ai_response = await get_ai_response(session)

    # Force completion if AI didn't produce one
    if not session.is_complete:
        completion = _fallback_complete(session)
        _parse_completion(session, completion)

    # Build and store report
    report = await _finalize_telegram_report(session, chat_id)

    # Clean up session but keep chat mapping for human operator replies
    _chat_sessions.pop(chat_id, None)
    _chat_live_report.pop(chat_id, None)
    remove_session(sid)

    # Keep mapping so human operators can message this victim
    _report_chat_map[report.report_id] = chat_id
    _chat_report_map[chat_id] = report.report_id

    # Send result
    sev = report.severity.value
    emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MODERATE": "🟡", "LOW": "🟢"}.get(sev, "⚪")
    risk = ", ".join(report.detected_risk_factors) if report.detected_risk_factors else "None identified"

    await update.message.reply_text(
        f"✅ *Triage Complete*\n\n"
        f"{emoji} *Severity: {sev}*\n"
        f"📋 Priority: {report.estimated_response_priority}/10\n"
        f"🎯 Confidence: {round(report.confidence * 100)}%\n\n"
        f"👤 Patient: {report.patient_name or 'Unknown'}\n"
        f"📍 Location: {report.location or 'Unknown'}\n"
        f"⚠️ Risk Factors: {risk}\n\n"
        f"📝 {report.reasoning}\n\n"
        f"_A human responder will follow up. You can keep chatting here — your messages will be forwarded._\n\n"
        f"Send /start for a new report.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages — continue the conversation.

    Flow (optimized for real-time):
      1. INSTANT: Update transcript + run critical keyword detection (0ms)
      2. INSTANT: If critical, immediately escalate severity + broadcast alert
      3. PARALLEL: Run AI response + Groq extraction concurrently
      4. STREAM: Update dashboard with extracted data
      5. REPLY: Send AI response to user
    """
    chat_id = update.effective_chat.id
    user_text = update.message.text

    if not user_text or not user_text.strip():
        return

    sid = _chat_sessions.get(chat_id)

    # If no active triage session, check if this is a post-triage reply
    if not sid:
        report_id = _chat_report_map.get(chat_id)
        if report_id:
            await _forward_victim_reply(chat_id, report_id, user_text.strip())
            await update.message.reply_text(
                "📨 Your message has been forwarded to the responder. They will reply shortly."
            )
            return
        else:
            await update.message.reply_text(
                "👋 Send /start to begin a 2020 AI Agent triage conversation."
            )
            return

    session = get_session(sid)
    if not session:
        _chat_sessions.pop(chat_id, None)
        await update.message.reply_text("Session expired. Send /start to begin a new one.")
        return

    msg_text = user_text.strip()
    live_report_id = _chat_live_report.get(chat_id)

    # ═══════════════════════════════════════════════════════
    # STEP 1: INSTANT — Critical detection (zero latency)
    # Runs BEFORE AI responds so responders are alerted immediately
    # ═══════════════════════════════════════════════════════
    critical_info = detect_critical_instant(msg_text)
    if critical_info and live_report_id:
        # Immediately escalate the live report
        escalation_fields = {}
        if critical_info.get("is_critical") or critical_info["severity"] == "CRITICAL":
            escalation_fields["severity"] = SeverityLevel.CRITICAL
            escalation_fields["estimated_response_priority"] = critical_info["priority"]
        elif critical_info["severity"] == "HIGH":
            escalation_fields["severity"] = SeverityLevel.HIGH
            escalation_fields["estimated_response_priority"] = critical_info["priority"]

        # Merge risk factors
        existing_report = await store.get_by_id(live_report_id)
        if existing_report:
            merged_risks = list(set(
                (existing_report.detected_risk_factors or []) + critical_info.get("risk_factors", [])
            ))
            escalation_fields["detected_risk_factors"] = merged_risks

        if escalation_fields:
            updated = await store.update(live_report_id, **escalation_fields)
            if updated:
                # Broadcast immediate update
                await event_manager.broadcast("report_update", updated)
                # Send CRITICAL ALERT — separate event for urgent notification
                if critical_info.get("is_critical"):
                    await event_manager.broadcast_raw("critical_alert", {
                        "report_id": live_report_id,
                        "severity": "CRITICAL",
                        "risk_factors": critical_info["risk_factors"],
                        "patient_name": updated.patient_name or "Unknown",
                        "message": msg_text[:100],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                logger.warning(
                    "⚠️ INSTANT ESCALATION: report=%s severity=%s risks=%s",
                    live_report_id, critical_info["severity"], critical_info["risk_factors"],
                )

    # ═══════════════════════════════════════════════════════
    # STEP 2: PARALLEL — AI response + data extraction at same time
    # ═══════════════════════════════════════════════════════
    session.add_user_message(msg_text)

    # Run AI conversation AND data extraction concurrently
    ai_task = asyncio.create_task(get_ai_response(session))
    extract_task = asyncio.create_task(extract_live_data(session))

    # Wait for both in parallel
    ai_response, partial_data = await asyncio.gather(ai_task, extract_task)

    display_text = ai_response.split("[TRIAGE_COMPLETE]")[0].strip()

    # ═══════════════════════════════════════════════════════
    # STEP 3: STREAM — Update dashboard immediately with extracted data
    # ═══════════════════════════════════════════════════════
    if live_report_id and not session.is_complete:
        update_fields = {
            "conversation_transcript": session.get_transcript(),
        }
        # Map extracted data to report fields
        field_mapping = {
            "patient_name": "patient_name",
            "age": "age",
            "location": "location",
            "situation_description": "situation_description",
            "disaster_type": "disaster_type",
            "num_victims": "num_victims",
            "environmental_dangers": "environmental_dangers",
            "is_conscious": "is_conscious",
            "is_breathing": "is_breathing",
            "has_heavy_bleeding": "has_heavy_bleeding",
            "is_trapped": "is_trapped",
        }
        for src_key, dst_key in field_mapping.items():
            val = partial_data.get(src_key)
            if val is not None:
                update_fields[dst_key] = val

        # Geocode location if we got a new one
        if "location" in update_fields:
            coords = await geocode_location(update_fields["location"])
            if coords:
                update_fields["latitude"] = coords[0]
                update_fields["longitude"] = coords[1]
                logger.info("Geocoded location '%s' → (%.4f, %.4f)", update_fields["location"], coords[0], coords[1])

        updated_report = await store.update(live_report_id, **update_fields)
        if updated_report:
            await event_manager.broadcast("report_update", updated_report)
            logger.info(
                "Streamed live data: report=%s new_fields=%s",
                live_report_id,
                [k for k in update_fields if k != "conversation_transcript"],
            )

    # ═══════════════════════════════════════════════════════
    # STEP 4: Check if interview completed naturally
    # ═══════════════════════════════════════════════════════
    if session.is_complete:
        # Finalize the existing live report with full triage data
        report = await _finalize_telegram_report(session, chat_id)
        _chat_sessions.pop(chat_id, None)
        _chat_live_report.pop(chat_id, None)
        remove_session(sid)

        # Keep mapping so human operators can message this victim
        _report_chat_map[report.report_id] = chat_id
        _chat_report_map[chat_id] = report.report_id

        sev = report.severity.value
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MODERATE": "🟡", "LOW": "🟢"}.get(sev, "⚪")
        risk = ", ".join(report.detected_risk_factors) if report.detected_risk_factors else "None identified"

        await update.message.reply_text(
            f"{display_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ *Triage Complete*\n\n"
            f"{emoji} *Severity: {sev}*\n"
            f"📋 Priority: {report.estimated_response_priority}/10\n"
            f"🎯 Confidence: {round(report.confidence * 100)}%\n\n"
            f"👤 Patient: {report.patient_name or 'Unknown'}\n"
            f"📍 Location: {report.location or 'Unknown'}\n"
            f"⚠️ Risk Factors: {risk}\n\n"
            f"📝 {report.reasoning}\n\n"
            f"_Report ID: {report.report_id}_\n"
            f"_A human responder will follow up. You can keep chatting here — your messages will be forwarded to the responder._\n\n"
            f"Send /start for a new report.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(display_text)
        # Also reply with voice — feels like talking to a real operator
        await _send_voice_reply(chat_id, display_text, context.bot)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages — transcribe, process, and reply with voice.

    Supports both voice notes and audio files from Telegram.
    Uses Groq Whisper (or ElevenLabs) for STT, then processes like text.
    Sends AI reply as both text and voice note.
    """
    chat_id = update.effective_chat.id

    sid = _chat_sessions.get(chat_id)
    if not sid:
        # Check if post-triage reply
        report_id = _chat_report_map.get(chat_id)
        if report_id:
            await update.message.reply_text(
                "🎙️ Please type your follow-up message — voice is only supported during triage.\n"
                "Or send /start to begin a new emergency report."
            )
            return
        await update.message.reply_text("👋 Send /start to begin a 2020 AI Agent triage conversation.")
        return

    session = get_session(sid)
    if not session:
        _chat_sessions.pop(chat_id, None)
        await update.message.reply_text("Session expired. Send /start to begin a new one.")
        return

    # Download voice file
    voice = update.message.voice or update.message.audio
    if not voice:
        return

    await update.message.reply_chat_action("typing")

    try:
        file = await context.bot.get_file(voice.file_id)
        audio_bytes = await file.download_as_bytearray()

        # Determine actual file extension from Telegram file path
        file_path = file.file_path or "voice.oga"
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else "oga"
        logger.info("Voice file: path=%s size=%d bytes ext=%s", file_path, len(audio_bytes), ext)

        # Convert Telegram .oga (OPUS) → WAV for reliable Whisper transcription
        converted_bytes, converted_name = await _convert_voice_for_stt(bytes(audio_bytes), ext)
        logger.info("STT input: %s (%d bytes)", converted_name, len(converted_bytes))

        # Transcribe using our STT service (auto-fallback: ElevenLabs → Groq Whisper)
        from app.services.elevenlabs import transcribe_audio
        transcript = await transcribe_audio(converted_bytes, filename=converted_name)

        logger.info("Voice transcript: '%s' (%d chars)", transcript, len(transcript) if transcript else 0)

        if not transcript or not transcript.strip():
            await update.message.reply_text(
                "⚠️ Couldn't understand the voice message. Please try again or type your message."
            )
            return

        # Filter out Whisper hallucinations on silent audio
        hallucinations = {
            "thank you.", "thanks for watching.", "you", "bye.", "...",
            "thank you for watching.", "thanks.", "the end.", "subscribe.",
        }
        if transcript.strip().lower() in hallucinations:
            logger.warning("Whisper hallucination detected: '%s' — likely silent audio", transcript)
            await update.message.reply_text(
                "⚠️ I couldn't hear anything in your voice message. "
                "Please make sure your microphone is working and try again, or type your message."
            )
            return

        # Show what was heard
        await update.message.reply_text(f"🎙️ _\"{transcript}\"_", parse_mode="Markdown")

        # Process like a text message — reuse the full handle_message pipeline
        # We need to inject the transcript as text and run the same logic
        msg_text = transcript.strip()
        live_report_id = _chat_live_report.get(chat_id)

        # STEP 1: Critical detection
        critical_info = detect_critical_instant(msg_text)
        if critical_info and live_report_id:
            escalation_fields = {}
            if critical_info.get("is_critical") or critical_info["severity"] == "CRITICAL":
                escalation_fields["severity"] = SeverityLevel.CRITICAL
                escalation_fields["estimated_response_priority"] = critical_info["priority"]
            elif critical_info["severity"] == "HIGH":
                escalation_fields["severity"] = SeverityLevel.HIGH
                escalation_fields["estimated_response_priority"] = critical_info["priority"]

            existing_report = await store.get_by_id(live_report_id)
            if existing_report:
                merged_risks = list(set(
                    (existing_report.detected_risk_factors or []) + critical_info.get("risk_factors", [])
                ))
                escalation_fields["detected_risk_factors"] = merged_risks

            if escalation_fields:
                updated = await store.update(live_report_id, **escalation_fields)
                if updated:
                    await event_manager.broadcast("report_update", updated)
                    if critical_info.get("is_critical"):
                        await event_manager.broadcast_raw("critical_alert", {
                            "report_id": live_report_id,
                            "severity": "CRITICAL",
                            "risk_factors": critical_info["risk_factors"],
                            "patient_name": updated.patient_name or "Unknown",
                            "message": msg_text[:100],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

        # STEP 2: Parallel AI + extraction
        session.add_user_message(msg_text)
        ai_task = asyncio.create_task(get_ai_response(session))
        extract_task = asyncio.create_task(extract_live_data(session))
        ai_response, partial_data = await asyncio.gather(ai_task, extract_task)

        display_text = ai_response.split("[TRIAGE_COMPLETE]")[0].strip()

        # STEP 3: Stream data to dashboard
        if live_report_id and not session.is_complete:
            update_fields = {"conversation_transcript": session.get_transcript()}
            field_mapping = {
                "patient_name": "patient_name", "age": "age", "location": "location",
                "situation_description": "situation_description", "disaster_type": "disaster_type",
                "num_victims": "num_victims", "environmental_dangers": "environmental_dangers",
                "is_conscious": "is_conscious", "is_breathing": "is_breathing",
                "has_heavy_bleeding": "has_heavy_bleeding", "is_trapped": "is_trapped",
            }
            for src_key, dst_key in field_mapping.items():
                val = partial_data.get(src_key)
                if val is not None:
                    update_fields[dst_key] = val

            if "location" in update_fields:
                coords = await geocode_location(update_fields["location"])
                if coords:
                    update_fields["latitude"] = coords[0]
                    update_fields["longitude"] = coords[1]

            updated_report = await store.update(live_report_id, **update_fields)
            if updated_report:
                await event_manager.broadcast("report_update", updated_report)

        # STEP 4: Check completion
        if session.is_complete:
            report = await _finalize_telegram_report(session, chat_id)
            _chat_sessions.pop(chat_id, None)
            _chat_live_report.pop(chat_id, None)
            remove_session(sid)
            _report_chat_map[report.report_id] = chat_id
            _chat_report_map[chat_id] = report.report_id

            sev = report.severity.value
            emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MODERATE": "🟡", "LOW": "🟢"}.get(sev, "⚪")
            risk = ", ".join(report.detected_risk_factors) if report.detected_risk_factors else "None identified"

            await update.message.reply_text(
                f"{display_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ *Triage Complete*\n\n"
                f"{emoji} *Severity: {sev}*\n"
                f"📋 Priority: {report.estimated_response_priority}/10\n"
                f"🎯 Confidence: {round(report.confidence * 100)}%\n\n"
                f"👤 Patient: {report.patient_name or 'Unknown'}\n"
                f"📍 Location: {report.location or 'Unknown'}\n"
                f"⚠️ Risk Factors: {risk}\n\n"
                f"_A human responder will follow up._\n"
                f"Send /start for a new report.",
                parse_mode="Markdown",
            )
        else:
            # Send text reply
            await update.message.reply_text(display_text)

            # Also send as voice note — feels like a real call
            await _send_voice_reply(chat_id, display_text, context.bot)

    except Exception as e:
        logger.error("Voice processing error: %s", e, exc_info=True)
        await update.message.reply_text(
            "⚠️ Error processing voice. Please type your message instead."
        )


# ── Human Operator ↔ Victim Messaging ───────────────────────

async def _forward_victim_reply(chat_id: int, report_id: str, message: str) -> None:
    """Forward a victim's post-triage reply to the dashboard via SSE."""
    import json as _json
    data = _json.dumps({
        "type": "victim_message",
        "report_id": report_id,
        "chat_id": chat_id,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sender": "victim",
    })
    sse_msg = f"event: victim_message\ndata: {data}\n\n"
    for queue in list(event_manager._queues):
        try:
            queue.put_nowait(sse_msg)
        except Exception:
            pass
    logger.info("Forwarded victim reply to dashboard: report=%s", report_id)


async def send_message_to_victim(report_id: str, message: str, sender_name: str = "Responder") -> bool:
    """Send a message from a human operator on the website to the victim via Telegram.
    Called from the API endpoint."""
    global _app

    chat_id = _report_chat_map.get(report_id)
    if not chat_id:
        logger.warning("No Telegram chat mapping for report %s", report_id)
        return False

    if not _app or not _app.bot:
        logger.warning("Telegram bot not running")
        return False

    try:
        await _app.bot.send_message(
            chat_id=chat_id,
            text=f"👨‍⚕️ *{sender_name}:*\n{message}",
            parse_mode="Markdown",
        )
        logger.info("Sent operator message to victim: report=%s chat=%s", report_id, chat_id)

        # Also broadcast to SSE so other dashboard users see it
        import json as _json
        data = _json.dumps({
            "type": "operator_message",
            "report_id": report_id,
            "chat_id": chat_id,
            "message": message,
            "sender_name": sender_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sender": "operator",
        })
        sse_msg = f"event: operator_message\ndata: {data}\n\n"
        for queue in list(event_manager._queues):
            try:
                queue.put_nowait(sse_msg)
            except Exception:
                pass

        return True
    except Exception as e:
        logger.error("Failed to send message to victim: %s", e)
        return False


async def _finalize_telegram_report(session: ConversationSession, chat_id: int) -> TriageReport:
    """Finalize the live report with full triage data from a completed conversation."""
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
        user_msgs = [
            m["content"] for m in session.messages
            if m["role"] == "user" and not m["content"].startswith("[SYSTEM")
        ]
        situation = " | ".join(user_msgs) if user_msgs else "See transcript"

    # Check if we have a live report to update
    live_report_id = _chat_live_report.get(chat_id)

    # Geocode the location if available
    lat, lng = None, None
    loc = data.get("location")
    if loc:
        coords = await geocode_location(loc)
        if coords:
            lat, lng = coords
            logger.info("Finalize geocoded '%s' → (%.4f, %.4f)", loc, lat, lng)

    if live_report_id:
        # Update the existing live report with final data
        updated = await store.update(
            live_report_id,
            patient_name=data.get("patient_name"),
            age=_safe_int(data.get("age")),
            gender=data.get("gender"),
            is_conscious=data.get("is_conscious"),
            is_breathing=data.get("is_breathing"),
            has_heavy_bleeding=data.get("has_heavy_bleeding"),
            location=data.get("location"),
            latitude=lat,
            longitude=lng,
            is_trapped=data.get("is_trapped"),
            situation_description=situation,
            disaster_type=data.get("disaster_type"),
            num_victims=_safe_int(data.get("num_victims")),
            environmental_dangers=data.get("environmental_dangers"),
            severity=SeverityLevel(severity),
            confidence=max(0.0, min(1.0, confidence)),
            detected_risk_factors=risk_factors if isinstance(risk_factors, list) else [],
            reasoning=reasoning,
            estimated_response_priority=max(1, min(10, priority)),
            conversation_transcript=session.get_transcript(),
            ai_model=model,
            status=ReportStatus.PENDING,
        )
        if updated:
            await event_manager.broadcast("report_update", updated)
            logger.info(
                "Telegram triage finalized: chat=%s severity=%s priority=%d id=%s",
                chat_id, updated.severity.value, updated.estimated_response_priority, updated.report_id,
            )
            return updated

    # Fallback: create a new report if no live report exists
    report = TriageReport(
        input_source=InputSource.TELEGRAM,
        patient_name=data.get("patient_name"),
        age=_safe_int(data.get("age")),
        gender=data.get("gender"),
        is_conscious=data.get("is_conscious"),
        is_breathing=data.get("is_breathing"),
        has_heavy_bleeding=data.get("has_heavy_bleeding"),
        location=data.get("location"),
        latitude=lat,
        longitude=lng,
        is_trapped=data.get("is_trapped"),
        situation_description=situation,
        disaster_type=data.get("disaster_type"),
        num_victims=_safe_int(data.get("num_victims")),
        environmental_dangers=data.get("environmental_dangers"),
        severity=SeverityLevel(severity),
        confidence=max(0.0, min(1.0, confidence)),
        detected_risk_factors=risk_factors if isinstance(risk_factors, list) else [],
        reasoning=reasoning,
        estimated_response_priority=max(1, min(10, priority)),
        needs_human_callback=True,
        conversation_transcript=session.get_transcript(),
        ai_model=model,
        caller_phone=f"telegram:{chat_id}",
    )

    await store.add(report)
    await event_manager.broadcast("new_report", report)

    logger.info(
        "Telegram triage complete: chat=%s severity=%s priority=%d id=%s",
        chat_id, report.severity.value, report.estimated_response_priority, report.report_id,
    )
    return report


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


async def start_telegram_bot() -> None:
    """Initialize and start the Telegram bot in polling mode."""
    global _app

    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled.")
        return

    logger.info("Starting Telegram bot...")

    _app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    _app.add_handler(CommandHandler("start", start_command))
    _app.add_handler(CommandHandler("cancel", cancel_command))
    _app.add_handler(CommandHandler("end", end_command))
    _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    _app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    # Initialize and start polling
    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling(drop_pending_updates=True)

    logger.info("✅ Telegram bot is running (polling mode).")


async def stop_telegram_bot() -> None:
    """Stop the Telegram bot gracefully."""
    global _app
    if _app:
        logger.info("Stopping Telegram bot...")
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
        _app = None
        logger.info("Telegram bot stopped.")
