"""Tests for Prometheus metrics helpers (task spec #22)."""

import pytest

from app.core import metrics
from app.core.config import settings


def test_inc_llm_counts_events(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    labels = {"provider": "prov", "kind": "called"}
    before = metrics._sample_value("autohh_llm_calls_total", labels) or 0

    metrics.inc_llm("prov", "called")

    assert metrics._sample_value("autohh_llm_calls_total", labels) == before + 1


def test_add_llm_cost_accumulates(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    labels = {"provider": "costtest"}
    before = metrics._sample_value("autohh_llm_cost_usd_total", labels) or 0

    metrics.add_llm_cost("costtest", 0.25)

    after = metrics._sample_value("autohh_llm_cost_usd_total", labels)
    assert after == pytest.approx(before + 0.25)


def test_zero_cost_is_ignored(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    labels = {"provider": "nocost"}

    metrics.add_llm_cost("nocost", 0.0)

    assert metrics._sample_value("autohh_llm_cost_usd_total", labels) is None


def test_ingestion_counters(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)

    metrics.inc_job_fetch("srct", "success")
    metrics.inc_job_ingested("srct", "new", amount=3)

    assert (
        metrics._sample_value(
            "autohh_job_fetch_total", {"source": "srct", "status": "success"}
        )
        or 0
    ) >= 1
    assert (
        metrics._sample_value(
            "autohh_job_ingested_total", {"source": "srct", "outcome": "new"}
        )
        or 0
    ) >= 3


def test_zero_amount_ingestion_is_noop(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    labels = {"source": "nosrc", "outcome": "new"}

    metrics.inc_job_ingested("nosrc", "new", amount=0)

    assert metrics._sample_value("autohh_job_ingested_total", labels) is None


def test_disabled_metrics_are_noop(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", False)

    metrics.inc_llm("noop", "called")
    metrics.observe_analysis(1.0, "analyzed")
    metrics.add_llm_cost("noop", 1.0)
    metrics.inc_job_fetch("noop", "success")
    metrics.inc_job_ingested("noop", "new")

    assert metrics._sample_value("autohh_llm_calls_total", {"provider": "noop", "kind": "called"}) is None
    assert metrics._sample_value("autohh_llm_cost_usd_total", {"provider": "noop"}) is None
    assert metrics._sample_value("autohh_job_fetch_total", {"source": "noop", "status": "success"}) is None


def test_observe_analysis_records(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    before = metrics._sample_value("autohh_match_analysis_duration_seconds_count", {"outcome": "analyzed"}) or 0

    metrics.observe_analysis(0.2, "analyzed")

    after = metrics._sample_value("autohh_match_analysis_duration_seconds_count", {"outcome": "analyzed"})
    assert after == before + 1
