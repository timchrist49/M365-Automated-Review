import re
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job, JobStatus

router = APIRouter()

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def run_audit_task(job_id: str, tenant_id: str):
    """Import and dispatch Celery task. Separated for testability."""
    from app.tasks.audit_task import execute_audit
    execute_audit.delay(job_id, tenant_id)


@router.get("/callback")
def oauth_callback(
    state: str = "",
    tenant: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    frontend_base = settings.APP_BASE_URL

    if error:
        return RedirectResponse(url=f"{frontend_base}/error?reason=consent_denied", status_code=302)

    if not tenant or not UUID_RE.match(tenant):
        return RedirectResponse(url=f"{frontend_base}/error?reason=invalid_tenant", status_code=302)

    if not state:
        return RedirectResponse(url=f"{frontend_base}/error?reason=missing_state", status_code=302)

    job = db.query(Job).filter(Job.id == state).first()
    if not job or job.status != JobStatus.PENDING:
        return RedirectResponse(url=f"{frontend_base}/error?reason=invalid_job", status_code=302)

    # Store tenant_id and advance state
    job.tenant_id = tenant
    job.status = JobStatus.CONSENTED
    db.commit()

    # Dispatch async audit job
    run_audit_task(job.id, tenant)

    return RedirectResponse(url=f"{frontend_base}/thank-you?email={job.email}", status_code=302)
