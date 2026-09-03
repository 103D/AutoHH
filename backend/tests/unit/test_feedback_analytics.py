"""Tests for feedback-loop analytics (task spec #17).

Pure deterministic aggregation over canned (application, match, job,
resume_profile) rows — no DB, no LLM.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.feedback_analytics import (
    FeedbackAnalyticsService,
    _bucket_for_score,
)

_parse_buckets = FeedbackAnalyticsService._parse_buckets


class FakeRepo:
    def __init__(self, rows):
        self._rows = rows

    async def list_feedback_dataset(self, candidate_profile_id=None):
        return self._rows


def _app(status="APPLIED", rejection_reason=None):
    return SimpleNamespace(status=status, rejection_reason=rejection_reason)


def _match(score=None, missing_skills=None):
    return SimpleNamespace(score=score, missing_skills=missing_skills or [])


def _job(specializations=None):
    return SimpleNamespace(specializations=specializations or [])


def _profile(name="Retail CV", specialization="RETAIL_COMMERCIAL_ANALYST"):
    return SimpleNamespace(id=uuid4(), profile_name=name, specialization=specialization)


def _make_service(rows):
    return FeedbackAnalyticsService(FakeRepo(rows))


# === Score buckets ===


def test_bucket_labels():
    buckets = [40, 55, 70, 85]
    assert _bucket_for_score(30, buckets) == "<40"
    assert _bucket_for_score(45, buckets) == "40-54"
    assert _bucket_for_score(55, buckets) == "55-69"
    assert _bucket_for_score(84, buckets) == "70-84"
    assert _bucket_for_score(85, buckets) == ">=85"
    assert _bucket_for_score(None, buckets) == "unknown"


def test_parse_buckets_fallback():
    assert _parse_buckets("40,55,70,85") == [40, 55, 70, 85]
    assert _parse_buckets(" 40 , 70 ") == [40, 70]
    assert _parse_buckets("oops") == [40, 55, 70, 85]
    assert _parse_buckets("") == [40, 55, 70, 85]


@pytest.mark.asyncio
async def test_empty_dataset():
    service = _make_service([])
    report = await service.feedback_report()
    assert report["total_applications"] == 0
    assert report["score_buckets"] == []
    assert report["response_rate"] == 0.0


@pytest.mark.asyncio
async def test_score_buckets_ordering_and_rates():
    rows = [
        (_app("APPLIED"), _match(30), _job(), None),          # <40, no response
        (_app("SCREENING"), _match(45), _job(), None),        # 40-54, response
        (_app("INTERVIEW"), _match(60), _job(), None),        # 55-69, response+interview
        (_app("OFFER"), _match(90), _job(), None),            # >=85, response+interview+offer
    ]
    report = await _make_service(rows).feedback_report()

    assert report["total_applications"] == 4
    assert report["responded"] == 3
    assert report["interviews"] == 2
    assert report["response_rate"] == 75.0
    assert report["interview_rate"] == 50.0

    labels = [b["bucket"] for b in report["score_buckets"]]
    assert labels == ["<40", "40-54", "55-69", ">=85"]
    by_label = {b["bucket"]: b for b in report["score_buckets"]}
    assert by_label["<40"]["applications"] == 1
    assert by_label["<40"]["responses"] == 0
    assert by_label[">=85"]["offers"] == 1


@pytest.mark.asyncio
async def test_unknown_bucket_when_no_match():
    rows = [(_app("APPLIED"), None, _job(), None)]
    report = await _make_service(rows).feedback_report()
    assert [b["bucket"] for b in report["score_buckets"]] == ["unknown"]


@pytest.mark.asyncio
async def test_resume_profile_stats():
    p1, p2 = _profile("Retail CV"), _profile("BI CV", "BI_ANALYST")
    rows = [
        (_app("INTERVIEW"), _match(70), _job(), p1),
        (_app("REJECTED", "seniority"), _match(50), _job(), p1),
        (_app("APPLIED"), _match(60), _job(), p2),
    ]
    report = await _make_service(rows).feedback_report()

    profiles = {p["profile_name"]: p for p in report["resume_profiles"]}
    assert profiles["Retail CV"]["applications"] == 2
    assert profiles["Retail CV"]["interviews"] == 1
    assert profiles["Retail CV"]["interview_rate"] == 50.0
    assert profiles["BI CV"]["applications"] == 1
    # Profiles with interviews rank first
    assert report["resume_profiles"][0]["profile_name"] == "Retail CV"


@pytest.mark.asyncio
async def test_specialization_multilabel_tally():
    rows = [
        (_app("INTERVIEW"), _match(70), _job(["BI_ANALYST", "RETAIL_COMMERCIAL_ANALYST"]), None),
    ]
    report = await _make_service(rows).feedback_report()
    specs = {s["specialization"]: s for s in report["specializations"]}
    assert specs["BI_ANALYST"]["applications"] == 1
    assert specs["RETAIL_COMMERCIAL_ANALYST"]["interviews"] == 1


@pytest.mark.asyncio
async def test_rejection_reasons_and_missing_skills():
    rows = [
        (_app("REJECTED", "seniority"), _match(50, ["DAX", "Cohort Analysis"]), _job(), None),
        (_app("REJECTED", "seniority"), _match(45, ["DAX"]), _job(), None),
        (_app("REJECTED", None), _match(40, []), _job(), None),
    ]
    report = await _make_service(rows).feedback_report()

    assert report["rejection_reasons"] == [
        {"name": "seniority", "count": 2},
        {"name": "unspecified", "count": 1},
    ]
    assert report["missing_skills_on_rejection"] == [
        {"name": "DAX", "count": 2},
        {"name": "Cohort Analysis", "count": 1},
    ]
