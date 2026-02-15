"""
In-memory call session manager for multi-turn phone conversations.

Each phone call has a session (keyed by Twilio CallSid) that tracks:
- Current question step
- All collected answers
- Full conversation transcript
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# The structured interview questions (in order)
QUESTIONS = [
    {
        "id": "conscious",
        "question": "Is the person conscious? Please answer yes or no.",
        "type": "bool",
    },
    {
        "id": "breathing",
        "question": "Is the person breathing? Please answer yes or no.",
        "type": "bool",
    },
    {
        "id": "bleeding",
        "question": "Is there heavy bleeding? Please answer yes or no.",
        "type": "bool",
    },
    {
        "id": "name",
        "question": "What is the patient's full name?",
        "type": "text",
    },
    {
        "id": "age",
        "question": "How old is the patient?",
        "type": "number",
    },
    {
        "id": "location",
        "question": "What is your exact location or address?",
        "type": "text",
    },
    {
        "id": "trapped",
        "question": "Is the person trapped? Yes or no.",
        "type": "bool",
    },
    {
        "id": "situation",
        "question": "Please describe what happened.",
        "type": "text",
    },
    {
        "id": "disaster",
        "question": "What type of disaster is this? For example, earthquake, flood, fire, or explosion.",
        "type": "text",
    },
    {
        "id": "victims",
        "question": "How many people are injured?",
        "type": "number",
    },
    {
        "id": "dangers",
        "question": "Are there any environmental dangers nearby, such as fire, rising water, or risk of collapse? Please describe or say none.",
        "type": "text",
    },
]


def _parse_bool(text: str) -> bool | None:
    """Parse yes/no from speech. Check negatives FIRST to avoid false positives."""
    t = text.lower().strip()
    # Check negatives first (longer/more specific phrases)
    no_phrases = [
        "not conscious", "not breathing", "unconscious", "unresponsive",
        "he is not", "she is not", "they are not", "isn't", "aren't",
        "no", "nope", "negative", "not really", "I don't think so",
    ]
    for w in no_phrases:
        if w in t:
            return False
    yes_phrases = [
        "yes", "yeah", "yep", "correct", "affirmative",
        "he is", "she is", "they are", "breathing", "conscious",
    ]
    for w in yes_phrases:
        if w in t:
            return True
    return None


def _parse_number(text: str) -> int | None:
    """Extract number from speech, handling compound numbers like 'forty five'."""
    import re
    t = text.lower().strip()

    # Try digits first
    match = re.search(r'\d+', t)
    if match:
        return int(match.group())

    # Word-to-number mapping
    tens = {
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    }
    ones = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9,
    }
    teens = {
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19,
    }

    # Check compound: "forty five" → 45
    result = 0
    found = False
    for word, val in tens.items():
        if word in t:
            result += val
            found = True
            break
    for word, val in ones.items():
        if word in t:
            result += val
            found = True
            break
    if found and result > 0:
        return result

    # Check teens
    for word, val in teens.items():
        if word in t:
            return val

    # Check "hundred"
    if "hundred" in t:
        return 100

    return None


class CallSession:
    """Tracks a single phone call's interview progress."""

    def __init__(self, call_sid: str, caller: str):
        self.call_sid = call_sid
        self.caller = caller
        self.step = 0
        self.answers: dict = {}
        self.transcript_lines: list[str] = []
        self.created_at = datetime.now(timezone.utc).isoformat()

    @property
    def is_complete(self) -> bool:
        return self.step >= len(QUESTIONS)

    @property
    def current_question(self) -> dict | None:
        if self.step < len(QUESTIONS):
            return QUESTIONS[self.step]
        return None

    def record_answer(self, speech: str) -> None:
        """Record the caller's answer for the current step and advance."""
        q = self.current_question
        if q is None:
            return

        qid = q["id"]
        qtype = q["type"]

        # Parse by type
        if qtype == "bool":
            parsed = _parse_bool(speech)
            self.answers[qid] = parsed
        elif qtype == "number":
            parsed = _parse_number(speech)
            self.answers[qid] = parsed
        else:
            self.answers[qid] = speech.strip()

        # Add to transcript
        self.transcript_lines.append(f"AI: {q['question']}")
        self.transcript_lines.append(f"Caller: {speech}")

        self.step += 1

    @property
    def full_transcript(self) -> str:
        return "\n".join(self.transcript_lines)

    def get_structured_data(self) -> dict:
        """Return collected data mapped to triage fields."""
        a = self.answers
        return {
            "is_conscious": a.get("conscious"),
            "is_breathing": a.get("breathing"),
            "has_heavy_bleeding": a.get("bleeding"),
            "patient_name": a.get("name"),
            "age": a.get("age"),
            "location": a.get("location"),
            "is_trapped": a.get("trapped"),
            "situation_description": a.get("situation", "No description provided"),
            "disaster_type": a.get("disaster"),
            "num_victims": a.get("victims"),
            "environmental_dangers": a.get("dangers"),
        }


class CallSessionManager:
    """Manages active call sessions."""

    def __init__(self):
        self._sessions: dict[str, CallSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, call_sid: str, caller: str = "") -> CallSession:
        async with self._lock:
            if call_sid not in self._sessions:
                self._sessions[call_sid] = CallSession(call_sid, caller)
                logger.info("New call session: %s from %s", call_sid, caller)
            return self._sessions[call_sid]

    async def remove(self, call_sid: str) -> None:
        async with self._lock:
            self._sessions.pop(call_sid, None)

    async def count(self) -> int:
        async with self._lock:
            return len(self._sessions)


# Module-level singleton
session_manager = CallSessionManager()
