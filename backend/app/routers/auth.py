import logging
import re
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job, JobStatus

router = APIRouter()
logger = logging.getLogger(__name__)

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def run_audit_task(job_id: str, tenant_id: str):
    """Import and dispatch Celery task. Separated for testability."""
    from app.tasks.audit_task import execute_audit
    execute_audit.delay(job_id, tenant_id)


@router.get("/callback")
def oauth_callback(
    request: Request,
    state: str = "",
    tenant: str = "",
    error: str = "",
    error_description: str = "",
    admin_consent: str = "",
    db: Session = Depends(get_db),
):
    # Log all query params so we can debug what Microsoft sends
    logger.warning("OAuth callback received. Params: %s", dict(request.query_params))

    frontend_base = settings.APP_BASE_URL

    if error:
        logger.warning("Consent error: %s - %s", error, error_description)

        # AADSTS650051 = SP already exists in the tenant (re-consent after a previous scan).
        # Not a real failure — the customer already has our app installed from a prior run.
        # Extract the tenant ID from the error description and proceed normally.
        if "AADSTS650051" in error_description:
            tenant_match = re.search(
                r"tenant\s+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                error_description, re.I,
            )
            if tenant_match and state:
                tenant = tenant_match.group(1)
                error = ""  # clear so normal flow continues below
                logger.info(
                    "SP already present in tenant %s — skipping re-consent, proceeding with job %s",
                    tenant, state,
                )
            else:
                logger.warning("AADSTS650051 but could not extract tenant ID from error_description")
                return RedirectResponse(url=f"{frontend_base}/error?reason=consent_denied", status_code=302)
        else:
            return RedirectResponse(url=f"{frontend_base}/error?reason=consent_denied", status_code=302)

    if not tenant or not UUID_RE.match(tenant):
        logger.warning("Invalid tenant param: %r", tenant)
        return RedirectResponse(url=f"{frontend_base}/error?reason=invalid_tenant", status_code=302)

    if not state:
        logger.warning("Missing state param")
        return RedirectResponse(url=f"{frontend_base}/error?reason=missing_state", status_code=302)

    job = db.query(Job).filter(Job.id == state).first()
    if not job:
        logger.warning("Job not found for state: %s", state)
        return RedirectResponse(url=f"{frontend_base}/error?reason=invalid_job", status_code=302)
    if job.status != JobStatus.PENDING:
        logger.warning("Job %s has status %s, expected PENDING", job.id, job.status)
        return RedirectResponse(url=f"{frontend_base}/error?reason=invalid_job", status_code=302)

    # Store tenant_id and advance state
    job.tenant_id = tenant
    job.status = JobStatus.CONSENTED
    db.commit()
    logger.info("Job %s consented by tenant %s, dispatching audit", job.id, tenant)

    # Dispatch async audit job
    run_audit_task(job.id, tenant)

    return RedirectResponse(url=f"{frontend_base}/thank-you?email={job.email}", status_code=302)
