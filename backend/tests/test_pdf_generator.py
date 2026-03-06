import os
import pytest
from unittest.mock import patch
from app.services.pdf_generator import generate_pdf, render_html


def test_render_html_includes_company_name():
    analysis = {
        "synthesis": "## Executive Summary\nThis tenant has several issues.",
        "EntraId": "## Entra ID\nSome findings here.",
    }
    html = render_html(company="Acme Corp", analysis=analysis, job_id="test-123")
    assert "Acme Corp" in html
    assert "Executive Summary" in html
    assert "Entra ID" in html


def test_render_html_includes_all_service_sections():
    services = ["EntraId", "ExchangeOnline", "SharePointOnline", "MicrosoftTeams", "Purview", "AdminPortal"]
    analysis = {svc: f"## {svc} findings" for svc in services}
    analysis["synthesis"] = "## Summary"
    html = render_html(company="Corp", analysis=analysis, job_id="j1")
    for svc in services:
        assert svc in html
