"""
Full integration test suite for the 2020 AI Agent.

Run with:  python tests/test_integration.py
Requires the server to be running on http://localhost:8000
"""

from __future__ import annotations

import json
import sys

import httpx

BASE = "http://localhost:8000"

passed = 0
failed = 0


def report(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    extra = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{extra}")


def main() -> None:
    global passed, failed
    client = httpx.Client(base_url=BASE, timeout=30.0)

    # ────────────────────────────────────────────────────────
    print("\n=== 1. Health Check ===")
    r = client.get("/api/health")
    report("GET /api/health returns 200", r.status_code == 200)
    data = r.json()
    report("Response has status=ok", data.get("status") == "ok")
    report("Response has service name", "2020 AI Agent" in data.get("service", ""))
    report("Response has timestamp", len(data.get("timestamp", "")) > 10)
    report("Response has version", data.get("version") == "1.0.0")

    # ────────────────────────────────────────────────────────
    print("\n=== 2. Text Triage — CRITICAL (simple message format) ===")
    r = client.post("/api/triage/text", json={
        "message": "Man not breathing, massive hemorrhage, trapped under rubble, unconscious",
        "location": "Zone A, Block 3",
        "disaster_type": "earthquake",
        "num_victims": 2,
    })
    report("POST /api/triage/text returns 200", r.status_code == 200)
    data = r.json()
    report("severity is CRITICAL", data["severity"] == "CRITICAL")
    report("input_source is text", data["input_source"] == "text")
    report("needs_human_callback is True", data["needs_human_callback"] is True)
    report("location preserved", data["location"] == "Zone A, Block 3")
    report("disaster_type preserved", data["disaster_type"] == "earthquake")
    report("num_victims preserved", data["num_victims"] == 2)
    report("report_id is present", len(data.get("report_id", "")) > 10)
    report("timestamp is present", len(data.get("timestamp", "")) > 10)
    report("has detected_risk_factors", len(data.get("detected_risk_factors", [])) > 0)
    report("confidence is float 0-1", 0 <= data.get("confidence", -1) <= 1)
    report("priority is 1 or 2 (highest)", data.get("estimated_response_priority") in (1, 2))
    report("has vital_signs_reported", "breathing" in data.get("vital_signs_reported", {}))
    report("status is pending", data.get("status") == "pending")
    critical_id = data["report_id"]

    # ────────────────────────────────────────────────────────
    print("\n=== 3. Text Triage — HIGH ===")
    r = client.post("/api/triage/text", json={
        "message": "Woman with a suspected fracture in her leg and a deep wound on her arm, heavy bleeding",
        "location": "Field hospital B",
    })
    data = r.json()
    report("severity is HIGH", data["severity"] == "HIGH")
    report("needs_human_callback is True", data["needs_human_callback"] is True)

    # ────────────────────────────────────────────────────────
    print("\n=== 4. Text Triage — MODERATE ===")
    r = client.post("/api/triage/text", json={
        "message": "I have a sprain in my ankle and a small cut that might need stitches",
    })
    data = r.json()
    report("severity is MODERATE", data["severity"] == "MODERATE")
    report("needs_human_callback is True", data["needs_human_callback"] is True)

    # ────────────────────────────────────────────────────────
    print("\n=== 5. Text Triage — LOW ===")
    r = client.post("/api/triage/text", json={
        "message": "Just a small bruise and feeling a bit scared",
    })
    data = r.json()
    report("severity is LOW", data["severity"] == "LOW")
    report("needs_human_callback is True", data["needs_human_callback"] is True)

    # ────────────────────────────────────────────────────────
    print("\n=== 6. Text Triage — Vulnerability Bump (child) ===")
    r = client.post("/api/triage/text", json={
        "message": "A child has a painful sprain and a wound that is bleeding",
    })
    data = r.json()
    report("child bumps severity (at least HIGH)", data["severity"] in ("HIGH", "CRITICAL"))

    # ────────────────────────────────────────────────────────
    print("\n=== 7. Text Triage — Arabic Input ===")
    r = client.post("/api/triage/text", json={
        "message": "\u0637\u0641\u0644 \u0641\u0627\u0642\u062f \u0627\u0644\u0648\u0639\u064a \u0648\u0644\u0627 \u064a\u062a\u0646\u0641\u0633 \u0628\u0639\u062f \u0627\u0646\u0647\u064a\u0627\u0631 \u0627\u0644\u0645\u0628\u0646\u0649",
        "disaster_type": "earthquake",
    })
    data = r.json()
    report("Arabic CRITICAL detected", data["severity"] == "CRITICAL")

    # ────────────────────────────────────────────────────────
    print("\n=== 8. Input Validation ===")
    r = client.post("/api/triage/text", json={"message": ""})
    report("Empty message returns 422", r.status_code == 422)

    r = client.post("/api/triage/text", json={})
    report("Missing message returns 422", r.status_code == 422)

    # ────────────────────────────────────────────────────────
    print("\n=== 9. Structured Text Intake ===")
    r = client.post("/api/triage/text", json={
        "situation_description": "Person collapsed after earthquake, heavy bleeding from leg",
        "is_conscious": False,
        "is_breathing": True,
        "has_heavy_bleeding": True,
        "patient_name": "Ahmed",
        "age": 45,
        "location": "Building C, Floor 2",
        "is_trapped": True,
        "disaster_type": "earthquake",
    })
    report("Structured intake returns 200", r.status_code == 200)
    data = r.json()
    report("Structured: severity is CRITICAL", data["severity"] == "CRITICAL")
    report("Structured: patient_name preserved", data["patient_name"] == "Ahmed")

    # ────────────────────────────────────────────────────────
    print("\n=== 10. Report History ===")
    r = client.get("/api/reports")
    report("GET /api/reports returns 200", r.status_code == 200)
    reports_list = r.json()
    report("Multiple reports exist", len(reports_list) >= 5)
    report("Newest first (desc order)", reports_list[0]["timestamp"] >= reports_list[-1]["timestamp"])

    # ────────────────────────────────────────────────────────
    print("\n=== 11. Report Filtering ===")
    r = client.get("/api/reports", params={"severity": "CRITICAL"})
    critical_reports = r.json()
    report("Filter by CRITICAL works", all(x["severity"] == "CRITICAL" for x in critical_reports))
    report("At least 1 CRITICAL report", len(critical_reports) >= 1)

    r = client.get("/api/reports", params={"severity": "LOW"})
    low_reports = r.json()
    report("Filter by LOW works", all(x["severity"] == "LOW" for x in low_reports))

    # ────────────────────────────────────────────────────────
    print("\n=== 12. Single Report Lookup ===")
    r = client.get(f"/api/reports/{critical_id}")
    report("GET report by ID returns 200", r.status_code == 200)
    report("Correct report returned", r.json()["report_id"] == critical_id)

    r = client.get("/api/reports/nonexistent-uuid")
    report("Nonexistent ID returns 404", r.status_code == 404)

    # ────────────────────────────────────────────────────────
    print("\n=== 13. Report Stats ===")
    r = client.get("/api/reports/stats")
    report("GET /api/reports/stats returns 200", r.status_code == 200)
    stats = r.json()
    report("Has total_reports", stats.get("total_reports", 0) > 0)
    report("Has severity_distribution", "CRITICAL" in stats.get("severity_distribution", {}))

    # ────────────────────────────────────────────────────────
    print("\n=== 14. Status Update ===")
    r = client.patch(f"/api/reports/{critical_id}/status", json={"status": "in_progress"})
    report("PATCH status returns 200", r.status_code == 200)
    report("Status updated to in_progress", r.json().get("status") == "in_progress")

    r = client.patch(f"/api/reports/{critical_id}/status", json={"status": "resolved"})
    report("PATCH status to resolved returns 200", r.status_code == 200)

    r = client.patch(f"/api/reports/{critical_id}/status", json={"status": "invalid"})
    report("Invalid status returns 400", r.status_code == 400)

    # ────────────────────────────────────────────────────────
    print("\n=== 15. Chat Triage (Conversational) ===")
    r = client.post("/api/triage/chat", json={
        "message": "There's been an earthquake, a building collapsed and someone is trapped!"
    })
    report("POST /api/triage/chat returns 200", r.status_code == 200)
    chat_data = r.json()
    report("Has session_id", len(chat_data.get("session_id", "")) > 0)
    report("Has ai_response", len(chat_data.get("ai_response", "")) > 0)
    report("is_complete is bool", isinstance(chat_data.get("is_complete"), bool))

    if not chat_data.get("is_complete") and chat_data.get("session_id"):
        # Continue conversation
        r = client.post("/api/triage/chat", json={
            "session_id": chat_data["session_id"],
            "message": "Yes, the person is conscious but not breathing, heavy bleeding from the leg. Location is Main Street Building 5."
        })
        report("Continue chat returns 200", r.status_code == 200)

    # ────────────────────────────────────────────────────────
    print("\n=== 16. Voice Triage — Bad File Type ===")
    r = client.post(
        "/api/triage/voice",
        files={"audio": ("test.txt", b"not audio", "text/plain")},
    )
    report("Invalid audio type returns 400", r.status_code == 400)

    # ────────────────────────────────────────────────────────
    print("\n=== 17. Voice Triage — Empty File ===")
    r = client.post(
        "/api/triage/voice",
        files={"audio": ("test.wav", b"", "audio/wav")},
    )
    report("Empty audio returns 400", r.status_code == 400)

    # ────────────────────────────────────────────────────────
    print("\n=== 18. Authentication ===")
    r = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "admin123",
    })
    report("Login returns 200", r.status_code == 200)
    login_data = r.json()
    report("Login returns token", len(login_data.get("token", "")) > 0)

    r = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrongpassword",
    })
    report("Bad password returns 401", r.status_code == 401)

    # ────────────────────────────────────────────────────────
    print("\n=== 19. OpenAPI Docs ===")
    r = client.get("/docs")
    report("Swagger UI available", r.status_code == 200)
    r = client.get("/openapi.json")
    report("OpenAPI schema available", r.status_code == 200)
    schema = r.json()
    report("Schema has paths", len(schema.get("paths", {})) > 5)

    # ────────────────────────────────────────────────────────
    print("\n=== 20. needs_human_callback is ALWAYS true ===")
    for rpt in reports_list:
        if not rpt.get("needs_human_callback"):
            report("ALL reports have needs_human_callback=true", False, f"Report {rpt['report_id']} has false")
            break
    else:
        report("ALL reports have needs_human_callback=true", True)

    # ────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"RESULTS:  {passed} passed,  {failed} failed,  {passed + failed} total")
    print(f"{'='*50}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
