from app.core.config import settings
from app.workers.celery_app import celery_app

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "fetch-jobs-periodic": {
        "task": "fetch_jobs_from_all_sources",
        "schedule": settings.job_fetch_interval_minutes * 60.0,
        "options": {"expires": 300},
    },
    "analyze-jobs-periodic": {
        "task": "analyze_new_jobs",
        "schedule": 600.0,  # Every 10 minutes
        "options": {"expires": 300},
    },
    "send-notifications-periodic": {
        "task": "send_notifications",
        "schedule": 300.0,  # Every 5 minutes
        "options": {"expires": 120},
    },
}
