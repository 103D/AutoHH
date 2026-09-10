"""Repository for HH account connections and remote snapshots (ADR-001)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hh import (
    HHAccount,
    HHApplyAttempt,
    HHNegotiation,
    HHResume,
)
from app.repositories.base import BaseRepository


class HHAccountRepository(BaseRepository[HHAccount]):
    def __init__(self, session: AsyncSession):
        super().__init__(HHAccount, session)

    async def get_by_user(self, user_id: UUID, host: str = "hh.ru") -> HHAccount | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.user_id == user_id, self.model.host == host
            )
        )
        return result.scalar_one_or_none()

    async def get_by_hh_user(
        self, hh_user_id: str, host: str = "hh.ru"
    ) -> HHAccount | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.hh_user_id == hh_user_id, self.model.host == host
            )
        )
        return result.scalar_one_or_none()

    async def list_connected(self, *, limit: int = 100) -> list[HHAccount]:
        """Connected accounts eligible for background HH sync/refresh."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.status == "CONNECTED")
            .order_by(self.model.last_sync_at.asc().nullsfirst(), self.model.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def upsert_connected(self, data: dict) -> HHAccount:
        """Create or update the (user, host) account with fresh credentials."""
        account = await self.get_by_user(data["user_id"], data.get("host", "hh.ru"))
        if account is None:
            return await self.create(data)
        for field, value in data.items():
            setattr(account, field, value)
        await self.session.flush()
        await self.session.refresh(account)
        return account

    async def mark_status(self, account: HHAccount, status: str) -> HHAccount:
        account.status = status
        await self.session.flush()
        await self.session.refresh(account)
        return account

    async def mark_synced(self, account: HHAccount) -> None:
        account.last_sync_at = datetime.now(UTC)
        await self.session.flush()

    async def delete(self, account: HHAccount) -> None:
        await self.session.delete(account)
        await self.session.flush()


class HHResumeRepository(BaseRepository[HHResume]):
    def __init__(self, session: AsyncSession):
        super().__init__(HHResume, session)

    async def get_by_remote(
        self, hh_account_id: UUID, remote_resume_id: str
    ) -> HHResume | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.hh_account_id == hh_account_id,
                self.model.remote_resume_id == remote_resume_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_from_remote(
        self, hh_account_id: UUID, data: dict
    ) -> tuple[HHResume, bool]:
        """Idempotent upsert keyed by content_hash; returns (row, changed)."""
        row = await self.get_by_remote(hh_account_id, data["remote_resume_id"])
        if row is None:
            return await self.create({**data, "hh_account_id": hh_account_id}), True
        if row.content_hash == data["content_hash"]:
            return row, False
        for field in (
            "title",
            "status",
            "remote_updated_at",
            "raw_data",
            "content_hash",
        ):
            setattr(row, field, data[field])
        await self.session.flush()
        return row, True

    async def list_for_account(self, hh_account_id: UUID) -> list[HHResume]:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.hh_account_id == hh_account_id)
            .order_by(self.model.remote_updated_at.desc().nullslast())
        )
        return list(result.scalars().all())

    async def link_resume_profile(self, row: HHResume, resume_profile_id: UUID) -> bool:
        """Set an explicit local resume-profile mapping idempotently."""
        if row.resume_profile_id == resume_profile_id:
            return False
        row.resume_profile_id = resume_profile_id
        await self.session.flush()
        return True


class HHNegotiationRepository(BaseRepository[HHNegotiation]):
    def __init__(self, session: AsyncSession):
        super().__init__(HHNegotiation, session)

    async def get_by_remote(
        self, hh_account_id: UUID, remote_negotiation_id: str
    ) -> HHNegotiation | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.hh_account_id == hh_account_id,
                self.model.remote_negotiation_id == remote_negotiation_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_from_remote(
        self, hh_account_id: UUID, data: dict
    ) -> tuple[HHNegotiation, bool]:
        """Idempotent upsert keyed by content_hash; returns (row, changed).

        Local workflow links (job_id / application_id, milestone 4) are never
        overwritten by remote syncs.
        """
        row = await self.get_by_remote(hh_account_id, data["remote_negotiation_id"])
        if row is None:
            return await self.create({**data, "hh_account_id": hh_account_id}), True
        if row.content_hash == data["content_hash"]:
            return row, False
        for field in (
            "remote_resume_id",
            "remote_vacancy_id",
            "state_id",
            "state_name",
            "remote_created_at",
            "remote_updated_at",
            "messages_metadata",
            "raw_data",
            "content_hash",
        ):
            setattr(row, field, data[field])
        await self.session.flush()
        return row, True

    async def list_for_account(self, hh_account_id: UUID) -> list[HHNegotiation]:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.hh_account_id == hh_account_id)
            .order_by(self.model.remote_updated_at.desc().nullslast())
        )
        return list(result.scalars().all())

    async def find_for_pair(
        self, hh_account_id: UUID, remote_resume_id: str, remote_vacancy_id: str
    ) -> HHNegotiation | None:
        """Newest synced negotiation for one (resume, vacancy) pair."""
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.hh_account_id == hh_account_id,
                self.model.remote_resume_id == remote_resume_id,
                self.model.remote_vacancy_id == remote_vacancy_id,
            )
            .order_by(self.model.remote_updated_at.desc().nullslast())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_by_resume_vacancy(
        self, hh_account_id: UUID, remote_resume_id: str, remote_vacancy_id: str
    ) -> HHNegotiation | None:
        """Alias with M5 naming: find remote negotiation for an apply pair."""
        return await self.find_for_pair(
            hh_account_id, remote_resume_id, remote_vacancy_id
        )

    async def link_local_entities(
        self,
        row: HHNegotiation,
        *,
        job_id: UUID | None = None,
        application_id: UUID | None = None,
    ) -> tuple[bool, bool]:
        """Fill absent local links without overwriting previous associations.

        A remote negotiation remains a remote fact. This method never changes
        its remote state or any local Application workflow field.
        """
        job_linked = row.job_id is None and job_id is not None
        application_linked = row.application_id is None and application_id is not None
        if job_linked:
            row.job_id = job_id
        if application_linked:
            row.application_id = application_id
        if job_linked or application_linked:
            await self.session.flush()
        return job_linked, application_linked



class HHApplyAttemptRepository(BaseRepository[HHApplyAttempt]):
    """Audit-guard rows for explicit applies (ADR-001 milestone 5)."""

    def __init__(self, session: AsyncSession):
        super().__init__(HHApplyAttempt, session)

    async def get_by_tuple(
        self, hh_account_id: UUID, remote_resume_id: str, remote_vacancy_id: str
    ) -> HHApplyAttempt | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.hh_account_id == hh_account_id,
                self.model.remote_resume_id == remote_resume_id,
                self.model.remote_vacancy_id == remote_vacancy_id,
            )
        )
        return result.scalar_one_or_none()
