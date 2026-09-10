"""Tests for reproducible matching input fingerprints."""

from copy import deepcopy
from types import SimpleNamespace

from app.services.match_provenance import (
    ENGINE_VERSION,
    TAXONOMY_VERSION,
    build_match_provenance,
    candidate_snapshot,
    job_snapshot,
)


def _profile(**overrides):
    data = {
        "skills": ["Python", "SQL"],
        "technologies": {"databases": ["PostgreSQL"], "tools": ["Git"]},
        "skills_metadata": {"Python": {"years": 2, "confidence": "high"}},
        "experience_years": 2,
        "experience_level": "middle",
        "experience": [{"id": "exp-1", "title": "Data Analyst", "company": "Safia"}],
        "projects": [{"id": "project-1", "name": "Retail Dashboard"}],
        "education": [{"institution": "IITU", "year": 2025}],
        "languages": {"ru": "native", "en": "C1"},
        "location": "Алматы",
        "relocation_possible": False,
        "business_trips_acceptable": True,
        "desired_salary_min": 400_000,
        "desired_salary_max": 600_000,
        "salary_currency": "KZT",
        "employment_types": ["full"],
        "work_formats": ["remote", "office"],
        "additional_preferences": {"telegram": "secret-not-a-match-input"},
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _job(**overrides):
    data = {
        "title": "Data Analyst",
        "company": "Example",
        "description": "Required SQL and Python. Power BI is preferred.",
        "location": "Алматы",
        "salary_min": 450_000,
        "salary_max": 650_000,
        "currency": "KZT",
        "employment_type": "full",
        "work_format": "remote",
        "experience_required": 2,
        "specializations": ["BI_ANALYST", "DATA_ANALYST"],
        "raw_data": {"private_note": "not-a-match-input"},
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _settings(**overrides):
    data = {
        "score_weight_technical": 0.3,
        "score_weight_experience": 0.2,
        "score_weight_location": 0.1,
        "score_weight_salary": 0.1,
        "score_weight_work_format": 0.1,
        "score_weight_education": 0.1,
        "score_weight_language": 0.1,
        "score_required_skill_weight": 3.0,
        "score_preferred_skill_weight": 1.5,
        "score_optional_skill_weight": 0.5,
        "score_missing_required_penalty": 25.0,
        "hard_filters_enabled": True,
        "hard_experience_max_factor": 1.5,
        "hard_experience_max_gap": 2.0,
        "hard_salary_tolerance": 0.2,
        "threshold_dream_job": 85,
        "threshold_stretch": 70,
        "threshold_solid_match": 55,
        "threshold_market_research": 40,
        "threshold_learning": 25,
        "stretch_experience_min_factor": 0.8,
        "stretch_experience_max_factor": 1.5,
        "stretch_max_missing_skills": 3,
        "stretch_salary_max_increase": 0.4,
        "llm_gate_enabled": True,
        "llm_gate_min_deterministic_score": 40,
        "prompt_version": "v7",
        "secret_key": "must-not-be-fingerprinted",
        "ai_api_key": "must-not-be-fingerprinted",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_candidate_fingerprint_is_stable_for_unordered_collections():
    first = _profile()
    second = _profile(
        skills=["SQL", "Python"],
        technologies={"tools": ["Git"], "databases": ["PostgreSQL"]},
        work_formats=["office", "remote"],
        languages={"en": "C1", "ru": "native"},
    )

    assert candidate_snapshot(first) == candidate_snapshot(second)
    assert build_match_provenance(first, _job(), _settings())["candidate_fingerprint"] == (
        build_match_provenance(second, _job(), _settings())["candidate_fingerprint"]
    )


def test_job_fingerprint_is_stable_for_specialization_order():
    first = _job(specializations=["DATA_ANALYST", "BI_ANALYST"])
    second = _job(specializations=["BI_ANALYST", "DATA_ANALYST"])

    assert job_snapshot(first) == job_snapshot(second)


def test_each_matching_input_changes_analysis_fingerprint():
    base = build_match_provenance(_profile(), _job(), _settings())

    changed_profile = build_match_provenance(
        _profile(desired_salary_min=500_000),
        _job(),
        _settings(),
    )
    changed_job = build_match_provenance(
        _profile(),
        _job(work_format="office"),
        _settings(),
    )
    changed_scoring = build_match_provenance(
        _profile(),
        _job(),
        _settings(score_missing_required_penalty=30.0),
    )

    assert changed_profile["analysis_fingerprint"] != base["analysis_fingerprint"]
    assert changed_job["analysis_fingerprint"] != base["analysis_fingerprint"]
    assert changed_scoring["analysis_fingerprint"] != base["analysis_fingerprint"]


def test_versions_change_analysis_fingerprint():
    base = build_match_provenance(_profile(), _job(), _settings())
    prompt = build_match_provenance(_profile(), _job(), _settings(prompt_version="v8"))
    engine = build_match_provenance(
        _profile(), _job(), _settings(), engine_version="match-v4"
    )
    taxonomy = build_match_provenance(
        _profile(), _job(), _settings(), taxonomy_version="taxonomy-v2"
    )

    assert base["engine_version"] == ENGINE_VERSION
    assert base["taxonomy_version"] == TAXONOMY_VERSION
    assert prompt["analysis_fingerprint"] != base["analysis_fingerprint"]
    assert engine["analysis_fingerprint"] != base["analysis_fingerprint"]
    assert taxonomy["analysis_fingerprint"] != base["analysis_fingerprint"]


def test_secrets_and_unrelated_metadata_do_not_affect_fingerprint():
    profile = _profile()
    job = _job()
    settings = _settings()
    base = build_match_provenance(profile, job, settings)

    changed_profile = deepcopy(profile)
    changed_profile.additional_preferences = {"telegram": "different-secret"}
    changed_job = deepcopy(job)
    changed_job.raw_data = {"private_note": "different"}
    changed_settings = deepcopy(settings)
    changed_settings.secret_key = "different-secret"
    changed_settings.ai_api_key = "different-api-key"

    changed = build_match_provenance(changed_profile, changed_job, changed_settings)

    assert changed["analysis_fingerprint"] == base["analysis_fingerprint"]
    assert "secret" not in repr(changed).lower()
