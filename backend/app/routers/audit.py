import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job, JobStatus

router = APIRouter()

MICROSOFT_ADMINCONSENT_URL = "https://login.microsoftonline.com/common/adminconsent"


class StartAuditRequest(BaseModel):
    email: EmailStr
    company: str


class StartAuditResponse(BaseModel):
    job_id: str
    consent_url: str


@router.post("/start", response_model=StartAuditResponse)
def start_audit(request: StartAuditRequest, db: Session = Depends(get_db)):
    # Rate limit: one active job per email
    existing = db.query(Job).filter(
        Job.email == request.email,
        Job.status.notin_([JobStatus.COMPLETE, JobStatus.FAILED])
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="An audit for this email is already in progress.")

    job_id = str(uuid.uuid4())
    job = Job(id=job_id, email=request.email, company=request.company)
    db.add(job)
    db.commit()

    params = urlencode({
        "client_id": settings.AZURE_CLIENT_ID,
        "redirect_uri": settings.REDIRECT_URI,
        "state": job_id,
    })
    consent_url = f"{MICROSOFT_ADMINCONSENT_URL}?{params}"

    return StartAuditResponse(job_id=job_id, consent_url=consent_url)


@router.get("/status/{job_id}")
def get_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job.id, "status": job.status, "company": job.company}
