from celery import Celery
celery_app = Celery("m365_audit", broker="redis://localhost:6379/0")
