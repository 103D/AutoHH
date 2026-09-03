"""Prometheus metrics for AutoHH pipelines (task spec #22).

Counters/histograms are registered once at import time and exposed via the
``/metrics`` ASGI endpoint (mounted in main.py when metrics are enabled).
All helpers are safe no-ops when ``settings.metrics_enabled`` is false —
observability must never break the pipeline.

Covered outcomes (Phase 5 scope — matching/LLM pipeline):
- match analysis duration by outcome (analyzed / cached / hard_filtered / llm_skipped)
- LLM calls by kind (called / cache_hit / gate_skipped / hard_filtered / error)
- accumulated LLM cost in USD

Fetch/ingest counters are pre-registered for the workers to adopt later.
"""

from prometheus_client import REGISTRY, Counter, Histogram

from app.core.config import settings

# --- Ingestion (workers) ---
JOB_FETCH_TOTAL = Counter(
    "autohh_job_fetch_total",
    "Job fetch attempts by source and status",
    ["source", "status"],
)
JOB_INGESTED_TOTAL = Counter(
    "autohh_job_ingested_total",
    "Jobs ingested by outcome (new/duplicate/error)",
    ["source", "outcome"],
)

# --- Matching / LLM pipeline ---
MATCH_ANALYSIS_DURATION = Histogram(
    "autohh_match_analysis_duration_seconds",
    "Time spent analyzing one job, by outcome",
    ["outcome"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
LLM_CALLS_TOTAL = Counter(
    "autohh_llm_calls_total",
    "AI provider calls by kind",
    ["provider", "kind"],
)
LLM_COST_USD_TOTAL = Counter(
    "autohh_llm_cost_usd_total",
    "Accumulated LLM cost in USD",
    ["provider"],
)
MATCH_RECOMMENDATIONS_TOTAL = Counter(
    "autohh_match_recommendations_total",
    "Final match recommendations produced (by category)",
    ["recommendation"],
)


def metrics_enabled() -> bool:
    """Feature flag; defaults to True when not configured."""
    return bool(getattr(settings, "metrics_enabled", True))


def _sample_value(name: str, labels: dict[str, str]) -> float | None:
    """Test helper: current value of a single-sample metric, if present."""
    try:
        return REGISTRY.get_sample_value(name, labels)
    except (KeyError, ValueError):
        return None


def observe_analysis(duration_s: float, outcome: str) -> None:
    """Record one analyze_job() call duration with its outcome."""
    if not metrics_enabled():
        return
    try:
        MATCH_ANALYSIS_DURATION.labels(outcome=outcome).observe(max(duration_s, 0.0))
    except Exception:  # metrics must never break the pipeline
        pass


def inc_llm(provider: str, kind: str) -> None:
    """Count one LLM event (called / cache_hit / gate_skipped / hard_filtered / error)."""
    if not metrics_enabled():
        return
    try:
        LLM_CALLS_TOTAL.labels(provider=provider or "unknown", kind=kind).inc()
    except Exception:
        pass


def add_llm_cost(provider: str, cost_usd: float) -> None:
    """Accumulate LLM spending in USD."""
    if not metrics_enabled() or not cost_usd:
        return
    try:
        LLM_COST_USD_TOTAL.labels(provider=provider or "unknown").inc(float(cost_usd))
    except Exception:
        pass


def inc_match_recommendation(recommendation: str, amount: int = 1) -> None:
    """Count final match recommendation categories (worker-level view)."""
    if not metrics_enabled() or amount <= 0:
        return
    try:
        MATCH_RECOMMENDATIONS_TOTAL.labels(
            recommendation=recommendation or "unknown"
        ).inc(amount)
    except Exception:
        pass


def inc_job_fetch(source: str, status: str) -> None:
    """Count one fetch task outcome per source (success/error/skipped)."""
    if not metrics_enabled():
        return
    try:
        JOB_FETCH_TOTAL.labels(source=source or "unknown", status=status).inc()
    except Exception:
        pass


def inc_job_ingested(source: str, outcome: str, amount: int = 1) -> None:
    """Count ingestion outcomes per source (new/duplicate/error)."""
    if not metrics_enabled() or amount <= 0:
        return
    try:
        JOB_INGESTED_TOTAL.labels(source=source or "unknown", outcome=outcome).inc(amount)
    except Exception:
        pass
