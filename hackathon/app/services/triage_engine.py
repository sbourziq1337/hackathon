"""
Triage classification engine — DATA COLLECTION & SEVERITY ONLY.

The AI classifies severity based on START triage principles.
It does NOT provide medical advice, treatment, or first-aid instructions.
All medical decisions are made by certified human responders.

Two classification paths:
  1. Minimax AI API  (primary)
  2. Keyword-based fallback  (offline)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx

from app.config import MINIMAX_API_KEY, MINIMAX_MODEL, MINIMAX_API_URL
from app.models.triage import (
    AIModel,
    InputSource,
    SeverityLevel,
    TriageReport,
)

logger = logging.getLogger(__name__)

# ── System prompt for Minimax AI ────────────────────────────

SYSTEM_PROMPT = """You are an AI triage CLASSIFICATION engine for a disaster emergency intake system.

Your ONLY role is to:
1. Analyze the emergency data collected from a caller
2. Classify the severity level
3. Identify risk factors
4. Determine response priority

You must NEVER provide medical advice, treatment instructions, or first-aid guidance.
You must NEVER diagnose conditions.
You are a DATA CLASSIFIER only.

Use START triage principles for classification:
- CRITICAL (Red): Not breathing, no pulse, unconscious, massive hemorrhage, trapped with crush injuries, cardiac arrest, drowning, severe burns >30%. Priority 1-2.
- HIGH (Orange): Fractures, moderate burns, chest pain, difficulty breathing, heavy bleeding (controlled), altered consciousness, spinal injury suspected. Priority 3-4.
- MODERATE (Yellow): Simple fractures, minor burns, lacerations, sprains, walking wounded with notable injuries. Priority 5-6.
- LOW (Green): Cuts, bruises, anxiety, minor sprains, no significant mechanism of injury. Priority 7-10.

Classification rules:
1. When in doubt, classify UP (never underestimate).
2. Not breathing or no pulse = always CRITICAL.
3. Children (age < 12) and elderly (age > 65) = bump severity one level up.
4. Trapped = bump severity one level up.
5. Multiple victims = increase priority.
6. Environmental dangers (fire, flood, collapse) = increase priority.

Respond ONLY with valid JSON (no markdown fences):
{
    "severity": "CRITICAL" | "HIGH" | "MODERATE" | "LOW",
    "confidence": <float 0.0-1.0>,
    "detected_risk_factors": ["<factor1>", ...],
    "reasoning": "<brief classification reasoning>",
    "estimated_response_priority": <int 1-10>,
    "needs_human_callback": true | false
}
"""


# ── Keyword-based fallback ──────────────────────────────────

CRITICAL_KEYWORDS = [
    "not breathing", "no pulse", "cardiac arrest", "unconscious",
    "massive bleeding", "massive hemorrhage", "crush", "trapped",
    "severe burn", "stroke", "anaphylaxis", "choking",
    "airway obstruction", "drowning", "electrocution", "amputation",
    "not conscious", "unresponsive",
    "لا يتنفس", "لا نبض", "سكتة قلبية", "فاقد الوعي",
    "نزيف حاد", "محاصر", "حروق شديدة", "غرق",
]

HIGH_KEYWORDS = [
    "fracture", "broken bone", "chest pain", "difficulty breathing",
    "head injury", "spinal", "moderate burn", "heavy bleeding",
    "altered consciousness", "seizure", "deep wound", "dislocation",
    "كسر", "ألم في الصدر", "صعوبة التنفس", "إصابة في الرأس",
    "نزيف غزير", "تشنج", "جرح عميق",
]

MODERATE_KEYWORDS = [
    "laceration", "sprain", "minor burn", "stitches", "swelling",
    "walking wounded", "pain", "bleeding", "wound", "cut",
    "جرح", "التواء", "حرق بسيط", "تورم", "ألم", "نزيف",
]

LOW_KEYWORDS = [
    "bruise", "scratch", "anxiety", "minor", "scrape",
    "sore", "tired", "scared", "stressed",
    "كدمة", "خدش", "قلق", "بسيط",
]

VULNERABILITY_KEYWORDS = [
    "child", "baby", "infant", "toddler", "elderly", "old man",
    "old woman", "pregnant", "disabled",
    "طفل", "رضيع", "مسن", "حامل",
]


def _keyword_classify(
    situation_text: str,
    is_conscious: bool | None = None,
    is_breathing: bool | None = None,
    has_heavy_bleeding: bool | None = None,
    is_trapped: bool | None = None,
    age: int | None = None,
) -> dict:
    """Classify using keyword matching on situation text + structured safety data."""
    text_lower = situation_text.lower()

    risk_factors = []

    # Direct safety checks override keywords
    if is_breathing is False:
        risk_factors.append("NOT BREATHING")
    if is_conscious is False:
        risk_factors.append("UNCONSCIOUS")
    if has_heavy_bleeding is True:
        risk_factors.append("HEAVY BLEEDING")
    if is_trapped is True:
        risk_factors.append("TRAPPED")

    critical_hits = [kw for kw in CRITICAL_KEYWORDS if kw in text_lower]
    high_hits = [kw for kw in HIGH_KEYWORDS if kw in text_lower]
    moderate_hits = [kw for kw in MODERATE_KEYWORDS if kw in text_lower]
    low_hits = [kw for kw in LOW_KEYWORDS if kw in text_lower]
    vuln_hits = [kw for kw in VULNERABILITY_KEYWORDS if kw in text_lower]

    risk_factors += critical_hits + high_hits

    # Determine base severity
    if is_breathing is False or is_conscious is False or critical_hits:
        severity = SeverityLevel.CRITICAL
        confidence = min(0.7 + 0.05 * len(critical_hits), 0.95)
        priority = 1
    elif has_heavy_bleeding is True or high_hits:
        severity = SeverityLevel.HIGH
        confidence = min(0.55 + 0.05 * len(high_hits), 0.80)
        priority = 3
    elif moderate_hits:
        severity = SeverityLevel.MODERATE
        confidence = min(0.45 + 0.05 * len(moderate_hits), 0.70)
        priority = 5
    elif low_hits:
        severity = SeverityLevel.LOW
        confidence = 0.45
        priority = 8
    else:
        severity = SeverityLevel.MODERATE
        confidence = 0.35
        priority = 5

    # Age-based vulnerability bump
    if age is not None:
        if age < 12:
            risk_factors.append(f"CHILD (age {age})")
        elif age > 65:
            risk_factors.append(f"ELDERLY (age {age})")

    if age is not None and (age < 12 or age > 65):
        if severity != SeverityLevel.CRITICAL:
            bump = {
                SeverityLevel.LOW: SeverityLevel.MODERATE,
                SeverityLevel.MODERATE: SeverityLevel.HIGH,
                SeverityLevel.HIGH: SeverityLevel.CRITICAL,
            }
            severity = bump.get(severity, severity)
            priority = max(1, priority - 1)

    # Vulnerability keywords bump
    if vuln_hits and severity != SeverityLevel.CRITICAL:
        bump = {
            SeverityLevel.LOW: SeverityLevel.MODERATE,
            SeverityLevel.MODERATE: SeverityLevel.HIGH,
            SeverityLevel.HIGH: SeverityLevel.CRITICAL,
        }
        severity = bump.get(severity, severity)
        priority = max(1, priority - 1)
        risk_factors.append(f"vulnerable: {', '.join(vuln_hits)}")

    # Trapped bump
    if is_trapped and severity != SeverityLevel.CRITICAL:
        bump = {
            SeverityLevel.LOW: SeverityLevel.MODERATE,
            SeverityLevel.MODERATE: SeverityLevel.HIGH,
            SeverityLevel.HIGH: SeverityLevel.CRITICAL,
        }
        severity = bump.get(severity, severity)
        priority = max(1, priority - 1)

    needs_callback = True  # ALWAYS true — every report needs human follow-up

    return {
        "severity": severity.value,
        "confidence": round(confidence, 2),
        "detected_risk_factors": list(set(risk_factors)),
        "reasoning": (
            f"Keyword classification: "
            f"{len(critical_hits)} critical, {len(high_hits)} high, "
            f"{len(moderate_hits)} moderate, {len(low_hits)} low indicators. "
            f"Safety: conscious={is_conscious}, breathing={is_breathing}, "
            f"heavy_bleeding={has_heavy_bleeding}, trapped={is_trapped}."
        ),
        "estimated_response_priority": priority,
        "needs_human_callback": needs_callback,
    }


# ── Minimax AI classification ──────────────────────────────

async def _minimax_classify(text: str) -> dict | None:
    """Call Minimax AI for severity classification only."""
    if not MINIMAX_API_KEY:
        logger.warning("MINIMAX_API_KEY not set — skipping AI classification.")
        return None

    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MINIMAX_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
        "max_tokens": 800,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(MINIMAX_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            base_resp = data.get("base_resp", {})
            if base_resp.get("status_code", 0) != 0:
                logger.error(
                    "Minimax API error %s: %s",
                    base_resp.get("status_code"),
                    base_resp.get("status_msg", "unknown"),
                )
                return None

            choices = data.get("choices")
            if not choices:
                logger.error("No choices in Minimax response.")
                return None

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                logger.error("Empty content from Minimax.")
                return None

            content = re.sub(r"^```(?:json)?\s*", "", content.strip())
            content = re.sub(r"\s*```$", "", content.strip())

            return json.loads(content)

    except httpx.HTTPStatusError as exc:
        logger.error("Minimax HTTP error %s: %s", exc.response.status_code, exc.response.text)
    except httpx.RequestError as exc:
        logger.error("Minimax request error: %s", exc)
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.error("Failed to parse Minimax response: %s", exc)

    return None


# ── Public API ──────────────────────────────────────────────

async def classify_intake(
    situation_description: str,
    input_source: InputSource,
    patient_name: str | None = None,
    age: int | None = None,
    gender: str | None = None,
    is_conscious: bool | None = None,
    is_breathing: bool | None = None,
    has_heavy_bleeding: bool | None = None,
    location: str | None = None,
    is_trapped: bool | None = None,
    indoor_outdoor: str | None = None,
    disaster_type: str | None = None,
    num_victims: int | None = None,
    environmental_dangers: str | None = None,
    conversation_transcript: str = "",
    caller_phone: str | None = None,
) -> TriageReport:
    """
    Classify an emergency intake and return a structured TriageReport.
    NO medical advice — severity classification and data collection only.
    """
    # Build enriched text for AI
    parts = [f"Situation: {situation_description}"]
    if is_conscious is not None:
        parts.append(f"Conscious: {'yes' if is_conscious else 'NO'}")
    if is_breathing is not None:
        parts.append(f"Breathing: {'yes' if is_breathing else 'NO'}")
    if has_heavy_bleeding is not None:
        parts.append(f"Heavy bleeding: {'YES' if has_heavy_bleeding else 'no'}")
    if is_trapped is not None:
        parts.append(f"Trapped: {'YES' if is_trapped else 'no'}")
    if age is not None:
        parts.append(f"Age: {age}")
    if disaster_type:
        parts.append(f"Disaster: {disaster_type}")
    if num_victims is not None:
        parts.append(f"Victims: {num_victims}")
    if environmental_dangers:
        parts.append(f"Dangers: {environmental_dangers}")
    if location:
        parts.append(f"Location: {location}")

    enriched_text = "\n".join(parts)

    # Try Minimax AI first
    ai_result = await _minimax_classify(enriched_text)
    ai_model = AIModel.MINIMAX

    if ai_result is None:
        logger.info("Using keyword fallback engine.")
        ai_result = _keyword_classify(
            situation_description,
            is_conscious=is_conscious,
            is_breathing=is_breathing,
            has_heavy_bleeding=has_heavy_bleeding,
            is_trapped=is_trapped,
            age=age,
        )
        ai_model = AIModel.FALLBACK_KEYWORD

    # Build vital_signs_reported for spec compliance
    vital_signs = {
        "breathing": "yes" if is_breathing is True else ("no" if is_breathing is False else "unknown"),
        "conscious": "yes" if is_conscious is True else ("no" if is_conscious is False else "unknown"),
        "bleeding": "severe" if has_heavy_bleeding is True else ("none" if has_heavy_bleeding is False else "unknown"),
    }

    # Geocode location
    from app.services.geocoding import geocode_location
    lat, lng = None, None
    if location:
        coords = await geocode_location(location)
        if coords:
            lat, lng = coords

    return TriageReport(
        input_source=input_source,
        patient_name=patient_name,
        age=age,
        gender=gender,
        is_conscious=is_conscious,
        is_breathing=is_breathing,
        has_heavy_bleeding=has_heavy_bleeding,
        location=location,
        latitude=lat,
        longitude=lng,
        is_trapped=is_trapped,
        indoor_outdoor=indoor_outdoor,
        situation_description=situation_description,
        disaster_type=disaster_type,
        num_victims=num_victims,
        environmental_dangers=environmental_dangers,
        severity=SeverityLevel(ai_result.get("severity", "MODERATE")),
        confidence=float(ai_result.get("confidence", 0.5)),
        detected_risk_factors=ai_result.get("detected_risk_factors", []),
        reasoning=ai_result.get("reasoning", ""),
        estimated_response_priority=int(ai_result.get("estimated_response_priority", 5)),
        needs_human_callback=True,  # ALWAYS true per spec
        vital_signs_reported=vital_signs,
        conversation_transcript=conversation_transcript,
        caller_phone=caller_phone,
        ai_model=ai_model,
    )
