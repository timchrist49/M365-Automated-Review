import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.models import Job, JobStatus
from app.database import SessionLocal

client = TestClient(app, follow_redirects=False)


def _create_job(job_id: str):
    db = SessionLocal()
    job = Job(id=job_id, email="test@client.com", company="Test Corp")
    db.add(job)
    db.commit()
    db.close()


def test_callback_valid_consent_queues_job():
    job_id = "aaaaaaaa-0000-0000-0000-000000000001"
    _create_job(job_id)

    with patch("app.routers.auth.run_audit_task") as mock_task:
        response = client.get(
            f"/auth/callback?tenant=bbbbbbbb-0000-0000-0000-000000000002&state={job_id}"
        )
    assert response.status_code == 302
    assert "/thank-you" in response.headers["location"]


def test_callback_missing_tenant_returns_error():
    response = client.get("/auth/callback?state=some-job-id")
    assert response.status_code == 302
    assert "error" in response.headers["location"]


def test_callback_invalid_job_id_returns_error():
    response = client.get("/auth/callback?tenant=bbbbbbbb-0000-0000-0000-000000000002&state=nonexistent-job")
    assert response.status_code == 302
    assert "error" in response.headers["location"]
