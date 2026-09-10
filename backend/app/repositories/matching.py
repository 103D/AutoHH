from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.matching import MatchCategory, MatchResult
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class MatchResultRepository(BaseRepository[MatchResult]):
    def __init__(self, session: AsyncSession):
        super().__init__(MatchResult, session)

    async def get_by_job_and_candidate(
        self, job_id: UUID, candidate_profile_id: UUID
    ) -> MatchResult | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.job_id == job_id,
                self.model.candidate_profile_id == candidate_profile_id,
                self.model.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def _acquire_revision_lock(self, job_id: UUID, candidate_profile_id: UUID) -> None:
        """Serialize concurrent revision creation for one (job, candidate) pair.

        Without this lock, two concurrent transactions can deadlock: each
        holds a wait on the other's uncommitted row via
        ``UPDATE ... WHERE is_current`` / the partial unique index (classic
        insert-vs-update cycle). A PostgreSQL deadlock aborts the whole
        transaction, which no SAVEPOINT retry can recover from.

        ``pg_advisory_xact_lock`` is transaction-scoped: it is released on
        commit/rollback, so the second worker proceeds with a clean snapshot
        and the in-loop IntegrityError retry remains only a safety net.
        """
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"match_revision:{job_id}:{candidate_profile_id}"},
        )

    async def create_revision(self, data: dict) -> MatchResult:
        """Append a new immutable revision and mark the previous one superseded.

        Exactly one row per (job, candidate) is ``is_current`` (partial unique
        index). Concurrent inserts are serialized by an advisory lock; a
        losing insert (if one still slips through) retries and either adopts
        the winner's identical fingerprint or re-inserts after superseding it.
        """
        payload = {k: v for k, v in data.items() if k not in {"id", "revision", "is_current"}}
        job_id = payload["job_id"]
        candidate_profile_id = payload["candidate_profile_id"]
        fingerprint = payload.get("analysis_fingerprint")

        await self._acquire_revision_lock(job_id, candidate_profile_id)

        for _attempt in range(3):
            if fingerprint:
                existing = await self.get_by_analysis_fingerprint(
                    fingerprint, job_id, candidate_profile_id
                )
                if existing is not None:
                    return existing

            try:
                async with self.session.begin_nested():
                    max_revision = await self.session.scalar(
                        select(func.max(self.model.revision)).where(
                            self.model.job_id == job_id,
                            self.model.candidate_profile_id == candidate_profile_id,
                        )
                    )
                    next_revision = int(max_revision or 0) + 1
                    await self.session.execute(
                        update(self.model)
                        .where(
                            self.model.job_id == job_id,
                            self.model.candidate_profile_id == candidate_profile_id,
                            self.model.is_current.is_(True),
                        )
                        .values(is_current=False)
                    )
                    obj = self.model(
                        **payload, revision=next_revision, is_current=True
                    )
                    self.session.add(obj)
                    await self.session.flush()
                await self.session.refresh(obj)
                return obj
            except Exception as e:
                # The savepoint was rolled back; on a concurrent IntegrityError
                # we retry with fresh estimates.
                logger.warning("Match revision insert failed, retrying: %s", e)
                continue

        raise RuntimeError("Could not insert a match revision after 3 attempts")

    async def get_by_analysis_fingerprint(
        self,
        analysis_fingerprint: str,
        job_id: UUID | None = None,
        candidate_profile_id: UUID | None = None,
    ) -> MatchResult | None:
        statement = select(self.model).where(
            self.model.analysis_fingerprint == analysis_fingerprint,
            self.model.is_current.is_(True),
        )
        if job_id is not None:
            statement = statement.where(self.model.job_id == job_id)
        if candidate_profile_id is not None:
            statement = statement.where(
                self.model.candidate_profile_id == candidate_profile_id
            )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_revision_history(
        self, job_id: UUID, candidate_profile_id: UUID
    ) -> list[MatchResult]:
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.job_id == job_id,
                self.model.candidate_profile_id == candidate_profile_id,
            )
            .order_by(self.model.revision)
        )
        return list(result.scalars().all())

    async def get_for_job(self, job_id: UUID) -> list[MatchResult]:
        result = await self.session.execute(
            select(self.model).where(
                self.model.job_id == job_id,
                self.model.is_current.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_for_candidate(self, candidate_profile_id: UUID) -> list[MatchResult]:
        result = await self.session.execute(
            select(self.model).where(
                self.model.candidate_profile_id == candidate_profile_id,
                self.model.is_current.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_high_priority(
        self, candidate_profile_id: UUID, limit: int = 10
    ) -> list[MatchResult]:
        from sqlalchemy import desc
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.candidate_profile_id == candidate_profile_id,
                self.model.recommendation.in_(
                    [MatchCategory.DREAM_JOB, MatchCategory.STRETCH]
                ),
            )
            .order_by(desc(self.model.analyzed_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending_notification(
        self, candidate_profile_id: UUID, limit: int = 20
    ) -> list[MatchResult]:
        """Get matches that haven't been notified yet (for notification worker)."""
        # Actionable categories only: worth showing to the user
        from sqlalchemy import desc
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.candidate_profile_id == candidate_profile_id,
                self.model.recommendation.in_(
                    [
                        MatchCategory.DREAM_JOB,
                        MatchCategory.STRETCH,
                        MatchCategory.SOLID_MATCH,
                    ]
                ),
            )
            .order_by(desc(self.model.analyzed_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_effective_top(
        self, candidate_profile_id: UUID, categories: list[str], limit: int = 5
    ) -> list[MatchResult]:
        """Get top matches by score within the given categories.

        Both the computed category and the manual user override are accepted,
        so overridden jobs are included in daily digests.
        """
        from sqlalchemy import desc
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.candidate_profile_id == candidate_profile_id,
                self.model.recommendation.in_(categories)
                | self.model.user_override_recommendation.in_(categories),
            )
            .order_by(desc(self.model.score))
            .limit(limit)
        )
        return list(result.scalars().all())
