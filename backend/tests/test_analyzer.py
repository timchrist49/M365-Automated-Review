import json
import pytest
from unittest.mock import patch, MagicMock
from app.services.analyzer import chunk_findings_by_service, build_chunk_prompt


def test_chunk_findings_by_service_returns_all_services():
    raw = {
        "EntraId": {"checks": [{"name": "MFA"}]},
        "ExchangeOnline": {"checks": []},
        "SharePointOnline": {"checks": []},
        "MicrosoftTeams": {"checks": []},
        "Purview": {"checks": []},
        "AdminPortal": {"checks": []},
    }
    chunks = chunk_findings_by_service(raw)
    assert set(chunks.keys()) == {"EntraId", "ExchangeOnline", "SharePointOnline", "MicrosoftTeams", "Purview", "AdminPortal"}


def test_build_chunk_prompt_includes_service_name():
    prompt = build_chunk_prompt("ExchangeOnline", {"checks": [{"name": "DKIM", "status": "FAIL"}]})
    assert "ExchangeOnline" in prompt
    assert "DKIM" in prompt
    assert "Critical" in prompt   # severity levels mentioned in prompt
    assert "remediation" in prompt.lower()
