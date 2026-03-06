from app.tasks.celery_app import celery_app

@celery_app.task(bind=True, name="execute_audit")
def execute_audit(self, job_id: str, tenant_id: str):
    pass
