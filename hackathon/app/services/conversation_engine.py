"""
Conversational AI engine for natural emergency triage interviews.

Tries AI providers in order:
  1. Groq (free, fast — Llama 3)
  2. Minimax (paid)
  3. Smart local fallback

The AI has a natural multi-turn conversation, collecting emergency data
through empathetic, adaptive dialogue.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import (
    MINIMAX_API_KEY, MINIMAX_MODEL, MINIMAX_API_URL,
    GROQ_API_KEY, GROQ_MODEL, GROQ_API_URL,
)

logger = logging.getLogger(__name__)


# ── The conversation system prompt ────────────────────────────

CONVERSATION_SYSTEM_PROMPT = """You are an AI emergency triage operator. Your ONLY job is to collect essential data efficiently.

RULES (STRICT):
- NO explanations, NO small talk, NO repeating back information.
- Ask ONLY what you need. Extract data from everything the caller says.
- One short direct question per response. 2 words max when possible.
- NEVER mention what you're doing or why you're asking.
- Never ask about something already provided.
- Combine questions only if critical: "Conscious and breathing?" not "Are they conscious? And breathing?"

DATA YOU NEED (in order):
1. What happened? (situation_description)
2. Conscious and breathing? (is_conscious, is_breathing)
3. Where? (location)
4. Name? (patient_name)
5. Trapped or dangers? (is_trapped, environmental_dangers)

THAT'S ALL. STOP AT THESE 5 ITEMS.

RESPONSE EXAMPLES (ONLY):
- "What happened?"
- "Conscious and breathing?"
- "Where?"
- "Name?"
- "Trapped or dangers nearby?"

NO OTHER RESPONSES. NO PLEASANTRIES. NO "THANK YOU" UNTIL THE END.

COMPLETION (when you have all 5 items):
- Output ONE brief message: "Recording complete. Responder dispatching."
- Then on new line: [TRIAGE_COMPLETE]
- Then JSON with all data.

Example:
"Recording complete. Responder dispatching."

[TRIAGE_COMPLETE]
{"patient_name": "Ahmed", "age": 45, "is_conscious": true, "is_breathing": true, "has_heavy_bleeding": true, "is_trapped": true, "location": "Building C, Zone 4", "situation_description": "Earthquake caused building collapse. Patient trapped under debris with heavy leg bleeding.", "disaster_type": "earthquake", "num_victims": 3, "environmental_dangers": "risk of further collapse, fire nearby", "severity": "CRITICAL", "confidence": 0.9, "detected_risk_factors": ["TRAPPED", "HEAVY BLEEDING", "MULTIPLE VICTIMS"], "reasoning": "Patient is trapped under debris with heavy bleeding following earthquake. Multiple victims and environmental dangers present.", "estimated_response_priority": 2, "needs_human_callback": true}

RULES FOR THE JSON:
- severity must be one of: CRITICAL, HIGH, MODERATE, LOW
- confidence is a float between 0.0 and 1.0
- estimated_response_priority is an integer 1-10 (1=most urgent)
- All boolean fields use true/false (not strings)
- If unknown, use null
- The [TRIAGE_COMPLETE] marker must appear on its own line before the JSON

IMPORTANT: ONLY respond with conversational text until you're ready to complete. Do NOT output JSON or the [TRIAGE_COMPLETE] marker until you have enough data. Each response should be 1-3 sentences max (it's being spoken aloud)."""


# ── Conversation Session ─────────────────────────────────────

class ConversationSession:
    """Manages a multi-turn AI conversation for emergency triage."""

    def __init__(self):
        self.session_id: str = str(uuid.uuid4())[:8]
        self.messages: list[dict] = [
            {"role": "system", "content": CONVERSATION_SYSTEM_PROMPT}
        ]
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.is_complete: bool = False
        self.extracted_data: dict | None = None
        self.final_message: str = ""
        self.ai_provider: str = "none"  # track which AI answered

    def add_user_message(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def get_transcript(self) -> str:
        lines = []
        for msg in self.messages:
            if msg["role"] == "user":
                lines.append(f"Operator: {msg['content']}")
            elif msg["role"] == "assistant":
                text = msg["content"].split("[TRIAGE_COMPLETE]")[0].strip()
                if text:
                    lines.append(f"AI: {text}")
        return "\n".join(lines)

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self.messages if m["role"] == "user")


# ── Session Manager ──────────────────────────────────────────

_sessions: dict[str, ConversationSession] = {}


def create_session() -> ConversationSession:
    session = ConversationSession()
    _sessions[session.session_id] = session
    logger.info("Conversation session created: %s", session.session_id)
    return session


def get_session(session_id: str) -> ConversationSession | None:
    return _sessions.get(session_id)


def remove_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


# ── Real-time Data Extraction ────────────────────────────────

EXTRACT_PROMPT = """You are a data extractor. From this emergency conversation transcript, extract all information mentioned so far into JSON. Only include fields that were explicitly stated. Use null for unknown/not mentioned fields.

Return ONLY valid JSON, no other text:
{
  "patient_name": string or null,
  "age": number or null,
  "is_conscious": boolean or null,
  "is_breathing": boolean or null,
  "has_heavy_bleeding": boolean or null,
  "location": string or null,
  "is_trapped": boolean or null,
  "situation_description": string or null,
  "disaster_type": string or null,
  "num_victims": number or null,
  "environmental_dangers": string or null
}"""


async def extract_live_data(session: ConversationSession) -> dict:
    """Extract structured data from conversation so far using a fast Groq call.
    Returns a dict with whatever data has been collected."""
    if not GROQ_API_KEY:
        return _extract_live_data_regex(session)

    # Build a compact transcript for extraction
    transcript_lines = []
    for msg in session.messages:
        if msg["role"] == "user":
            transcript_lines.append(f"Caller: {msg['content']}")
        elif msg["role"] == "assistant":
            text = msg["content"].split("[TRIAGE_COMPLETE]")[0].strip()
            if text:
                transcript_lines.append(f"AI: {text}")
    transcript = "\n".join(transcript_lines[-12:])  # last 12 messages max

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": EXTRACT_PROMPT},
                        {"role": "user", "content": transcript},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # Clean markdown wrapping
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
            data = json.loads(content)
            # Remove null values
            return {k: v for k, v in data.items() if v is not None}
    except Exception as e:
        logger.debug("Live extraction via Groq failed: %s", e)
        return _extract_live_data_regex(session)


def _extract_live_data_regex(session: ConversationSession) -> dict:
    """Fallback regex-based extraction for live data."""
    data = {}
    user_msgs = [m["content"] for m in session.messages if m["role"] == "user"]
    text = " ".join(user_msgs).lower()

    # Name
    for pattern in [r"(?:name is|i'm|i am|called)\s+([a-z]+(?:\s+[a-z]+)?)", r"(?:my name)\s+(?:is\s+)?([a-z]+)"]:
        m = re.search(pattern, text)
        if m:
            name = m.group(1).strip().title()
            if name.lower() not in ("is", "the", "a", "an", "here", "fine", "ok"):
                data["patient_name"] = name
                break

    # Age
    for pattern in [r"(\d{1,3})\s*(?:years?\s*old|y/?o)", r"(?:age|aged?|i am|i'm)\s*(\d{1,3})"]:
        m = re.search(pattern, text)
        if m:
            age = int(m.group(1))
            if 0 < age < 150:
                data["age"] = age
                break

    # Booleans
    bool_checks = {
        "is_conscious": (["conscious", "awake", "alert", "can hear"], ["unconscious", "passed out", "not conscious", "not responding"]),
        "is_breathing": (["breathing", "can breathe"], ["not breathing", "stopped breathing", "can't breathe"]),
        "has_heavy_bleeding": (["bleeding heavily", "heavy bleeding", "lot of blood", "blood everywhere"], ["no bleeding", "not bleeding"]),
        "is_trapped": (["trapped", "stuck", "pinned", "can't move", "under debris"], ["not trapped", "not stuck", "can move"]),
    }
    for field, (pos, neg) in bool_checks.items():
        if any(w in text for w in neg):
            # Negative keywords: set False for all fields (conscious=False, breathing=False,
            # bleeding=False meaning no heavy bleeding, trapped=False meaning not trapped)
            data[field] = False
        elif any(w in text for w in pos):
            data[field] = True

    # Situation
    if user_msgs:
        data["situation_description"] = user_msgs[0][:200] if user_msgs[0] else None

    # Disaster type
    for dtype in ["earthquake", "flood", "fire", "explosion", "hurricane", "tornado", "building collapse"]:
        if dtype in text:
            data["disaster_type"] = dtype
            break

    # Location
    for pattern in [r"(?:at|in|on|near|location is|address is|we are at)\s+(.{5,60}?)(?:\.|$|,)", r"(?:street|road|building|floor|block|zone|district)\s*\w*"]:
        m_loc = re.search(pattern, text)
        if m_loc:
            loc = m_loc.group(1).strip().rstrip(",. ")
            if len(loc) > 3:
                data["location"] = loc.title()
                break

    # Victims
    for pattern in [r"(\d+)\s*(?:people|persons?|victims?|injured|casualties)", r"family of\s*(\d+)"]:
        m_v = re.search(pattern, text)
        if m_v:
            data["num_victims"] = int(m_v.group(1))
            break

    # Dangers
    dangers = []
    for name, kws in {"gas leak": ["gas leak", "gas smell"], "fire": ["fire", "flames"], "flood": ["flood water", "rising water"], "collapse risk": ["further collapse", "unstable"]}.items():
        if any(kw in text for kw in kws):
            dangers.append(name)
    if dangers:
        data["environmental_dangers"] = ", ".join(dangers)

    return {k: v for k, v in data.items() if v is not None}


# ── Instant Critical Detection (zero latency) ───────────────

def detect_critical_instant(text: str) -> dict:
    """Instant keyword-based critical detection. Runs on every message with ZERO
    latency — no API calls. Returns severity info if critical indicators found.

    This runs BEFORE the AI responds, so responders get alerted immediately.
    """
    text_lower = text.lower()
    risk_factors = []
    severity = None
    priority = 10

    # CRITICAL indicators — immediate life threat
    critical_keywords = {
        "NOT BREATHING": ["not breathing", "stopped breathing", "can't breathe", "cant breathe",
                          "no breath", "choking", "suffocating", "no air"],
        "UNCONSCIOUS": ["unconscious", "not conscious", "passed out", "fainted",
                        "unresponsive", "not responding", "not waking", "collapsed",
                        "won't wake", "wont wake"],
        "NO PULSE": ["no pulse", "heart stopped", "cardiac arrest"],
        "HEAVY BLEEDING": ["bleeding heavily", "heavy bleeding", "lot of blood",
                           "blood everywhere", "won't stop bleeding", "losing blood",
                           "massive bleeding", "blood gushing"],
    }
    for factor, keywords in critical_keywords.items():
        if any(kw in text_lower for kw in keywords):
            risk_factors.append(factor)
            severity = "CRITICAL"
            priority = 1

    # HIGH indicators
    high_keywords = {
        "TRAPPED": ["trapped", "stuck under", "pinned", "buried", "under debris",
                     "can't move", "cant move", "crushed"],
        "CHEST PAIN": ["chest pain", "heart attack"],
        "HEAD INJURY": ["head injury", "head wound", "skull", "brain"],
        "FRACTURE": ["broken bone", "fracture", "broken leg", "broken arm"],
        "BURN": ["burned", "burning", "on fire", "burn victim"],
    }
    for factor, keywords in high_keywords.items():
        if any(kw in text_lower for kw in keywords):
            risk_factors.append(factor)
            if severity != "CRITICAL":
                severity = "HIGH"
                priority = min(priority, 3)

    # ENVIRONMENTAL DANGER escalation
    env_keywords = {
        "FIRE NEARBY": ["fire", "flames", "smoke", "burning building"],
        "FLOOD": ["flooding", "water rising", "flood water", "drowning"],
        "GAS LEAK": ["gas leak", "gas smell", "smell gas"],
        "COLLAPSE RISK": ["collapsing", "structure unstable", "building falling"],
        "EXPLOSION": ["explosion", "blast", "bomb"],
    }
    for factor, keywords in env_keywords.items():
        if any(kw in text_lower for kw in keywords):
            risk_factors.append(factor)
            if not severity:
                severity = "HIGH"
                priority = min(priority, 4)

    # MULTIPLE VICTIMS escalation
    import re as _re
    multi_match = _re.search(r"(\d+)\s*(?:people|persons?|victims?|injured|dead|casualties)", text_lower)
    if multi_match:
        n = int(multi_match.group(1))
        if n > 1:
            risk_factors.append(f"MULTIPLE VICTIMS ({n})")
            priority = max(1, priority - 1)

    # Child/elderly
    age_match = _re.search(r"(\d{1,3})\s*(?:years?\s*old|y/?o|months?\s*old)", text_lower)
    if age_match:
        age = int(age_match.group(1))
        if age < 5:
            risk_factors.append(f"INFANT/TODDLER (age {age})")
            priority = max(1, priority - 1)
        elif age < 12:
            risk_factors.append(f"CHILD (age {age})")
        elif age > 75:
            risk_factors.append(f"ELDERLY (age {age})")
            priority = max(1, priority - 1)

    if not risk_factors:
        return {}

    return {
        "severity": severity or "MODERATE",
        "priority": priority,
        "risk_factors": list(set(risk_factors)),
        "is_critical": severity == "CRITICAL",
    }


# ── AI Conversation Turn ─────────────────────────────────────

async def get_ai_response(session: ConversationSession) -> str:
    """
    Send conversation to AI and get response. Tries providers in order:
    1. Groq (free, fast — Llama 3)
    2. Minimax (fallback)
    3. Smart fallback
    """
    # Opening turn — use a simple greeting
    if session.turn_count == 0:
        opening = (
            "Hello, this is the 2020 AI Agent triage line. "
            "I'm here to help you report an emergency. "
            "Can you tell me what's happening?"
        )
        session.add_assistant_message(opening)
        return opening

    # Try Groq first (free, fast)
    response = await _groq_converse(session.messages)
    if response:
        session.ai_provider = "groq"
    else:
        # Fallback to Minimax
        response = await _minimax_converse(session.messages)
        if response:
            session.ai_provider = "minimax"
        else:
            # Last resort fallback
            response = _fallback_response(session)
            session.ai_provider = "fallback"

    # Check if AI completed the interview
    if "[TRIAGE_COMPLETE]" in response:
        _parse_completion(session, response)
    else:
        session.add_assistant_message(response)

    return response


# ── Groq AI (free, fast — Llama 3) ──────────────────────────

async def _groq_converse(messages: list[dict]) -> str | None:
    """Call Groq API with full conversation history. OpenAI-compatible format."""
    if not GROQ_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 500,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(GROQ_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]
            if content:
                logger.info("Groq response received (%d chars)", len(content))
                return content.strip()

    except httpx.HTTPStatusError as exc:
        logger.error("Groq HTTP error %s: %s", exc.response.status_code, exc.response.text[:200])
    except httpx.RequestError as exc:
        logger.error("Groq request error: %s", exc)
    except Exception as exc:
        logger.error("Groq unexpected error: %s", exc)

    return None


# ── Minimax AI ──────────────────────────────────────────────

async def _minimax_converse(messages: list[dict]) -> str | None:
    """Call Minimax AI with full conversation history."""
    if not MINIMAX_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MINIMAX_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 400,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(MINIMAX_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            base_resp = data.get("base_resp", {})
            if base_resp.get("status_code", 0) != 0:
                logger.error(
                    "Minimax error %s: %s",
                    base_resp.get("status_code"),
                    base_resp.get("status_msg", "unknown"),
                )
                return None

            choices = data.get("choices")
            if not choices:
                return None

            content = choices[0].get("message", {}).get("content", "")
            if content:
                logger.info("Minimax response received (%d chars)", len(content))
                return content.strip()

    except httpx.HTTPStatusError as exc:
        logger.error("Minimax HTTP error %s", exc.response.status_code)
    except httpx.RequestError as exc:
        logger.error("Minimax request error: %s", exc)
    except Exception as exc:
        logger.error("Minimax unexpected error: %s", exc)

    return None


# ── Smart Fallback (no AI available) ─────────────────────────

_TOPICS = {
    "situation": "Can you describe what happened? What is the emergency?",
    "conscious": "Is the person conscious and responsive?",
    "breathing": "Are they breathing normally?",
    "bleeding": "Is there any heavy bleeding?",
    "name": "What is the patient's name?",
    "age": "How old are they, approximately?",
    "location": "What is your exact location or address?",
    "trapped": "Is anyone trapped or unable to move?",
    "disaster": "What type of disaster is this — earthquake, flood, fire?",
    "victims": "How many people are injured?",
    "dangers": "Are there any environmental dangers nearby, like fire or gas leak?",
}

# Natural follow-up phrasing per topic (more conversational than _TOPICS)
_NATURAL_QUESTIONS = {
    "situation": [
        "Tell me what happened — describe the emergency situation.",
        "What's going on? Describe what you're seeing.",
        "Please describe the emergency. What happened?",
    ],
    "conscious": [
        "Is the injured person awake and responding to you?",
        "Can they talk to you? Are they conscious?",
        "Are they alert and responsive?",
    ],
    "breathing": [
        "Are they breathing? Can you see their chest moving?",
        "Check if they're breathing — is their chest rising and falling?",
        "Can you tell if they're breathing normally?",
    ],
    "bleeding": [
        "Is there any bleeding? How bad is it?",
        "Can you see any blood or wounds?",
        "Is anyone bleeding? Is it heavy or minor?",
    ],
    "name": [
        "Do you know the patient's name?",
        "What's the injured person's name?",
        "Can you tell me their name?",
    ],
    "age": [
        "How old are they? Even a rough estimate helps.",
        "About how old is the patient?",
        "Can you estimate their age?",
    ],
    "location": [
        "Where are you right now? Give me an address or landmark.",
        "What's your exact location? Street name, building, anything specific.",
        "Tell me your location so we can send help — an address or nearby landmark.",
    ],
    "trapped": [
        "Is anyone trapped or pinned down?",
        "Can the injured person move freely, or are they stuck?",
        "Is anyone unable to move or trapped under something?",
    ],
    "disaster": [
        "What caused this — earthquake, flood, fire, something else?",
        "What type of incident is this?",
        "Was this caused by a natural disaster or an accident?",
    ],
    "victims": [
        "How many people are hurt?",
        "Is it just one person, or are there multiple injured?",
        "How many victims are there?",
    ],
    "dangers": [
        "Is there any immediate danger around you — fire, gas leak, collapsing walls?",
        "Are there environmental hazards nearby?",
        "Is the area safe, or are there dangers like fire or flooding?",
    ],
}

_ESSENTIAL = {"situation", "conscious", "breathing", "location"}


def _detect_covered_topics(full_text: str) -> set[str]:
    """Analyze conversation text to determine which topics have been covered."""
    covered = set()
    t = full_text.lower()

    # Situation — any description of an emergency event
    if any(w in t for w in [
        "happened", "earthquake", "flood", "fire", "collapse", "explosion",
        "accident", "building", "injured", "hurt", "fell", "crash", "hit",
        "drowned", "burning", "destroyed", "damaged", "emergency", "disaster",
        "trapped", "bleeding", "broken", "wound", "attack", "shot", "stabbed",
        "car", "vehicle", "wreck", "pile", "rubble", "debris", "struck",
        "crushed", "buried", "swept", "tornado", "hurricane", "bomb",
    ]):
        covered.add("situation")

    # Consciousness
    if any(w in t for w in ["conscious", "responsive", "unconscious", "unresponsive", "awake", "talking", "alert", "not responding", "passed out", "fainted"]):
        covered.add("conscious")

    # Breathing
    if any(w in t for w in ["breathing", "not breathing", "breath", "suffocating", "choking", "gasping", "can't breathe", "stopped breathing"]):
        covered.add("breathing")

    # Bleeding
    if any(w in t for w in ["bleeding", "blood", "hemorrhage", "cut", "wound", "no bleeding", "not bleeding", "gash", "laceration"]):
        covered.add("bleeding")

    # Name
    if re.search(r"(?:name is|named|called|name\'s)\s+\w", t) or re.search(r"(?:his|her|the patient)\s+name\s", t):
        covered.add("name")

    # Age
    if re.search(r"\d{1,3}\s*(?:years?\s*old|y/?o)|(?:age|aged?|about|around)\s*\d|(?:child|baby|infant|elderly|old man|old woman|teenager|kid)", t):
        covered.add("age")

    # Location
    if any(w in t for w in ["street", "building", "zone", "district", "address", "floor", "road", "avenue", "block", "school", "hospital", "market", "shelter", "mosque", "church", "park", "highway", "intersection", "corner", "downtown", "north", "south", "east", "west", "apartment", "house", "home"]):
        covered.add("location")

    # Trapped
    if any(w in t for w in ["trapped", "stuck", "pinned", "stranded", "under debris", "under concrete", "not trapped", "can move", "can walk", "free", "on rooftop", "on the roof", "cut off", "buried"]):
        covered.add("trapped")

    # Disaster type
    if any(w in t for w in ["earthquake", "flood", "fire", "hurricane", "explosion", "collapse", "storm", "tsunami", "landslide", "tornado", "bombing"]):
        covered.add("disaster")

    # Victim count
    if re.search(r"\d+\s*(?:people|person|victim|injured|total|hurt|children|kids|adults|family)", t):
        covered.add("victims")
    if re.search(r"family of\s*\d+", t):
        covered.add("victims")
    number_words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    if any(f"{w} people" in t or f"{w} person" in t or f"{w} injured" in t or f"{w} victim" in t or f"{w} children" in t for w in number_words):
        covered.add("victims")
    if any(phrase in t for phrase in ["just her", "just him", "only one", "no one else", "nobody else", "alone", "just me", "one person", "single victim"]):
        covered.add("victims")

    # Dangers
    if any(w in t for w in ["gas leak", "danger", "fire", "flood", "collapse", "hazard", "risk", "no danger", "safe", "no hazard", "smoke", "toxic", "chemical"]):
        covered.add("dangers")

    return covered


def _extract_info_from_last_msg(last_msg: str) -> dict[str, str]:
    """Extract what the user just told us, to give a smart acknowledgment."""
    info = {}
    t = last_msg.lower()

    if any(w in t for w in ["not breathing", "stopped breathing", "can't breathe"]):
        info["breathing"] = "not breathing"
    elif any(w in t for w in ["breathing", "is breathing"]):
        info["breathing"] = "breathing"

    if any(w in t for w in ["unconscious", "unresponsive", "not conscious", "passed out", "fainted"]):
        info["conscious"] = "unconscious"
    elif any(w in t for w in ["conscious", "awake", "alert", "responsive", "talking"]):
        info["conscious"] = "conscious"

    if any(w in t for w in ["heavy bleeding", "lot of blood", "massive bleeding", "bleeding heavily"]):
        info["bleeding"] = "heavy bleeding"
    elif any(w in t for w in ["bleeding", "some blood", "cut", "wound"]):
        info["bleeding"] = "some bleeding"
    elif any(w in t for w in ["no bleeding", "not bleeding"]):
        info["bleeding"] = "no bleeding"

    if any(w in t for w in ["trapped", "stuck", "pinned", "buried", "under debris"]):
        info["trapped"] = "trapped"

    for dtype in ["earthquake", "flood", "fire", "explosion", "collapse", "hurricane", "storm"]:
        if dtype in t:
            info["disaster"] = dtype
            break

    return info


def _build_smart_acknowledgment(last_msg: str, covered_now: set, covered_before: set) -> str:
    """Build a natural-sounding acknowledgment of what the user just said."""
    new_info = covered_now - covered_before
    extracted = _extract_info_from_last_msg(last_msg)

    if not new_info and not extracted:
        return ""

    parts = []
    if "breathing" in extracted:
        if extracted["breathing"] == "not breathing":
            parts.append("Not breathing — that's critical, noted")
        else:
            parts.append("Okay, they're breathing")
    if "conscious" in extracted:
        if extracted["conscious"] == "unconscious":
            parts.append("unconscious — understood, that's serious")
        else:
            parts.append("conscious and responsive, good")
    if "bleeding" in extracted:
        if "heavy" in extracted["bleeding"]:
            parts.append("heavy bleeding noted")
        elif extracted["bleeding"] == "no bleeding":
            parts.append("no bleeding, okay")
        else:
            parts.append("noted the bleeding")
    if "trapped" in extracted:
        parts.append("they're trapped — I've noted that")
    if "disaster" in extracted:
        parts.append(f"{extracted['disaster']} situation")

    if parts:
        return f"{', '.join(parts).capitalize()}."
    elif new_info:
        return "Okay, I've noted that."
    return ""


def _is_medical_advice_request(text: str) -> bool:
    """Check if user is asking for medical advice."""
    t = text.lower()
    advice_phrases = [
        "what should i do", "how do i help", "what can i do",
        "how to help", "what do i do", "should i move",
        "how do i stop the bleeding", "should i give",
        "how to treat", "first aid", "what medicine",
        "should i perform", "how to do cpr", "ماذا أفعل",
    ]
    return any(phrase in t for phrase in advice_phrases)


def _fallback_response(session: ConversationSession) -> str:
    """
    Smart conversational fallback when no AI API is available.
    Uses context-aware responses, natural acknowledgments, and
    adaptive question flow.
    """
    import random

    turn = session.turn_count
    user_texts = [m["content"] for m in session.messages if m["role"] == "user" and not m["content"].startswith("[SYSTEM")]
    if not user_texts:
        return "I'm here to help. What's the emergency?"

    last_msg = user_texts[-1].strip()
    last_lower = last_msg.lower()
    full_text = " ".join(user_texts)

    # ── SAFETY: Medical advice requests ──────────────────
    if _is_medical_advice_request(last_lower):
        return "A trained human responder will contact you immediately. Please stay calm and stay on the line."

    # ── Handle greetings (only on first occurrence) ──────
    greetings = ["hello", "hi", "hey", "good morning", "good evening", "good afternoon",
                 "salam", "salaam", "marhaba", "ahlan", "yo", "howdy"]
    is_greeting = any(last_lower == g or last_lower.startswith(g + " ") or last_lower.startswith(g + ",") for g in greetings)

    # Track if we already handled a greeting
    ai_msgs = [m["content"] for m in session.messages if m["role"] == "assistant"]
    already_greeted = any("emergency" in m.lower() and ("hello" in m.lower() or "hi" in m.lower() or "here to help" in m.lower()) for m in ai_msgs)

    if is_greeting and not already_greeted:
        return "Hello! I'm the 2020 AI Agent operator. Please tell me — what is the emergency? What happened?"

    # If they keep saying hello/hi without describing anything
    if is_greeting and already_greeted:
        covered = _detect_covered_topics(full_text)
        if "situation" not in covered:
            return "I'm ready to help. I need you to describe the emergency — what happened and who is injured?"
        # They greeted again but we already have situation info — just continue
        pass

    # ── Handle very short/vague messages ─────────────────
    if len(last_lower.split()) <= 2 and not _detect_covered_topics(last_msg):
        covered = _detect_covered_topics(full_text)
        if "situation" not in covered:
            prompts = [
                "I need you to describe what happened. What's the emergency?",
                "Please tell me about the situation — who is hurt and what happened?",
                "To send the right help, I need to know what's going on. Can you describe the emergency?",
            ]
            return random.choice(prompts)

    # ── Handle yes/no answers intelligently ──────────────
    is_yes = last_lower in ("yes", "yeah", "yep", "correct", "affirmative", "yes they are", "yes he is", "yes she is", "نعم")
    is_no = last_lower in ("no", "nope", "negative", "no they're not", "no he's not", "no she's not", "لا")

    if is_yes or is_no:
        # Figure out what question they're answering from the last AI message
        last_ai = ai_msgs[-1].lower() if ai_msgs else ""
        if "conscious" in last_ai or "responsive" in last_ai or "awake" in last_ai:
            if is_yes:
                return "Good, they're conscious. Are they breathing normally?"
            else:
                return "Unconscious — that's critical information. Are they breathing at all?"
        elif "breathing" in last_ai:
            if is_yes:
                return "They're breathing, okay. Is there any bleeding?"
            else:
                return "Not breathing — this is very urgent. I've noted that. What's your exact location so we can dispatch help immediately?"
        elif "bleeding" in last_ai:
            if is_yes:
                return "Bleeding noted. Is it heavy bleeding or minor? And what is your location?"
            else:
                return "No bleeding, okay. What is your current location or address?"
        elif "trapped" in last_ai:
            if is_yes:
                return "They're trapped — noted. Can you describe exactly where they are?"
            else:
                return "Okay, not trapped. Can you move them to a safe area if needed?"
        elif "danger" in last_ai or "hazard" in last_ai:
            if is_yes:
                return "There are dangers nearby — please be careful. Can you describe what the hazards are?"
            else:
                return "Good, the area is relatively safe. Let me make sure I have everything I need."

    # ── Detect what's covered before and after this message ──
    text_before = " ".join(user_texts[:-1]) if len(user_texts) > 1 else ""
    covered_before = _detect_covered_topics(text_before) if text_before else set()
    covered_now = _detect_covered_topics(full_text)
    new_topics = covered_now - covered_before

    # ── Build contextual acknowledgment ──────────────────
    ack = _build_smart_acknowledgment(last_msg, covered_now, covered_before)

    # ── Check if we can complete ─────────────────────────
    has_essentials = _ESSENTIAL.issubset(covered_now)
    extra_covered = covered_now - _ESSENTIAL
    if has_essentials and (len(extra_covered) >= 2 or turn >= 5):
        return _fallback_complete(session)
    if turn >= 8:
        return _fallback_complete(session)

    # ── Find the next question to ask ────────────────────
    # Priority order: life-threatening first, then patient info, then details
    priority = ["situation", "breathing", "conscious", "location",
                "bleeding", "name", "age", "trapped", "disaster", "victims", "dangers"]

    next_topic = None
    for topic_id in priority:
        if topic_id not in covered_now:
            next_topic = topic_id
            break

    if next_topic is None:
        return _fallback_complete(session)

    # Pick a natural question variant
    question = random.choice(_NATURAL_QUESTIONS.get(next_topic, [_TOPICS[next_topic]]))

    # Combine acknowledgment + next question naturally
    if ack:
        # Don't double-ask if acknowledgment already implies the next topic
        return f"{ack} {question}"
    elif new_topics:
        # They gave us new info but ack was empty — simple bridge
        bridges = ["Got it.", "Understood.", "Noted.", "Thank you.", "Okay."]
        return f"{random.choice(bridges)} {question}"
    else:
        # No new info — they might be confused
        return question


def _fallback_complete(session: ConversationSession) -> str:
    """Extract structured data from conversation and build triage completion."""
    user_texts = [m["content"] for m in session.messages if m["role"] == "user" and not m["content"].startswith("[SYSTEM")]
    full_text = " ".join(user_texts).lower()
    all_raw = " ".join(user_texts)

    # Build a comprehensive situation description from all real user messages
    real_msgs = [t for t in user_texts if len(t.split()) > 3]
    situation_desc = " | ".join(real_msgs) if real_msgs else (user_texts[0] if user_texts else "No description")

    data: dict = {
        "patient_name": None, "age": None, "is_conscious": None,
        "is_breathing": None, "has_heavy_bleeding": None, "is_trapped": None,
        "location": None,
        "situation_description": situation_desc,
        "disaster_type": None, "num_victims": None, "environmental_dangers": None,
    }

    # Consciousness (negatives first)
    if any(w in full_text for w in ["unconscious", "unresponsive", "not conscious", "not responsive", "not responding"]):
        data["is_conscious"] = False
    elif any(w in full_text for w in ["conscious", "responsive", "talking", "awake", "alert", "responding"]):
        data["is_conscious"] = True

    # Breathing (negatives first)
    if any(w in full_text for w in ["not breathing", "stopped breathing", "no breathing", "can't breathe"]):
        data["is_breathing"] = False
    elif any(w in full_text for w in ["breathing", "labored", "is breathing"]):
        data["is_breathing"] = True

    # Bleeding
    if any(w in full_text for w in ["heavy bleeding", "bleeding heavily", "lot of blood", "massive bleeding", "deep cut"]):
        data["has_heavy_bleeding"] = True
    elif any(w in full_text for w in ["no bleeding", "not bleeding", "no blood"]):
        data["has_heavy_bleeding"] = False

    # Trapped (negatives first)
    if any(w in full_text for w in ["not trapped", "isn't trapped", "not stuck", "can walk", "can move", "free to move"]):
        data["is_trapped"] = False
    elif any(w in full_text for w in ["trapped", "stuck", "pinned", "stranded", "cannot move", "can't move", "under debris", "under concrete", "on rooftop", "on the roof", "on a roof", "cut off"]):
        data["is_trapped"] = True

    # Disaster type
    disaster_map = {
        "earthquake": ["earthquake", "quake"], "flood": ["flood", "flooding"],
        "fire": ["fire", "burning", "flames"], "hurricane": ["hurricane", "storm", "cyclone"],
        "explosion": ["explosion", "blast"], "building_collapse": ["building collapse", "collapsed"],
    }
    for dtype, kws in disaster_map.items():
        if any(kw in full_text for kw in kws):
            data["disaster_type"] = dtype
            break

    # Name — try multiple patterns
    name_patterns = [
        r"(?:name is|named|called|name's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"(?:name is|named|called|his name|her name)\s+(?:is\s+)?([a-z]+(?:\s+[a-z]+)*)",
        r"(?:father|mother|brother|sister|patient)\s+([A-Z][a-z]+)",
        r"(?:Mr\.|Mrs\.|Ms\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
    ]
    for pattern in name_patterns:
        m = re.search(pattern, all_raw, re.IGNORECASE)
        if m:
            name = m.group(1).strip().title()
            # Filter out common non-name words
            if name.lower() not in ("is", "the", "a", "an", "and", "or", "about", "age", "years", "old"):
                data["patient_name"] = name
                break

    # Age
    for pattern in [r"(\d{1,3})\s*(?:years?\s*old|y/?o)", r"(?:age|aged?|about|around)\s*(\d{1,3})", r"(?:he|she|patient)\s+is\s+(?:about\s+)?(\d{1,3})"]:
        m = re.search(pattern, full_text)
        if m:
            age = int(m.group(1))
            if 0 < age < 150:
                data["age"] = age
                break

    # Location — multiple patterns, prefer specific ones
    loc_patterns = [
        r"(?:address is|we are at|located at|location is|they are at)\s+(.{5,80}?)(?:\.|$)",
        # Match "Nile Road Building 12" or "Main Street Block 4" etc.
        r"([A-Z][a-z]+(?:\s+[A-Z]?[a-z]*)*\s+(?:Road|Street|St|Ave|Avenue|Blvd|Building|Block|Lane|Drive|District|Zone|Floor)(?:\s+\w+){0,3}?)(?:\.|$|,\s*(?:water|the|he|she|it|we|they|all))",
        r"(?:on|at|in|near)\s+(.{5,80}?(?:street|road|building|floor|block|avenue|zone|district|school|hospital|market|shelter|mosque|church)[^.]{0,20}?)(?:\.|$|,\s*(?:water|the|he|she|it|we|they|all))",
    ]
    for pattern in loc_patterns:
        m = re.search(pattern, all_raw, re.IGNORECASE)
        if m:
            loc = m.group(1).strip().rstrip(",. ")
            # Filter out obviously wrong matches
            if len(loc) > 4 and not loc.lower().startswith(("father", "mother", "the patient")):
                data["location"] = loc
                break

    # Victims — multiple patterns
    victims_patterns = [
        r"(\d+)\s*(?:people|persons?|victims?|injured|casualties|total|hurt|affected)",
        r"family of\s*(\d+)",
        r"(\d+)\s*(?:children|kids|adults|men|women)",
    ]
    for pattern in victims_patterns:
        m = re.search(pattern, full_text)
        if m:
            data["num_victims"] = int(m.group(1))
            break
    if data["num_victims"] is None:
        word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        for w, n in word_to_num.items():
            if re.search(rf"\b{w}\b\s*(?:people|persons?|victims?|injured|total|children|kids)", full_text):
                data["num_victims"] = n
                break
    if data["num_victims"] is None and any(p in full_text for p in ["just her", "just him", "only one", "no one else"]):
        data["num_victims"] = 1

    # Dangers
    dangers = []
    for name, kws in {"gas leak": ["gas leak", "gas smell"], "fire": ["fire", "flames"], "flood": ["flood"], "collapse risk": ["further collapse", "unstable", "risk of collapse"]}.items():
        if any(kw in full_text for kw in kws):
            dangers.append(name)
    if dangers:
        data["environmental_dangers"] = ", ".join(dangers)

    # ── Severity ──────
    severity, priority, risk_factors = "MODERATE", 5, []

    if data["is_breathing"] is False:
        severity, priority = "CRITICAL", 1
        risk_factors.append("NOT BREATHING")
    if data["is_conscious"] is False:
        severity, priority = "CRITICAL", 1
        risk_factors.append("UNCONSCIOUS")
    if data["is_trapped"]:
        risk_factors.append("TRAPPED")
        if severity != "CRITICAL":
            severity, priority = "HIGH", min(priority, 3)
    if data["has_heavy_bleeding"]:
        risk_factors.append("HEAVY BLEEDING")
        if severity != "CRITICAL":
            severity, priority = "HIGH", min(priority, 3)

    for w in ["not breathing", "no pulse", "cardiac arrest", "crush"]:
        if w in full_text and w.upper() not in risk_factors:
            severity, priority = "CRITICAL", min(priority, 2)
            risk_factors.append(w.upper())
    for w in ["fracture", "broken", "chest pain", "head injury", "cannot feel"]:
        if w in full_text and w.upper() not in risk_factors:
            if severity != "CRITICAL":
                severity, priority = "HIGH", min(priority, 3)
            risk_factors.append(w.upper())

    if data["is_trapped"] and data["has_heavy_bleeding"]:
        severity, priority = "CRITICAL", min(priority, 2)
    if data["age"] and data["age"] < 12:
        risk_factors.append(f"CHILD (age {data['age']})")
    if data["age"] and data["age"] > 65:
        risk_factors.append(f"ELDERLY (age {data['age']})")
    if data["environmental_dangers"]:
        priority = max(1, priority - 1)
        risk_factors.append("ENVIRONMENTAL HAZARDS")
    if data["num_victims"] and data["num_victims"] > 1:
        priority = max(1, priority - 1)
        risk_factors.append(f"MULTIPLE VICTIMS ({data['num_victims']})")

    data["severity"] = severity
    data["confidence"] = 0.55 if risk_factors else 0.35
    data["detected_risk_factors"] = list(set(risk_factors))
    data["reasoning"] = f"Analysis of {len(user_texts)} messages. {len(risk_factors)} risk factors identified."
    data["estimated_response_priority"] = priority
    data["needs_human_callback"] = True  # ALWAYS true — every report needs human follow-up

    json_str = json.dumps(data)
    return (
        "Thank you. I've logged this case and a human responder will follow up shortly. Stay safe.\n\n"
        f"[TRIAGE_COMPLETE]\n{json_str}"
    )


# ── Parse completion ─────────────────────────────────────────

def _parse_completion(session: ConversationSession, response: str) -> None:
    """Extract the triage data from a completion response."""
    parts = response.split("[TRIAGE_COMPLETE]")
    session.final_message = parts[0].strip()
    session.add_assistant_message(session.final_message)
    session.is_complete = True

    json_text = parts[1].strip() if len(parts) > 1 else ""
    try:
        json_text = re.sub(r"^```(?:json)?\s*", "", json_text)
        json_text = re.sub(r"\s*```$", "", json_text)
        session.extracted_data = json.loads(json_text)
        logger.info("Conversation %s: triage data extracted (%s)", session.session_id, session.ai_provider)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to parse triage JSON: %s", e)
        session.extracted_data = {
            "severity": "MODERATE", "confidence": 0.3,
            "detected_risk_factors": [],
            "reasoning": "Unable to parse AI response — manual review recommended.",
            "estimated_response_priority": 5, "needs_human_callback": True,
        }
