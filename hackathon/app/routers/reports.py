"""
Report history and management routes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.models.triage import CallbackStatus, InputSource, ReportStatus, SeverityLevel, TriageReport
from app.services.pdf_generator import generate_single_report_pdf, generate_summary_pdf
from app.services.report_store import store

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class StatusUpdateRequest(BaseModel):
    status: str  # "in_progress" or "resolved"


class OperatorMessageRequest(BaseModel):
    """Body for POST /api/reports/{id}/message — send message to victim via Telegram."""
    message: str
    sender_name: str = "Responder"


@router.get("/stats")
async def report_stats() -> dict:
    """Summary statistics."""
    return {
        "total_reports": await store.count(),
        "severity_distribution": await store.severity_counts(),
        "callback_status": await store.callback_counts(),
    }


@router.get("/pending")
async def pending_callbacks() -> list[TriageReport]:
    """Get reports that need human callback, priority-ordered."""
    return await store.pending_callbacks()


@router.get("/pdf/summary")
async def download_summary_pdf() -> Response:
    """Download summary PDF."""
    reports = await store.get_all(limit=500)
    if not reports:
        raise HTTPException(status_code=404, detail="No reports available.")
    stats = {
        "total_reports": await store.count(),
        "severity_distribution": await store.severity_counts(),
    }
    pdf_bytes = await generate_summary_pdf(reports, stats)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=triage_summary.pdf"},
    )


# ── PDF Export (spec endpoint) — MUST be above /{report_id} to avoid route conflict
@router.get("/export/pdf")
async def export_all_reports_pdf(
    severity: Optional[SeverityLevel] = Query(None),
) -> Response:
    """Generate and return a PDF summary of all reports (or filtered subset)."""
    reports = await store.get_all(severity=severity, limit=500)
    if not reports:
        raise HTTPException(status_code=404, detail="No reports available.")
    stats = {
        "total_reports": await store.count(),
        "severity_distribution": await store.severity_counts(),
    }
    pdf_bytes = await generate_summary_pdf(reports, stats)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=triage_export.pdf"},
    )


@router.get("", response_model=list[TriageReport])
async def list_reports(
    severity: Optional[SeverityLevel] = Query(None),
    input_source: Optional[InputSource] = Query(None),
    callback_status: Optional[CallbackStatus] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[TriageReport]:
    """List reports with optional filters."""
    return await store.get_all(
        severity=severity,
        input_source=input_source,
        callback_status=callback_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{report_id}", response_model=TriageReport)
async def get_report(report_id: str) -> TriageReport:
    """Get single report."""
    report = await store.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@router.get("/{report_id}/pdf")
async def download_report_pdf(report_id: str) -> Response:
    """Download PDF for a single report."""
    report = await store.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    pdf_bytes = await generate_single_report_pdf(report)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=triage_{report_id[:8]}.pdf"},
    )


# ── Status Update (spec endpoint) ──────────────────────────

@router.patch("/{report_id}/status")
async def update_report_status(report_id: str, body: StatusUpdateRequest) -> dict:
    """
    Update a report's status.
    Valid transitions: "pending" → "in_progress" → "resolved"
    """
    valid_statuses = {"pending", "in_progress", "resolved"}
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    report = await store.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    report.status = ReportStatus(body.status)
    # Also sync the callback_status field for backward compat
    status_to_callback = {
        "pending": CallbackStatus.PENDING,
        "in_progress": CallbackStatus.IN_PROGRESS,
        "resolved": CallbackStatus.RESOLVED,
    }
    if body.status in status_to_callback:
        report.callback_status = status_to_callback[body.status]

    from app.services.events import event_manager
    await event_manager.broadcast("callback_update", report)

    return {"report_id": report_id, "status": body.status}


# ── Human→Victim Chat (Telegram bridge) ────────────────────

@router.post("/{report_id}/message")
async def send_message_to_victim_endpoint(report_id: str, body: OperatorMessageRequest) -> dict:
    """Send a message from a human operator on the dashboard to the victim via Telegram."""
    report = await store.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    from app.services.telegram_bot import send_message_to_victim
    sent = await send_message_to_victim(report_id, body.message, body.sender_name)
    if not sent:
        raise HTTPException(status_code=400, detail="Could not send message. Victim may not be on Telegram or bot is not running.")

    return {"status": "sent", "report_id": report_id}
