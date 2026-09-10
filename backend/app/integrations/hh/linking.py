"""Deterministic remote-to-local entity linker (ADR-001 milestone 4).

The linker joins facts that can be proven equal; it deliberately does not use
title, company, URL, or resume-headline fuzzy matching:

* HH negotiation -> Job: exact remote vacancy id == local HH Job.external_id,
  and exactly one HH source candidate exists;
* HH negotiation -> Application: the linked Job has an existing application
  whose candidate profile belongs to the HH account owner;
* HH resume -> ResumeProfile: explicit user action only after ownership check.

No operation here creates an Application or changes an Application status.
Remote applicant state remains in ``HHNegotiation`` as remote data.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.hh import HHAccount
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository, ResumeProfileRepository
from app.repositories.hh import HHAccountRepository, HHNegotiationRepository, HHResumeRepository
from app.repositories.job import JobRepository


@dataclass
class LinkResult:
    """Counters from a deterministic negotiation-link pass."""

    scanned: int = 0
    jobs_linked: int = 0
    applications_linked: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "jobs_linked": self.jobs_linked,
            "applications_linked": self.applications_linked,
        }


class HHLinkService:
    """Link synced HH remote entities to local entities owned by one user."""

    def __init__(self, session: AsyncSession):
        self.account_repo = HHAccountRepository(session)
        self.resume_repo = HHResumeRepository(session)
        self.negotiation_repo = HHNegotiationRepository(session)
        self.job_repo = JobRepository(session)
        self.application_repo = ApplicationRepository(session)
        self.candidate_repo = CandidateRepository(session)
        self.resume_profile_repo = ResumeProfileRepository(session)

    async def link_negotiations(self, user_id: UUID) -> LinkResult:
        """Link all already-synced negotiations for the account owner."""
        account = await self._account_for_user(user_id)
        result = LinkResult()

        for negotiation in await self.negotiation_repo.list_for_account(account.id):
            result.scanned += 1
            job = None
            if negotiation.job_id is None and negotiation.remote_vacancy_id:
                job = await self.job_repo.get_by_hh_vacancy_id(
                    negotiation.remote_vacancy_id
                )

            # An existing persisted Job link is authoritative. We resolve it
            # only when necessary so an idempotent rerun has no extra writes.
            job_id = negotiation.job_id or (job.id if job else None)
            application = None
            if negotiation.application_id is None and job_id is not None:
                application = await self.application_repo.get_by_job_and_user(
                    job_id, account.user_id
                )

            job_linked, application_linked = await self.negotiation_repo.link_local_entities(
                negotiation,
                job_id=job.id if job else None,
                application_id=application.id if application else None,
            )
            result.jobs_linked += int(job_linked)
            result.applications_linked += int(application_linked)

        return result

    async def link_resume_profile(
        self, user_id: UUID, remote_resume_id: str, resume_profile_id: UUID
    ) -> bool:
        """Explicitly map a remote HH resume to the owner's local profile.

        A local ResumeProfile has no stable external HH id and title matching is
        unsafe; the user chooses this mapping. Both records must belong to the
        same account owner.
        """
        account = await self._account_for_user(user_id)
        remote_resume = await self.resume_repo.get_by_remote(account.id, remote_resume_id)
        if remote_resume is None:
            raise NotFoundError(f"HH resume {remote_resume_id} not found")

        profile = await self.resume_profile_repo.get(resume_profile_id)
        if profile is None:
            raise NotFoundError(f"Resume profile {resume_profile_id} not found")
        candidate = await self.candidate_repo.get(profile.candidate_profile_id)
        if candidate is None or candidate.user_id != user_id:
            # Do not reveal whether a foreign profile exists.
            raise ValidationError("Resume profile does not belong to the HH account owner")
        return await self.resume_repo.link_resume_profile(remote_resume, profile.id)

    async def _account_for_user(self, user_id: UUID) -> HHAccount:
        account = await self.account_repo.get_by_user(user_id)
        if account is None:
            raise NotFoundError("HH account is not connected")
        return account
