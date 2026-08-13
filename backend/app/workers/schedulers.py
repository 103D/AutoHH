from celery.schedules import crontab

from app.core.config import settings
from app.workers.celery_app import celery_app

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "fetch-jobs-periodic": {
        "task": "fetch_jobs_from_all_sources",
        "schedule": settings.job_fetch_interval_minutes * 60.0,  # Convert to seconds
        "options": {"expires": 300},  # Task expires after 5 minutes if not executed
    },
    # Placeholder for future tasks
    # "analyze-jobs-periodic": {
    #     "task": "analyze_new_jobs",
    #     "schedule": 600.0,  # Every 10 minutes
    # },
}