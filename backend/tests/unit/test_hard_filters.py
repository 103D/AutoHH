"""Tests for hard requirement filtering (task spec #8)."""

import pytest

from app.core.config import settings
from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.services.hard_filters import HardFilterEngine


@pytest.fixture
def engine() -> HardFilterEngine:
    return HardFilterEngine()


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        id="00000000-0000-0000-0000-0000000000aa",
        user_id="00000000-0000-0000-0000-0000000000bb",
        experience_years=3,
        location="Almaty",
        desired_salary_min=500000,
        salary_currency="KZT",
        employment_types=["full_time"],
        work_formats=["remote", "hybrid"],
        relocation_possible=False,
        resume_versions={},
    )


@pytest.fixture
def job() -> Job:
    return Job(
        id="00000000-0000-0000-0000-0000000000cc",
        source_id="00000000-0000-0000-0000-0000000000dd",
        external_id="hh_1",
        title="Data Analyst",
        company="Corp",
        description="SQL, dashboards, reporting.",
        location="Almaty",
        salary_min=450000,
        salary_max=650000,
        currency="KZT",
        employment_type="full_time",
        work_format="hybrid",
        url="https://hh.kz/vacancy/1",
        published_at="2026-01-01T00:00:00Z",
        first_seen_at="2026-01-01T00:00:00Z",
        last_seen_at="2026-01-01T00:00:00Z",
        content_hash="h1",
        url_normalized="https://hh.kz/vacancy/1",
        raw_data={},
    )


def test_all_requirements_met_passes(engine, profile, job):
    result = engine.evaluate(profile, job)
    assert result.passed
    assert result.failures == []


def test_experience_requirement_fails(engine, profile, job):
    job.experience_required = 10  # max allowed = 3 * 1.5 = 4.5
    result = engine.evaluate(profile, job)
    assert not result.passed
    assert any(f.startswith("experience") for f in result.failures)


def test_experience_within_factor_passes(engine, profile, job):
    job.experience_required = 4
    assert engine.evaluate(profile, job).passed


def test_office_only_fails_for_remote_candidate(engine, profile, job):
    job.work_format = "office"
    result = engine.evaluate(profile, job)
    assert not result.passed
    assert any(f.startswith("work_format") for f in result.failures)


def test_location_mismatch_fails_without_relocation(engine, profile, job):
    job.location = "Moscow"
    result = engine.evaluate(profile, job)
    assert not result.passed
    assert any(f.startswith("location") for f in result.failures)


def test_location_mismatch_ok_with_relocation(engine, profile, job):
    profile.relocation_possible = True
    job.location = "Moscow"
    assert engine.evaluate(profile, job).passed


def test_remote_job_ignores_location(engine, profile, job):
    job.location = "Moscow"
    job.work_format = "remote"
    assert engine.evaluate(profile, job).passed


def test_employment_type_mismatch_fails(engine, profile, job):
    job.employment_type = "part_time"
    result = engine.evaluate(profile, job)
    assert not result.passed
    assert any(f.startswith("employment_type") for f in result.failures)


def test_salary_below_floor_fails(engine, profile, job):
    job.salary_max = 350000  # floor = 500000 * 0.8 = 400000
    result = engine.evaluate(profile, job)
    assert not result.passed
    assert any(f.startswith("salary") for f in result.failures)


def test_salary_within_tolerance_passes(engine, profile, job):
    job.salary_max = 420000
    assert engine.evaluate(profile, job).passed


def test_currency_mismatch_skips_salary_check(engine, profile, job):
    profile.salary_currency = "USD"
    job.currency = "KZT"
    job.salary_max = 100
    assert engine.evaluate(profile, job).passed


def test_missing_data_is_skip_tolerant(engine, profile, job):
    job.experience_required = None
    job.location = None
    job.employment_type = None
    job.work_format = None
    job.salary_max = None
    profile.location = None
    assert engine.evaluate(profile, job).passed


def test_city_aliases_normalized(engine, profile, job):
    profile.location = "Almaty"
    job.location = "алматы"
    assert engine.evaluate(profile, job).passed


def test_disabled_via_settings(engine, profile, job, monkeypatch):
    monkeypatch.setattr(settings, "hard_filters_enabled", False)
    job.experience_required = 10
    assert engine.evaluate(profile, job).passed


# --- hard_experience_max_factor / hard_experience_max_gap (documented rule) ---


def test_junior_zero_years_not_blocked_by_gap(engine, profile, job):
    """0 documented years must not silently block an entry vacancy.

    With only the multiplicative factor, 0 x 1.5 = 0 would block every
    vacancy; the absolute gap buffer (years + gap) keeps entry roles open.
    """
    profile.experience_years = 0
    job.experience_required = 1  # entry "1+ year"; max(0*1.5, 0+2) = 2
    assert engine.evaluate(profile, job).passed


def test_junior_zero_years_blocked_above_gap(engine, profile, job):
    profile.experience_years = 0
    job.experience_required = 5  # way above the 0 + 2 buffer
    result = engine.evaluate(profile, job)
    assert not result.passed
    assert any(f.startswith("experience") for f in result.failures)


def test_experience_exactly_at_boundary_passes(engine, profile, job):
    # candidate 3y, gap 2 -> allowed up to max(4.5, 5) = 5
    profile.experience_years = 3
    job.experience_required = 5
    assert engine.evaluate(profile, job).passed


def test_experience_just_above_boundary_fails(engine, profile, job):
    profile.experience_years = 3
    job.experience_required = 6  # above the allowed 5
    result = engine.evaluate(profile, job)
    assert not result.passed
    assert any(f.startswith("experience") for f in result.failures)
