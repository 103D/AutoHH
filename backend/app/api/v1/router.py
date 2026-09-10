from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    applications,
    hh,
    jobs,
    matching,
    profile,
    resume_analysis,
    resumes,
    telegram,
)

api_router = APIRouter()

api_router.include_router(profile.router)
api_router.include_router(jobs.router)
api_router.include_router(jobs.source_router)
api_router.include_router(matching.router)
api_router.include_router(applications.router)
api_router.include_router(resumes.router)
api_router.include_router(resume_analysis.router)
api_router.include_router(telegram.router)
api_router.include_router(analytics.router)
api_router.include_router(hh.router)
