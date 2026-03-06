import logging
from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, JobStatus

logger = logging.getLogger(__name__)


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

    try:
        # Step 1: Run Monkey365
        _update_job_status(job_id, JobStatus.RUNNING)
        from app.services.monkey365 import run_monkey365
        json_output_path = run_monkey365(job_id, tenant_id)

        # Step 2: Analyze findings with OpenAI
        _update_job_status(job_id, JobStatus.ANALYZING)
        from app.services.analyzer import analyze_findings
        analysis = analyze_findings(json_output_path)

        # Step 3: Generate PDF
        from app.services.pdf_generator import generate_pdf
        pdf_path = generate_pdf(job_id, company, analysis)

        # Step 4: Email report
        from app.services.email_sender import send_report_email
        send_report_email(email, company, pdf_path)

        _update_job_status(job_id, JobStatus.COMPLETE)
        logger.info(f"Audit complete for job {job_id}")

    except Exception as exc:
        logger.exception(f"Audit failed for job {job_id}: {exc}")
        _update_job_status(job_id, JobStatus.FAILED, error_msg=str(exc))
        raise
