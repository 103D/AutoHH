"""Service for application tracking."""

from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import DuplicateError, NotFoundError
from app.core.logging import get_logger
from app.models.application import Application, ApplicationStatusHistory
from app.repositories.application import (
    ApplicationRepository,
    ApplicationStatusHistoryRepository,
)
from app.repositories.job import JobRepository
from app.schemas.application import ApplicationCreate, ApplicationUpdate
from app.services.candidate import CandidateService

logger = get_logger(__name__)

VALID_STATUSES = {
    "DRAFT", "READY", "APPLIED", "SCREENING", "INTERVIEW",
    "TECHNICAL_INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN", "NO_RESPONSE",
}


class ApplicationService:
    """Service for application tracking business logic."""

    def __init__(
        self,
        application_repo: ApplicationRepository,
        history_repo: ApplicationStatusHistoryRepository,
        job_repo: JobRepository,
        candidate_service: CandidateService,
    ):
        self.application_repo = application_repo
        self.history_repo = history_repo
        self.job_repo = job_repo
        self.candidate_service = candidate_service

    async def create_application(
        self, app_in: ApplicationCreate
    ) -> Application:
        """Create a new application."""
        # Resolve candidate profile
        if app_in.candidate_profile_id:
            profile = await self.candidate_service.get_profile(app_in.candidate_profile_id)
        else:
            profiles = await self.candidate_service.repository.get_multi(0, 1)
            if not profiles:
                raise NotFoundError("No candidate profile found")
            profile = profiles[0]

        # Check for duplicate
        existing = await self.application_repo.get_by_job_and_candidate(
            app_in.job_id, profile.id
        )
        if existing:
            raise DuplicateError(
                f"Application already exists for job {app_in.job_id}"
            )

        app_data = app_in.model_dump(exclude={"candidate_profile_id"})
        app_data["candidate_profile_id"] = profile.id
        app_data["status"] = "DRAFT"

        application = await self.application_repo.create(app_data)

        # Record initial status in history
        await self.history_repo.create({
            "application_id": application.id,
            "from_status": None,
            "to_status": "DRAFT",
            "comment": "Application created",
            "changed_at": datetime.now(UTC),
        })

        logger.info(f"Application created: {application.id} for job {app_in.job_id}")
        return application

    async def get_application(self, application_id: UUID) -> Application:
        """Get application by ID."""
        application = await self.application_repo.get(application_id)
        if not application:
            raise NotFoundError(f"Application {application_id} not found")
        return application

    async def get_applications(
        self,
        candidate_profile_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Application]:
        """Get applications with optional filters."""
        if candidate_profile_id:
            return await self.application_repo.get_for_candidate(
                candidate_profile_id, limit
            )
        if status:
            return await self.application_repo.get_by_status(status, limit)
        return await self.application_repo.get_multi(0, limit)

    async def update_application(
        self, application_id: UUID, app_in: ApplicationUpdate
    ) -> Application:
        """Update application and record status change in history."""
        application = await self.get_application(application_id)

        update_data = app_in.model_dump(exclude_unset=True)
        comment = update_data.pop("comment", None)
        new_status = update_data.get("status")

        # Validate status
        if new_status and new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}. Valid: {VALID_STATUSES}")

        # Record status change in history
        if new_status and new_status != application.status:
            await self.history_repo.create({
                "application_id": application.id,
                "from_status": application.status,
                "to_status": new_status,
                "comment": comment,
                "changed_at": datetime.now(UTC),
            })

            # Set applied_at when status becomes APPLIED
            if new_status == "APPLIED" and not application.applied_at:
                update_data["applied_at"] = datetime.now(UTC)

        # Update application
        if update_data:
            application = await self.application_repo.update(application, update_data)

        logger.info(f"Application {application_id} updated: status={application.status}")
        return application

    async def get_status_history(
        self, application_id: UUID
    ) -> list[ApplicationStatusHistory]:
        """Get status history for an application."""
        await self.get_application(application_id)
        return await self.history_repo.get_for_application(application_id)

    async def get_statistics(
        self, candidate_profile_id: UUID | None = None
    ) -> dict:
        """Get application statistics."""
        if candidate_profile_id:
            apps = await self.application_repo.get_for_candidate(
                candidate_profile_id, limit=1000
            )
        else:
            apps = await self.application_repo.get_multi(0, 1000)

        total = len(apps)
        by_status: dict[str, int] = {}
        for app in apps:
            by_status[app.status] = by_status.get(app.status, 0) + 1

        # Calculate rates
        applied = by_status.get("APPLIED", 0) + by_status.get("SCREENING", 0)
        applied += by_status.get("INTERVIEW", 0) + by_status.get("TECHNICAL_INTERVIEW", 0)
        applied += by_status.get("OFFER", 0) + by_status.get("REJECTED", 0)
        applied += by_status.get("NO_RESPONSE", 0)

        interview = (
            by_status.get("INTERVIEW", 0)
            + by_status.get("TECHNICAL_INTERVIEW", 0)
            + by_status.get("OFFER", 0)
        )

        responded = (
            by_status.get("SCREENING", 0)
            + by_status.get("INTERVIEW", 0)
            + by_status.get("TECHNICAL_INTERVIEW", 0)
            + by_status.get("OFFER", 0)
            + by_status.get("REJECTED", 0)
        )

        interview_rate = round(interview / applied * 100, 1) if applied > 0 else 0.0
        response_rate = round(responded / applied * 100, 1) if applied > 0 else 0.0

        return {
            "total": total,
            "by_status": by_status,
            "interview_rate": interview_rate,
            "response_rate": response_rate,
        }
