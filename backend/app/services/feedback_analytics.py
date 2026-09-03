"""Feedback-loop analytics (task spec #17).

Aggregates quality outcome events — which score range produces interviews,
which resume profile performs better, which specialization performs better,
which missing skills correlate with rejection. Pure deterministic counting of
collected events; no ML, no score inflation (task spec #31).
"""

from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.repositories.application import ApplicationRepository

logger = get_logger(__name__)

# Outcome classes by application status (mirrors application service logic)
RESPONDED_STATUSES = {"SCREENING", "INTERVIEW", "TECHNICAL_INTERVIEW", "OFFER", "REJECTED"}
INTERVIEW_STATUSES = {"INTERVIEW", "TECHNICAL_INTERVIEW", "OFFER"}
OFFER_STATUSES = {"OFFER"}
REJECTED_STATUSES = {"REJECTED"}


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator > 0 else 0.0


def _bucket_for_score(score: int | None, buckets: list[int]) -> str:
    """Deterministic score bucket label, e.g. '55-69' or '<40'."""
    if score is None:
        return "unknown"
    boundaries = sorted(buckets)
    if score < boundaries[0]:
        return f"<{boundaries[0]}"
    for low, high in zip(boundaries, boundaries[1:], strict=False):
        if score < high:
            return f"{low}-{high - 1}"
    return f">={boundaries[-1]}"


def _bucket_order_key(label: str) -> tuple[int, int]:
    """Numeric ordering for bucket labels: <X first, then X-Y ranges, >=Z,
    'unknown' last (lexicographic order would put '<40' after '40-54')."""
    if label == "unknown":
        return (3, 0)
    if label.startswith("<"):
        return (0, 0)
    if label.startswith(">="):
        return (2, int(label[2:]))
    return (1, int(label.split("-")[0]))


def _tally(stats: dict, responded: bool, interview: bool, offer: bool) -> None:
    """Accumulate one application event into a stats dict."""
    stats["applications"] += 1
    if responded:
        stats["responses"] += 1
    if interview:
        stats["interviews"] += 1
    if offer:
        stats["offers"] += 1


def _add_rates(stats: dict) -> None:
    """Attach response/interview/offer rates to a stats dict."""
    apps = stats["applications"]
    stats["response_rate"] = _rate(stats["responses"], apps)
    stats["interview_rate"] = _rate(stats["interviews"], apps)
    stats["offer_rate"] = _rate(stats["offers"], apps)


class FeedbackAnalyticsService:
    """Collects and aggregates application outcome events."""

    def __init__(self, application_repo: ApplicationRepository):
        self.application_repo = application_repo

    async def feedback_report(
        self, candidate_profile_id: UUID | None = None
    ) -> dict:
        """Aggregate the feedback dataset into per-bucket / per-profile stats."""
        rows = await self.application_repo.list_feedback_dataset(candidate_profile_id)
        buckets = self._parse_buckets(settings.feedback_score_buckets)

        total = len(rows)
        bucket_stats: dict[str, dict] = {}
        profile_stats: dict[str, dict] = {}
        specialization_stats: dict[str, dict] = {}
        rejection_reasons: dict[str, int] = {}
        missing_skills_on_rejection: dict[str, int] = {}

        for app, match, job, resume_profile in rows:
            score = getattr(match, "score", None)
            status = app.status
            responded = status in RESPONDED_STATUSES
            interview = status in INTERVIEW_STATUSES
            offer = status in OFFER_STATUSES
            rejected = status in REJECTED_STATUSES

            # --- Score buckets (only where a match exists -> label 'unknown') ---
            label = _bucket_for_score(score, buckets)
            stats = bucket_stats.setdefault(
                label,
                {
                    "bucket": label,
                    "applications": 0,
                    "responses": 0,
                    "interviews": 0,
                    "offers": 0,
                },
            )
            _tally(stats, responded, interview, offer)

            # --- Resume profiles ---
            if resume_profile is not None:
                key = str(resume_profile.id)
                pstats = profile_stats.setdefault(
                    key,
                    {
                        "resume_profile_id": str(resume_profile.id),
                        "profile_name": resume_profile.profile_name,
                        "specialization": resume_profile.specialization,
                        "applications": 0,
                        "responses": 0,
                        "interviews": 0,
                        "offers": 0,
                    },
                )
                _tally(pstats, responded, interview, offer)

            # --- Specializations (multi-label, from the job) ---
            for spec in getattr(job, "specializations", None) or []:
                sstats = specialization_stats.setdefault(
                    spec,
                    {"specialization": spec, "applications": 0, "responses": 0,
                     "interviews": 0, "offers": 0},
                )
                _tally(sstats, responded, interview, offer)

            # --- Rejection details ---
            if rejected:
                reason = (app.rejection_reason or "unspecified").strip()
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                for skill in getattr(match, "missing_skills", None) or []:
                    missing_skills_on_rejection[str(skill)] = (
                        missing_skills_on_rejection.get(str(skill), 0) + 1
                    )

        # Finalize rates and ordering
        for stats in bucket_stats.values():
            _add_rates(stats)
        for stats in profile_stats.values():
            _add_rates(stats)
        for stats in specialization_stats.values():
            _add_rates(stats)
        ordered_buckets = sorted(
            bucket_stats.values(), key=lambda s: _bucket_order_key(s["bucket"])
        )
        profiles = sorted(
            profile_stats.values(), key=lambda s: (-s["interviews"], -s["applications"])
        )
        specializations = sorted(
            specialization_stats.values(),
            key=lambda s: (-s["applications"], s["specialization"]),
        )

        responded_total = sum(s["responses"] for s in ordered_buckets)
        interview_total = sum(s["interviews"] for s in ordered_buckets)

        logger.info(
            f"Feedback report: total={total} responded={responded_total} "
            f"interviews={interview_total}"
        )
        return {
            "total_applications": total,
            "responded": responded_total,
            "interviews": interview_total,
            "response_rate": _rate(responded_total, total),
            "interview_rate": _rate(interview_total, total),
            "score_buckets": ordered_buckets,
            "resume_profiles": profiles,
            "specializations": specializations,
            "rejection_reasons": sorted(
                (
                    {"name": reason, "count": count}
                    for reason, count in rejection_reasons.items()
                ),
                key=lambda r: (-r["count"], r["name"]),
            ),
            "missing_skills_on_rejection": sorted(
                (
                    {"name": skill, "count": count}
                    for skill, count in missing_skills_on_rejection.items()
                ),
                key=lambda s: (-s["count"], s["name"]),
            ),
        }

    @staticmethod
    def _parse_buckets(raw: str) -> list[int]:
        """Parse configurable bucket boundaries, e.g. '40,55,70,85'."""
        try:
            values = [int(v.strip()) for v in raw.split(",") if v.strip()]
        except ValueError:
            return [40, 55, 70, 85]
        return values or [40, 55, 70, 85]
