from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "auto_dev_orchestrator",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Configure Celery to auto-discover tasks in app.workers module
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Explicitly import tasks to ensure they're registered
from app.workers import job_worker  # noqa: E402, F401
