"""Adaptive threshold suggestions from accumulated feedback data.

Phase 5 (task specs #18, #32): the feedback loop (Phase 4) now collects
per-score-bucket outcomes. This advisor analyzes them and *proposes* threshold
adjustments. It is read-only: runtime behaviour is never changed automatically
— thresholds stay configuration (``LLM_GATE_MIN_DETERMINISTIC_SCORE``,
ranking thresholds), suggestions are exposed via
``GET /api/v1/analytics/feedback/threshold-suggestions``.

No ML (spec #17): simple deterministic rate analysis, plus explicit minimum
data requirements before any suggestion is produced.
"""

import re

from pydantic import BaseModel, Field


class ThresholdSuggestion(BaseModel):
    """Proposal derived from feedback data; None = not enough data yet."""

    suggested_min_llm_score: int | None = Field(
        None,
        description=(
            "Lower bound of the best-performing score bucket — a candidate "
            "value for LLM_GATE_MIN_DETERMINISTIC_SCORE"
        ),
    )
    suggested_skip_below: int | None = Field(
        None,
        description=(
            "Below this score no interviews were observed — safe to skip "
            "LLM analysis entirely"
        ),
    )
    best_bucket: str | None = Field(None, description="Bucket with the highest interview rate")
    data_points: int = Field(0, description="Applications considered across buckets")
    insights: list[str] = Field(default_factory=list)


def _num(row: dict, *keys: str) -> int:
    for key in keys:
        value = row.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def _bucket_lower(label: str) -> int | None:
    """Extract the numeric lower bound from a bucket label like '40-54'."""
    match = re.search(r"\d+", str(label or ""))
    return int(match.group()) if match else None


class ThresholdAdvisor:
    """Deterministic advisor over score-bucket feedback statistics."""

    def __init__(self, min_applications_per_bucket: int = 5):
        self.min_applications = max(int(min_applications_per_bucket), 1)

    def suggest(self, buckets: list[dict]) -> ThresholdSuggestion:
        """Analyze normalized bucket rows: {bucket, applications, interviews}."""
        rows: list[dict] = []
        for bucket in buckets or []:
            applications = _num(bucket, "applications", "total", "count")
            if applications <= 0:
                continue
            interviews = _num(bucket, "interviews")
            rows.append(
                {
                    "label": str(bucket.get("bucket") or bucket.get("label") or "?"),
                    "lower": _bucket_lower(bucket.get("bucket") or bucket.get("label")),
                    "applications": applications,
                    "interviews": interviews,
                    "rate": interviews / applications,
                }
            )

        insights: list[str] = []
        if not rows:
            return ThresholdSuggestion(
                insights=[
                    "No application outcomes yet — collect feedback first (spec #17)"
                ]
            )

        total_applications = sum(row["applications"] for row in rows)
        total_interviews = sum(row["interviews"] for row in rows)
        insights.append(
            f"Considered {total_applications} applications, {total_interviews} interviews"
        )

        # Prefer statistically meaningful buckets; fall back to all data when sparse.
        qualified = [r for r in rows if r["applications"] >= self.min_applications]
        if not qualified:
            insights.append(
                f"Fewer than {self.min_applications} applications per bucket — "
                "suggestions are provisional"
            )
            qualified = rows

        best = max(qualified, key=lambda r: (r["rate"], r["applications"]))
        insights.append(
            f"Best bucket: {best['label']} "
            f"(interview rate {best['rate']:.0%} on {best['applications']} applications)"
        )

        # Skip-below suggestion: the lower bound of the first bucket that
        # produced interviews — everything below it produced none.
        with_interviews = [
            r for r in qualified if r["interviews"] > 0 and r["lower"] is not None
        ]
        suggested_skip_below = (
            min(r["lower"] for r in with_interviews) if with_interviews else None
        )
        if suggested_skip_below in (None, 0):
            # Either no interviews at all, or interviews exist from the very
            # first bucket — there is nothing safe to skip.
            suggested_skip_below = None
        else:
            insights.append(
                f"No interviews below {suggested_skip_below} — "
                "consider skipping LLM analysis for lower scores"
            )

        return ThresholdSuggestion(
            suggested_min_llm_score=best["lower"],
            suggested_skip_below=suggested_skip_below,
            best_bucket=best["label"],
            data_points=total_applications,
            insights=insights,
        )

    def suggest_from_response(self, stats) -> ThresholdSuggestion:
        """Adapter over FeedbackAnalyticsService output (attr- or dict-based)."""
        raw_buckets = (
            getattr(stats, "score_buckets", None)
            or (stats.get("score_buckets") if isinstance(stats, dict) else None)
            or []
        )
        buckets: list[dict] = []
        for row in raw_buckets:
            if isinstance(row, dict):
                buckets.append(row)
            else:  # pydantic model
                buckets.append(
                    {
                        "bucket": getattr(row, "bucket", None)
                        or getattr(row, "label", None),
                        "applications": getattr(row, "applications", None)
                        or getattr(row, "total", None)
                        or getattr(row, "count", 0),
                        "interviews": getattr(row, "interviews", 0),
                    }
                )
        return self.suggest(buckets)
