from app.config import settings

def test_settings_has_required_fields():
    assert hasattr(settings, "AZURE_CLIENT_ID")
    assert hasattr(settings, "REDIS_URL")
    assert hasattr(settings, "OPENAI_API_KEY")
    assert hasattr(settings, "CERT_PATH")
