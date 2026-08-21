from app.repositories.application import (
    ApplicationRepository,
    ApplicationStatusHistoryRepository,
)
from app.repositories.base import BaseRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository, JobSourceRepository
from app.repositories.matching import MatchResultRepository
from app.repositories.notification import NotificationRepository

__all__ = [
    "BaseRepository",
    "ApplicationRepository",
    "ApplicationStatusHistoryRepository",
    "CandidateRepository",
    "JobRepository",
    "JobSourceRepository",
    "MatchResultRepository",
    "NotificationRepository",
]
