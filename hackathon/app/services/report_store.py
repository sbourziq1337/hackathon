"""
In-memory report store with thread-safe access.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.models.triage import CallbackStatus, InputSource, SeverityLevel, TriageReport


class ReportStore:
    """Thread-safe in-memory store for triage reports."""

    def __init__(self) -> None:
        self._reports: list[TriageReport] = []
        self._lock = asyncio.Lock()

    async def add(self, report: TriageReport) -> None:
        async with self._lock:
            self._reports.append(report)

    async def update(self, report_id: str, **fields) -> TriageReport | None:
        """Update specific fields on an existing report. Returns the updated report."""
        async with self._lock:
            for r in self._reports:
                if r.report_id == report_id:
                    for key, value in fields.items():
                        if hasattr(r, key) and value is not None:
                            setattr(r, key, value)
                    return r
        return None

    async def get_all(
        self,
        severity: Optional[SeverityLevel] = None,
        input_source: Optional[InputSource] = None,
        callback_status: Optional[CallbackStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TriageReport]:
        """Retrieve reports with optional filtering, newest first."""
        async with self._lock:
            filtered = list(reversed(self._reports))

            if severity is not None:
                filtered = [r for r in filtered if r.severity == severity]
            if input_source is not None:
                filtered = [r for r in filtered if r.input_source == input_source]
            if callback_status is not None:
                filtered = [r for r in filtered if r.callback_status == callback_status]

            return filtered[offset : offset + limit]

    async def get_by_id(self, report_id: str) -> Optional[TriageReport]:
        async with self._lock:
            for r in self._reports:
                if r.report_id == report_id:
                    return r
        return None

    async def count(self) -> int:
        async with self._lock:
            return len(self._reports)

    async def severity_counts(self) -> dict[str, int]:
        async with self._lock:
            counts = {s.value: 0 for s in SeverityLevel}
            for r in self._reports:
                counts[r.severity.value] += 1
            return counts

    async def callback_counts(self) -> dict[str, int]:
        """Return count of reports per callback status."""
        async with self._lock:
            counts = {s.value: 0 for s in CallbackStatus}
            for r in self._reports:
                counts[r.callback_status.value] += 1
            return counts

    async def pending_callbacks(self) -> list[TriageReport]:
        """Return reports that need human callback, highest priority first."""
        async with self._lock:
            pending = [
                r for r in self._reports
                if r.needs_human_callback and r.callback_status == CallbackStatus.PENDING
            ]
            return sorted(pending, key=lambda r: r.estimated_response_priority)


store = ReportStore()
