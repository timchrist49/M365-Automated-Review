import pytest
from unittest.mock import patch, MagicMock
from app.services.email_sender import build_email_message


def test_build_email_message_has_correct_fields():
    msg = build_email_message(
        to_email="client@corp.com",
        company="Corp Inc",
        pdf_path="/tmp/fake.pdf",
        from_email="assessments@myco.com",
        from_name="My Company",
    )
    assert msg["To"] == "client@corp.com"
    assert "Corp Inc" in msg["Subject"]
    assert msg["From"].startswith("My Company")
