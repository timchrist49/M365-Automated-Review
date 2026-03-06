import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_start_returns_consent_url():
    response = client.post("/api/start", json={
        "email": "admin@clientcorp.com",
        "company": "Client Corp"
    })
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "consent_url" in data
    assert "adminconsent" in data["consent_url"]
    assert "client_id" in data["consent_url"]


def test_start_rejects_duplicate_email():
    client.post("/api/start", json={"email": "dup@test.com", "company": "Corp A"})
    response = client.post("/api/start", json={"email": "dup@test.com", "company": "Corp B"})
    assert response.status_code == 409


def test_start_rejects_invalid_email():
    response = client.post("/api/start", json={"email": "not-an-email", "company": "Corp"})
    assert response.status_code == 422


def test_status_returns_job():
    res = client.post("/api/start", json={"email": "status@test.com", "company": "StatusCorp"})
    job_id = res.json()["job_id"]
    status_res = client.get(f"/api/status/{job_id}")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "PENDING"


def test_status_unknown_job_returns_404():
    res = client.get("/api/status/nonexistent-id")
    assert res.status_code == 404
