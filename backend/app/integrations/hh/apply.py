"""Explicit HH apply (ADR-001 milestone 5).

One explicit user action: POST /negotiations with (resume, vacancy, message).
Idempotency guard is the durable triple (account, remote_resume, remote_vacancy)
in ``hh_apply_attempts``: a repeated call never issues a second remote POST.

Never creates or mutates the local Application workflow: the remote
negotiation stays a remote fact with unlinked job/application refs.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.integrations.hh.exceptions import (
    HHAlreadyAppliedError,
    HHAuthRequiredError,
    HHIntegrationError,
)
from app.models.hh import HHAccount, HHAccountStatus, HHApplyAttemptStatus
from app.repositories.hh import (
    HHApplyAttemptRepository,
    HHNegotiationRepository,
    HHResumeRepository,
)

logger = get_logger(__name__)

STALE_IN_PROGRESS_SECONDS = 600


@dataclass(frozen=True)
class ApplyResult:
    applied: bool
    duplicate: bool
    remote_negotiation_id: str | None = None


class HHApplyService:
    """Explicit, owner-scoped, idempotent apply to an HH vacancy."""

    def __init__(self, session: AsyncSession, *, account_service=None):
        from app.integrations.hh.accounts import HHAccountService

        self.session = session
        self.accounts = account_service or HHAccountService(session)
        self.attempts = HHApplyAttemptRepository(session)
        self.resumes = HHResumeRepository(session)
        self.negotiations = HHNegotiationRepository(session)

    async def apply(
        self,
        user_id: UUID,
        remote_resume_id: str,
        remote_vacancy_id: str,
        message: str | None = None,
    ) -> ApplyResult:
        resume_id = (remote_resume_id or "").strip()
        vacancy_id = (remote_vacancy_id or "").strip()
        if not resume_id or not vacancy_id:
            raise ValidationError("remote_resume_id and remote_vacancy_id required")
        clean = message.strip() if isinstance(message, str) else None

        account = await self.accounts.repo.get_by_user(user_id)
        if account is None or account.status != HHAccountStatus.CONNECTED:
            raise HHAuthRequiredError("HH account is not connected")

        resume = await self.resumes.get_by_remote(account.id, resume_id)
        if resume is None:
            raise NotFoundError(f"HH resume {resume_id!r} not found")

        attempt = await self.attempts.get_by_tuple(account.id, resume_id, vacancy_id)
        if attempt is not None:
            if attempt.status == HHApplyAttemptStatus.SUCCEEDED:
                return ApplyResult(True, True, attempt.remote_negotiation_id)
            if attempt.status == HHApplyAttemptStatus.IN_PROGRESS:
                if not self._is_stale(attempt.updated_at or attempt.created_at):
                    raise DuplicateError("HH apply is already in progress")

        if attempt is None:
            try:
                attempt = await self.attempts.create(
                    {
                        "hh_account_id": account.id,
                        "remote_resume_id": resume_id,
                        "remote_vacancy_id": vacancy_id,
                        "status": HHApplyAttemptStatus.IN_PROGRESS,
                    }
                )
            except IntegrityError as exc:
                await self.session.rollback()
                raise DuplicateError("HH apply is already in progress") from exc
        else:
            attempt.status = HHApplyAttemptStatus.IN_PROGRESS
            attempt.error = None
            await self.session.flush()

        client = self.accounts.applicant_client_for(user_id)
        try:
            response = await client.apply_to_vacancy(
                resume_id=resume_id, vacancy_id=vacancy_id, message=clean or None
            )
        except HHAlreadyAppliedError:
            remote_id = await self._sync_and_find(account, user_id, resume_id, vacancy_id)
            attempt.status = HHApplyAttemptStatus.SUCCEEDED
            attempt.remote_negotiation_id = remote_id
            attempt.error = None
            await self.session.flush()
            return ApplyResult(True, True, remote_id)
        except HHIntegrationError as exc:
            attempt.status = HHApplyAttemptStatus.FAILED
            attempt.error = f"{type(exc).__name__}: {exc}"
            await self.session.flush()
            raise
        except Exception as exc:
            attempt.status = HHApplyAttemptStatus.FAILED
            attempt.error = f"{type(exc).__name__}: {exc}"
            await self.session.flush()
            raise

        posted = response.get("id") if isinstance(response, dict) else None
        remote_id = await self._sync_and_find(account, user_id, resume_id, vacancy_id)
        attempt.status = HHApplyAttemptStatus.SUCCEEDED
        attempt.remote_negotiation_id = remote_id or (str(posted) if posted else None)
        attempt.error = None
        await self.session.flush()
        return ApplyResult(True, False, attempt.remote_negotiation_id)


    async def _sync_and_find(
        self, account: HHAccount, user_id: UUID, resume_id: str, vacancy_id: str
    ) -> str | None:
        """Best-effort refresh of the remote list, then find our pair."""
        try:
            await self.accounts.sync_negotiations(user_id)
        except HHIntegrationError as exc:
            logger.warning("HH apply follow-up sync failed: %s", type(exc).__name__)
        found = await self.negotiations.find_by_resume_vacancy(
            account.id, resume_id, vacancy_id
        )
        if found is not None:
            return found.remote_negotiation_id
        return None

    @staticmethod
    def _is_stale(moment: datetime | None) -> bool:
        if moment is None:
            return False
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return (datetime.now(UTC) - moment).total_seconds() > STALE_IN_PROGRESS_SECONDS
