"""
Integration test: verifies full flow with mocked external services.
Does NOT call Microsoft, OpenAI, PowerShell, or SMTP.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app


def test_full_flow_start_to_callback():
    # Use follow_redirects=False so we can inspect the 302 redirect headers.
    # The autouse setup_test_db fixture applies the DB override to `app` before
    # this function runs, so creating the client here is safe.
    client = TestClient(app, follow_redirects=False)

    # Step 1: Start audit
    start_resp = client.post("/api/start", json={
        "email": "integration@test.com",
        "company": "Integration Test Corp"
    })
    assert start_resp.status_code == 200
    job_id = start_resp.json()["job_id"]
    consent_url = start_resp.json()["consent_url"]
    assert job_id
    assert "adminconsent" in consent_url

    # Step 2: Simulate Microsoft callback with consent
    with patch("app.routers.auth.run_audit_task") as mock_task:
        callback_resp = client.get(
            f"/auth/callback?tenant=cccccccc-0000-0000-0000-000000000003&state={job_id}"
        )
    assert callback_resp.status_code == 302
    assert "thank-you" in callback_resp.headers["location"]
    mock_task.assert_called_once_with(job_id, "cccccccc-0000-0000-0000-000000000003")

    # Step 3: Check job status (follow redirects is fine here — it's a JSON endpoint)
    status_resp = client.get(f"/api/status/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "CONSENTED"


def test_health_endpoint():
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
