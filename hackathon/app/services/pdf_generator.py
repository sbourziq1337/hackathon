"""
PDF report generator using Playwright (headless Chromium).

Renders an HTML template to PDF for individual reports or summary dashboards.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

from app.config import REPORTS_DIR
from app.models.triage import TriageReport

logger = logging.getLogger(__name__)

# Jinja2 template environment
_template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
_jinja_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)


async def _render_html_to_pdf(html: str) -> bytes:
    """Render an HTML string to PDF bytes using Playwright Chromium."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20px", "bottom": "20px", "left": "20px", "right": "20px"},
        )
        await browser.close()
    return pdf_bytes


async def generate_single_report_pdf(report: TriageReport) -> bytes:
    """Generate a PDF for a single triage report."""
    template = _jinja_env.get_template("report.html")
    html = template.render(report=report)
    pdf = await _render_html_to_pdf(html)
    logger.info("Generated single-report PDF (%d bytes) for %s", len(pdf), report.report_id)
    return pdf


async def generate_summary_pdf(
    reports: list[TriageReport],
    stats: dict,
) -> bytes:
    """Generate a summary PDF with severity distribution and all reports."""
    template = _jinja_env.get_template("report.html")
    html = template.render(
        reports=reports,
        stats=stats,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    pdf = await _render_html_to_pdf(html)
    logger.info("Generated summary PDF (%d bytes) for %d reports", len(pdf), len(reports))
    return pdf


async def save_pdf(pdf_bytes: bytes, filename: str) -> str:
    """Save PDF bytes to the reports directory and return the file path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    logger.info("PDF saved to %s", filepath)
    return filepath
