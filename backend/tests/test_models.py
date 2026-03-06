from app.config import settings

def test_settings_has_required_fields():
    assert hasattr(settings, "AZURE_CLIENT_ID")
    assert hasattr(settings, "REDIS_URL")
    assert hasattr(settings, "OPENAI_API_KEY")
    assert hasattr(settings, "CERT_PATH")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Job, JobStatus

def test_job_model_creates_with_uuid():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    from app.database import Base
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    job = Job(email="client@test.com", company="Test Corp")
    db.add(job)
    db.commit()
    db.refresh(job)

    assert job.id is not None
    assert len(job.id) == 36  # UUID4 format
    assert job.status == JobStatus.PENDING
    assert job.tenant_id is None
    db.close()
