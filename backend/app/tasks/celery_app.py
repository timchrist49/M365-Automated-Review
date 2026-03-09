from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "m365_audit",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.audit_task", "app.tasks.periodic"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task limits — Monkey365 scan takes up to 40 min
    task_time_limit=2700,         # 45 min hard kill
    task_soft_time_limit=2400,    # 40 min soft — allows graceful cleanup

    # Fresh worker process per audit task: prevents memory leaks from
    # repeated PowerShell subprocess invocations accumulating over time
    worker_max_tasks_per_child=1,

    # Silences CPendingDeprecationWarning from Celery 5 → 6 migration
    broker_connection_retry_on_startup=True,

    # Beat schedule — periodic maintenance tasks
    beat_schedule={
        # Every 30 min: mark stuck RUNNING/ANALYZING jobs as FAILED, alert admin
        "detect-stuck-jobs": {
            "task": "app.tasks.periodic.detect_stuck_jobs",
            "schedule": crontab(minute="*/30"),
        },
        # Every 4 hours: prune /tmp scan + PDF directories older than 24 hours
        "cleanup-tmp-dirs": {
            "task": "app.tasks.periodic.cleanup_tmp_dirs",
            "schedule": crontab(minute="0", hour="*/4"),
        },
    },
)
