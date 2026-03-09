"""
periodic.py — Celery beat maintenance tasks.

  detect_stuck_jobs : every 30 min — find RUNNING/ANALYZING jobs > 2 hours old,
                      mark them FAILED, attempt SP cleanup, alert admin.
  cleanup_tmp_dirs  : every 4 hours — delete scan + PDF temp dirs older than 24 hours.
"""
import logging
import os
import shutil
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.tasks.celery_app import celery_app
from app.constants import PENDING_JOB_EXPIRY_MINUTES
from app.database import SessionLocal
from app.models import Job, JobStatus

logger = logging.getLogger(__name__)

STUCK_JOB_THRESHOLD_HOURS = 2
TMP_DIRS = ["/tmp/monkey365", "/tmp/audit_jobs"]
TMP_MAX_AGE_HOURS = 24


@celery_app.task(name="app.tasks.periodic.detect_stuck_jobs")
def detect_stuck_jobs():
    """
    Periodic cleanup of stuck jobs:
      - PENDING > 30 min  → consent never completed, free up the email slot
      - RUNNING/ANALYZING > 2 hours → worker likely crashed, alert admin + attempt SP cleanup
    """
    now = datetime.now(timezone.utc)
    pending_cutoff = now - timedelta(minutes=PENDING_JOB_EXPIRY_MINUTES)
    running_cutoff = now - timedelta(hours=STUCK_JOB_THRESHOLD_HOURS)
    db = SessionLocal()
    try:
        # --- Expire stale PENDING jobs (consent timed out) ---
        stale_pending = db.query(Job).filter(
            Job.status == JobStatus.PENDING,
            Job.created_at < pending_cutoff,
        ).all()

        for job in stale_pending:
            logger.info("Expiring stale PENDING job %s for %s (created %s)", job.id, job.email, job.created_at)
            job.status = JobStatus.FAILED
            job.error_msg = "Consent was not completed within 30 minutes — expired automatically."

        if stale_pending:
            logger.info("Expired %d stale PENDING job(s)", len(stale_pending))

        # --- Detect stuck RUNNING/ANALYZING jobs (worker crash) ---
        stuck = db.query(Job).filter(
            Job.status.in_([JobStatus.RUNNING, JobStatus.ANALYZING]),
            Job.updated_at < running_cutoff,
        ).all()

        for job in stuck:
            logger.warning(
                "Stuck job detected: %s (status=%s, last updated=%s)",
                job.id, job.status, job.updated_at,
            )
            job.status = JobStatus.FAILED
            job.error_msg = f"Job timed out — stuck in {job.status} for over {STUCK_JOB_THRESHOLD_HOURS} hours."

            if job.tenant_id:
                _try_sp_cleanup(job.tenant_id, job.id)

            _send_stuck_job_alert(job)

        if stuck:
            logger.info("Marked %d stuck RUNNING/ANALYZING job(s) as FAILED", len(stuck))

        db.commit()

        if not stale_pending and not stuck:
            logger.info("Stuck-job check: all clear")

    finally:
        db.close()


def _try_sp_cleanup(tenant_id: str, job_id: str):
    """Attempt to find and remove our SP from the customer's tenant. Best-effort."""
    try:
        from app.services.graph_admin import _get_token_for_tenant, _get_service_principal_id, remove_service_principal
        token = _get_token_for_tenant(tenant_id)
        sp_id = _get_service_principal_id(token, retries=2, delay=5.0)
        remove_service_principal(tenant_id, sp_id)
        logger.info("SP cleanup via stuck-job detector succeeded for tenant %s", tenant_id)
    except Exception as exc:
        logger.warning(
            "SP cleanup for stuck job %s (tenant %s) failed: %s",
            job_id, tenant_id, exc,
        )


def _send_stuck_job_alert(job: Job):
    """Send admin alert about a stuck job."""
    try:
        from app.services.email_sender import send_admin_alert
        send_admin_alert(
            subject=f"[M365 Audit] Stuck job detected — {job.company}",
            body=(
                f"A job was automatically marked as FAILED due to inactivity.\n\n"
                f"Job ID:    {job.id}\n"
                f"Company:   {job.company}\n"
                f"Email:     {job.email}\n"
                f"Tenant:    {job.tenant_id or 'unknown'}\n"
                f"Last seen: {job.updated_at} UTC\n\n"
                f"The worker process likely crashed or was OOM-killed. "
                f"SP cleanup was attempted. Check logs for details."
            ),
        )
    except Exception as exc:
        logger.warning("Failed to send stuck-job admin alert: %s", exc)


@celery_app.task(name="app.tasks.periodic.cleanup_tmp_dirs")
def cleanup_tmp_dirs():
    """Delete scan and PDF temp directories older than TMP_MAX_AGE_HOURS hours."""
    cutoff = time.time() - (TMP_MAX_AGE_HOURS * 3600)
    removed = 0
    for base in TMP_DIRS:
        base_path = Path(base)
        if not base_path.exists():
            continue
        for entry in base_path.iterdir():
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                try:
                    shutil.rmtree(entry)
                    logger.info("Removed old tmp dir: %s", entry)
                    removed += 1
                except Exception as exc:
                    logger.warning("Failed to remove %s: %s", entry, exc)
    logger.info("Tmp cleanup complete: removed %d director(ies)", removed)
