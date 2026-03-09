import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import markdown
from weasyprint import HTML

from app.constants import SERVICE_DISPLAY_NAMES

logger = logging.getLogger(__name__)

SERVICE_SHORT_NAMES = {
    "EntraId": "Entra ID",
    "ExchangeOnline": "Exchange Online",
    "SharePointOnline": "SharePoint Online",
    "MicrosoftTeams": "MS Teams",
    "Purview": "Purview",
    "Defender": "Defender",
    "Intune": "Intune",
    "AdminPortal": "Admin Portal",
    "Microsoft365": "Microsoft 365",
    "Unknown": "General",
}

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "report.html"

COLOR_FAIL = "#c62828"
COLOR_MANUAL = "#e65100"
COLOR_PASS = "#2e7d32"
COLOR_PRIMARY = "#1e3a5f"


def _md_to_html(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=["tables", "fenced_code"])


def _render_donut_svg(fail: int, manual: int, passing: int) -> str:
    """SVG donut chart for overall findings distribution."""
    total = fail + manual + passing or 1
    cx, cy, r, sw = 80, 80, 56, 24
    circumference = 2 * math.pi * r
    segments = [(fail, COLOR_FAIL), (manual, COLOR_MANUAL), (passing, COLOR_PASS)]
    circles = []
    offset = 0.0
    for count, color in segments:
        if count == 0:
            continue
        dash = (count / total) * circumference
        gap = circumference - dash
        circles.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
            f'stroke-width="{sw}" stroke-dasharray="{dash:.2f} {gap:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}"/>'
        )
        offset += dash
    total_display = fail + manual + passing
    return (
        f'<svg viewBox="0 0 160 160" width="160" height="160" xmlns="http://www.w3.org/2000/svg">'
        f'<g transform="rotate(-90 {cx} {cy})">{"".join(circles)}</g>'
        f'<text x="{cx}" y="{cy - 8}" text-anchor="middle" font-family="Arial" '
        f'font-size="24" font-weight="bold" fill="{COLOR_PRIMARY}">{total_display}</text>'
        f'<text x="{cx}" y="{cy + 10}" text-anchor="middle" font-family="Arial" '
        f'font-size="9" fill="#666">Total Checks</text>'
        f'</svg>'
    )


def _render_service_bars(by_service: dict) -> str:
    """Horizontal stacked bar chart per service."""
    if not by_service:
        return "<p>No service data available.</p>"
    bar_width = 220
    rows = []
    for service, counts in by_service.items():
        fail = counts.get("fail", 0)
        manual = counts.get("manual", 0)
        passing = counts.get("pass", 0)
        total = fail + manual + passing or 1
        fw = fail / total * bar_width
        mw = manual / total * bar_width
        pw = passing / total * bar_width
        display = SERVICE_SHORT_NAMES.get(service, service)
        bar = (
            f'<svg width="{bar_width}" height="16" xmlns="http://www.w3.org/2000/svg">'
            f'<rect x="0" y="0" width="{fw:.1f}" height="16" fill="{COLOR_FAIL}"/>'
            f'<rect x="{fw:.1f}" y="0" width="{mw:.1f}" height="16" fill="{COLOR_MANUAL}"/>'
            f'<rect x="{fw + mw:.1f}" y="0" width="{pw:.1f}" height="16" fill="{COLOR_PASS}"/>'
            f'</svg>'
        )
        rows.append(
            f'<tr>'
            f'<td style="width:120px;padding:5px 10px 5px 0;font-size:8.5pt;'
            f'color:{COLOR_PRIMARY};font-weight:500">{display}</td>'
            f'<td style="padding:5px 8px">{bar}</td>'
            f'<td style="width:36px;text-align:right;color:{COLOR_FAIL};font-size:8pt;'
            f'font-weight:700;padding:5px 4px">{fail}</td>'
            f'<td style="width:36px;text-align:right;color:{COLOR_MANUAL};font-size:8pt;'
            f'font-weight:700;padding:5px 4px">{manual}</td>'
            f'<td style="width:36px;text-align:right;color:{COLOR_PASS};font-size:8pt;'
            f'font-weight:700;padding:5px 4px">{passing}</td>'
            f'</tr>'
        )
    header = (
        f'<tr>'
        f'<th style="text-align:left;font-size:7.5pt;color:#666;font-weight:500;'
        f'padding:0 10px 6px 0;background:none;border:none">Service</th>'
        f'<th style="font-size:7.5pt;color:#666;font-weight:500;padding:0 8px 6px;'
        f'background:none;border:none">Distribution</th>'
        f'<th style="text-align:right;font-size:7.5pt;color:{COLOR_FAIL};font-weight:700;'
        f'padding:0 4px 6px;background:none;border:none">Fail</th>'
        f'<th style="text-align:right;font-size:7.5pt;color:{COLOR_MANUAL};font-weight:700;'
        f'padding:0 4px 6px;background:none;border:none">Manual</th>'
        f'<th style="text-align:right;font-size:7.5pt;color:{COLOR_PASS};font-weight:700;'
        f'padding:0 4px 6px;background:none;border:none">Pass</th>'
        f'</tr>'
    )
    return (
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead>{header}</thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table>'
    )


def _render_passing_table(passing_controls: list) -> str:
    if not passing_controls:
        return "<p>No passing controls recorded.</p>"
    rows = "".join(
        f'<tr>'
        f'<td style="width:130px;font-size:8pt;color:#555">{c["service"]}</td>'
        f'<td style="font-size:8.5pt;font-weight:500;color:#1e3a5f">{c["title"]}</td>'
        f'<td style="font-size:8pt;color:#444">{c["description"]}</td>'
        f'</tr>'
        for c in passing_controls
    )
    return (
        f'<table style="width:100%;border-collapse:collapse;font-size:8.5pt;margin:3mm 0">'
        f'<thead><tr>'
        f'<th style="width:130px;background:#2e7d32;color:#fff;padding:5px 8px;font-size:8pt">Service</th>'
        f'<th style="background:#2e7d32;color:#fff;padding:5px 8px;font-size:8pt">Control</th>'
        f'<th style="background:#2e7d32;color:#fff;padding:5px 8px;font-size:8pt">Description</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
    )


def _render_manual_table(manual_controls: list) -> str:
    if not manual_controls:
        return "<p>No manual review items recorded.</p>"
    rows = "".join(
        f'<tr>'
        f'<td style="width:100px;font-size:8pt;color:#555;vertical-align:top">{c["service"]}</td>'
        f'<td style="width:160px;font-size:8.5pt;font-weight:500;color:#1e3a5f;vertical-align:top">{c["title"]}</td>'
        f'<td style="width:50px;font-size:8pt;color:#e65100;font-weight:600;text-align:center;vertical-align:top">{c["severity"]}</td>'
        f'<td style="font-size:8pt;color:#444;vertical-align:top;word-wrap:break-word;overflow-wrap:break-word">{c["description"]}</td>'
        f'</tr>'
        for c in manual_controls
    )
    return (
        f'<table style="width:100%;border-collapse:collapse;font-size:8.5pt;margin:3mm 0;table-layout:fixed">'
        f'<thead><tr>'
        f'<th style="width:100px;background:#e65100;color:#fff;padding:5px 8px;font-size:8pt">Service</th>'
        f'<th style="width:160px;background:#e65100;color:#fff;padding:5px 8px;font-size:8pt">Control</th>'
        f'<th style="width:50px;background:#e65100;color:#fff;padding:5px 8px;font-size:8pt;text-align:center">Severity</th>'
        f'<th style="background:#e65100;color:#fff;padding:5px 8px;font-size:8pt">What to Verify</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
    )


def render_html(company: str, analysis: dict, job_id: str) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    stats = analysis.get("_stats", {"total": {"fail": 0, "manual": 0, "pass": 0}, "by_service": {}})

    synthesis_html = _md_to_html(analysis.get("synthesis", ""))
    donut_svg = _render_donut_svg(
        stats["total"]["fail"],
        stats["total"]["manual"],
        stats["total"]["pass"],
    )
    service_bars = _render_service_bars(stats.get("by_service", {}))
    passing_table = _render_passing_table(stats.get("passing_controls", []))
    manual_table = _render_manual_table(stats.get("manual_controls", []))

    sections_html = ""
    for key, display in SERVICE_DISPLAY_NAMES.items():
        if key in analysis:
            content_html = _md_to_html(analysis[key])
            sections_html += (
                f'<div class="section" id="{key}">'
                f'<h2>{display}</h2>{content_html}'
                f'</div>\n'
            )

    html = template.replace("COMPANY_PLACEHOLDER", company)
    html = html.replace("DATE_PLACEHOLDER", datetime.now(timezone.utc).strftime("%B %d, %Y"))
    html = html.replace("SYNTHESIS_PLACEHOLDER", synthesis_html)
    html = html.replace("SERVICE_SECTIONS_PLACEHOLDER", sections_html)
    html = html.replace("DONUT_CHART_PLACEHOLDER", donut_svg)
    html = html.replace("SERVICE_BARS_PLACEHOLDER", service_bars)
    html = html.replace("PASSING_TABLE_PLACEHOLDER", passing_table)
    html = html.replace("MANUAL_TABLE_PLACEHOLDER", manual_table)
    html = html.replace("FAIL_COUNT", str(stats["total"]["fail"]))
    html = html.replace("MANUAL_COUNT", str(stats["total"]["manual"]))
    html = html.replace("PASS_COUNT", str(stats["total"]["pass"]))

    return html


def generate_pdf(job_id: str, company: str, analysis: dict) -> str:
    out_dir = f"/tmp/audit_jobs/{job_id}"
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = f"{out_dir}/report_{job_id}.pdf"

    html_content = render_html(company=company, analysis=analysis, job_id=job_id)

    logger.info("Generating PDF for job %s", job_id)
    HTML(string=html_content).write_pdf(pdf_path)
    logger.info("PDF generated: %s", pdf_path)

    return pdf_path
