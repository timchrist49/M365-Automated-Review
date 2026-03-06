import json
import pytest
from unittest.mock import patch, MagicMock
from app.services.monkey365 import build_ps_script, parse_monkey365_output


def test_build_ps_script_contains_required_params():
    script = build_ps_script(
        job_id="test-job-123",
        tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        cert_path="/app/certs/monkey365.pfx",
        client_id="client-id-here",
        out_dir="/tmp/monkey365/test-job-123"
    )
    assert "monkey365" in script
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in script
    assert "ExchangeOnline" in script
    assert "SharePointOnline" in script
    assert "AdminPortal" in script
    assert "MicrosoftTeams" in script
    assert "Purview" in script
    assert "JSON" in script
    assert "$env:CERT_PASSWORD" in script  # password never hardcoded


def test_parse_monkey365_output_extracts_all_services(tmp_path):
    """Legacy dict format is returned as-is."""
    fake_output = {
        "EntraId": {"checks": [{"name": "MFA", "status": "FAIL", "severity": "High"}]},
        "ExchangeOnline": {"checks": [{"name": "DKIM", "status": "PASS", "severity": "None"}]},
        "SharePointOnline": {"checks": []},
        "MicrosoftTeams": {"checks": []},
        "Purview": {"checks": []},
        "AdminPortal": {"checks": []},
    }
    output_file = tmp_path / "monkey365_output.json"
    output_file.write_text(json.dumps(fake_output))

    result = parse_monkey365_output(str(tmp_path))
    assert "EntraId" in result
    assert "ExchangeOnline" in result
    assert result["EntraId"]["checks"][0]["name"] == "MFA"


def test_parse_monkey365_output_handles_ocsf_list_format(tmp_path):
    """OCSF list format (Monkey365 v0.9+) is grouped by provider."""
    ocsf_output = [
        {"unmapped": {"provider": "EntraID"}, "statusCode": "fail", "activityName": "MFA not enforced"},
        {"unmapped": {"provider": "EntraID"}, "statusCode": "pass", "activityName": "Guest access restricted"},
        {"unmapped": {"provider": "ExchangeOnline"}, "statusCode": "fail", "activityName": "DKIM disabled"},
    ]
    # Monkey365 nests output: {out_dir}/{uuid}/json/*.json
    nested = tmp_path / "some-uuid" / "json"
    nested.mkdir(parents=True)
    (nested / "monkey365_output.json").write_text(json.dumps(ocsf_output))

    result = parse_monkey365_output(str(tmp_path))
    # "EntraID" should be normalised to "EntraId"
    assert "EntraId" in result
    assert "ExchangeOnline" in result
    assert len(result["EntraId"]) == 2
    assert len(result["ExchangeOnline"]) == 1
