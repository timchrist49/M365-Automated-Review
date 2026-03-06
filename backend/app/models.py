import uuid
from datetime import datetime, UTC
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, Text, Enum
from app.database import Base


class JobStatus(str, PyEnum):
    PENDING = "PENDING"
    CONSENTED = "CONSENTED"
    RUNNING = "RUNNING"
    ANALYZING = "ANALYZING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    tenant_id = Column(String(36), nullable=True)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    error_msg = Column(Text, nullable=True)
