"""Celery application configuration.

This module configures the Celery application for BSForge background tasks.
Uses Redis as both broker and result backend.
"""

from celery import Celery

from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "bsforge",
    broker=str(settings.celery_broker_url),
    backend=str(settings.celery_result_backend),
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=600,  # 10 minutes hard limit
    task_soft_time_limit=540,  # 9 minutes soft limit
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    # Result settings
    result_expires=86400,  # 24 hours
    result_extended=True,
    # Beat scheduler settings
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename="celerybeat-schedule",
    # Task routes
    task_routes={
        "app.workers.collect.*": {"queue": "collect"},
        "app.workers.generate.*": {"queue": "generate"},
        "app.workers.upload.*": {"queue": "upload"},
    },
    # Default queue
    task_default_queue="default",
)

# Auto-discover tasks from these modules
celery_app.autodiscover_tasks(
    [
        "app.workers.collect",
    ]
)

__all__ = ["celery_app"]
