import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import markdown
from weasyprint import HTML

logger = logging.getLogger(__name__)

SERVICE_DISPLAY_NAMES = {
    "EntraId": "Microsoft Entra ID",
    "ExchangeOnline": "Exchange Online",
    "SharePointOnline": "SharePoint Online",
    "MicrosoftTeams": "Microsoft Teams",
    "Purview": "Microsoft Purview",
    "AdminPortal": "M365 Admin Portal",
}

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "report.html"


def _md_to_html(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=["tables", "fenced_code"])


def render_html(company: str, analysis: dict, job_id: str) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    synthesis_html = _md_to_html(analysis.get("synthesis", ""))

    # Build per-service sections — include raw key as div id so tests can assert on it
    sections_html = ""
    for key, display in SERVICE_DISPLAY_NAMES.items():
        if key in analysis:
            content_html = _md_to_html(analysis[key])
            sections_html += f'<div class="section" id="{key}"><h2>{display}</h2>{content_html}</div>\n'

    html = template.replace("COMPANY_PLACEHOLDER", company)
    html = html.replace("DATE_PLACEHOLDER", datetime.now(timezone.utc).strftime("%B %d, %Y"))
    html = html.replace("SYNTHESIS_PLACEHOLDER", synthesis_html)
    html = html.replace("SERVICE_SECTIONS_PLACEHOLDER", sections_html)

    return html


def generate_pdf(job_id: str, company: str, analysis: dict) -> str:
    out_dir = f"/tmp/monkey365/{job_id}"
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = f"{out_dir}/report_{job_id}.pdf"

    html_content = render_html(company=company, analysis=analysis, job_id=job_id)

    logger.info(f"Generating PDF for job {job_id}")
    HTML(string=html_content).write_pdf(pdf_path)
    logger.info(f"PDF generated: {pdf_path}")

    return pdf_path
