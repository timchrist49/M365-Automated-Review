import logging
import time
from celery.exceptions import SoftTimeLimitExceeded
from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, JobStatus

logger = logging.getLogger(__name__)


def _send_failure_alert(job_id: str, email: str, company: str, error: str):
    """Non-blocking admin alert — failure here must never mask the original error."""
    try:
        from app.services.email_sender import send_admin_alert
        send_admin_alert(
            subject=f"[M365 Audit] Job FAILED — {company}",
            body=(
                f"An audit job has failed.\n\n"
                f"Job ID:  {job_id}\n"
                f"Company: {company}\n"
                f"Email:   {email}\n\n"
                f"Error:\n{error}\n\n"
                f"Check the worker logs for the full traceback."
            ),
        )
    except Exception as exc:
        logger.warning("Could not send failure alert for job %s: %s", job_id, exc)


def _update_job_status(job_id: str, status: JobStatus, error_msg: str = None):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = status
            if error_msg:
                job.error_msg = error_msg
            db.commit()
    finally:
        db.close()


@celery_app.task(bind=True, name="execute_audit")
def execute_audit(self, job_id: str, tenant_id: str):
    """
    Main audit orchestration task.
    Steps: run Monkey365 → analyze with OpenAI → generate PDF → email client
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        email = job.email
        company = job.company
    finally:
        db.close()

    sp_object_id = None

    try:
        # Step 1: Assign admin roles in the customer's tenant, then run Monkey365
        _update_job_status(job_id, JobStatus.RUNNING)
        from app.services.graph_admin import assign_audit_roles
        sp_object_id = assign_audit_roles(tenant_id)

        # Wait for Azure AD role assignments to propagate before scanning.
        # Role assignments are eventually consistent — without this delay Monkey365
        # hits Exchange/SharePoint/Teams APIs before the new roles are active and
        # gets empty results, producing only manual checks for those services.
        logger.info("Waiting 90s for role assignment propagation before scanning...")
        time.sleep(90)

        from app.services.monkey365 import run_monkey365
        json_output_path = run_monkey365(job_id, tenant_id)

        # Step 2: Analyze findings with OpenAI
        _update_job_status(job_id, JobStatus.ANALYZING)
        from app.services.analyzer import analyze_findings
        analysis = analyze_findings(json_output_path)

        # Guard: if the scan collected no findings at all, skip PDF and notify client
        stats = analysis.get("_stats", {})
        total = stats.get("total", {})
        total_findings = total.get("fail", 0) + total.get("manual", 0) + total.get("pass", 0)
        if total_findings == 0:
            logger.warning("Job %s produced zero findings — sending no-findings notification", job_id)
            from app.services.email_sender import send_no_findings_email
            send_no_findings_email(email, company)
            _update_job_status(job_id, JobStatus.COMPLETE)
            logger.info("No-findings notification sent for job %s", job_id)
            return

        # Step 3: Generate PDF
        from app.services.pdf_generator import generate_pdf
        pdf_path = generate_pdf(job_id, company, analysis)

        # Step 4: Email report
        from app.services.email_sender import send_report_email
        send_report_email(email, company, pdf_path)

        _update_job_status(job_id, JobStatus.COMPLETE)
        logger.info("Audit complete for job %s", job_id)

    except SoftTimeLimitExceeded:
        msg = "Audit exceeded the 40-minute time limit and was stopped."
        logger.error("Soft time limit exceeded for job %s", job_id)
        _update_job_status(job_id, JobStatus.FAILED, error_msg=msg)
        _send_failure_alert(job_id, email, company, msg)
        raise

    except Exception as exc:
        logger.exception("Audit failed for job %s: %s", job_id, exc)
        _update_job_status(job_id, JobStatus.FAILED, error_msg=str(exc))
        _send_failure_alert(job_id, email, company, str(exc))
        raise

    finally:
        # Always attempt cleanup — remove our SP from the customer's tenant
        # regardless of success or failure, so no lingering high-privilege access remains.
        # Runs even if the task raised, but only if we have an SP ID to clean up.
        if sp_object_id:
            try:
                from app.services.graph_admin import remove_service_principal
                remove_service_principal(tenant_id, sp_object_id)
            except Exception as cleanup_exc:
                # Log but never let cleanup failure propagate — the audit result stands
                logger.warning(
                    "SP cleanup failed for tenant %s (SP %s): %s — manual removal may be needed",
                    tenant_id, sp_object_id, cleanup_exc,
                )
