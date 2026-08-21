from fastapi import APIRouter

from app.api.v1 import applications, jobs, matching, profile, telegram

api_router = APIRouter()

api_router.include_router(profile.router)
api_router.include_router(jobs.router)
api_router.include_router(jobs.source_router)
api_router.include_router(matching.router)
api_router.include_router(applications.router)
api_router.include_router(telegram.router)
