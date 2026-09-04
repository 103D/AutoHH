"""Tests for deterministic resume selection (task spec #16)."""

from uuid import uuid4

from app.models.candidate import ResumeProfile
from app.models.job import Job
from app.services.resume_selection import ResumeSelector


def make_job(**kwargs) -> Job:
    defaults: dict = {
        "id": uuid4(),
        "source_id": uuid4(),
        "external_id": "hh_1",
        "title": "Data Analyst",
        "company": "Corp",
        "description": "SQL, reporting, dashboards.",
        "url": "https://hh.kz/vacancy/1",
        "url_normalized": "https://hh.kz/vacancy/1",
        "content_hash": "hash1",
        "raw_data": {},
    }
    defaults.update(kwargs)
    return Job(**defaults)


def make_profile(**kwargs) -> ResumeProfile:
    defaults: dict = {
        "id": uuid4(),
        "candidate_profile_id": uuid4(),
        "specialization": "DATA_ANALYST",
        "profile_name": "cv_data",
        "selected_skills": ["SQL", "PostgreSQL"],
        "selected_experience_ids": [],
        "selected_project_ids": [],
        "specialization_keywords": ["data analyst", "отчетность"],
        "is_active": True,
    }
    defaults.update(kwargs)
    return ResumeProfile(**defaults)


def test_specialization_match_wins():
    selector = ResumeSelector()
    retail = make_profile(
        specialization="RETAIL_COMMERCIAL_ANALYST",
        profile_name="cv_retail",
        specialization_keywords=["retail"],
    )
    data = make_profile()
    job = make_job(specializations=["DATA_ANALYST"])

    result = selector.recommend(job, [retail, data])

    assert result.recommended_profile_name == "cv_data"
    assert result.recommended_specialization == "DATA_ANALYST"
    assert any("specialization" in r for r in result.reasons)


def test_reasons_explain_choice():
    selector = ResumeSelector()
    profile = make_profile(
        specialization="RETAIL_COMMERCIAL_ANALYST",
        profile_name="cv_retail",
        specialization_keywords=["retail analytics", "inventory"],
        selected_skills=["SQL", "PostgreSQL", "Power BI"],
    )
    job = make_job(
        title="Retail Data Analyst",
        description="Retail analytics: inventory reports in SQL and PostgreSQL.",
        specializations=["RETAIL_COMMERCIAL_ANALYST"],
    )

    result = selector.recommend(job, [profile])

    assert result.recommended_profile_id == profile.id
    # Task spec #16 example: specialization + domain keywords + skills
    assert any("RETAIL_COMMERCIAL_ANALYST" in r for r in result.reasons)
    assert any("keywords" in r for r in result.reasons)
    assert any("SQL" in r for r in result.reasons)


def test_no_confident_match_returns_empty_recommendation():
    selector = ResumeSelector()
    profile = make_profile(specialization_keywords=["quantum physics"])
    job = make_job(title="Cook", description="Baking.", specializations=[])

    result = selector.recommend(job, [profile])

    assert result.recommended_profile_id is None
    assert result.scores  # scores still computed for transparency


def test_inactive_profile_excluded():
    selector = ResumeSelector()
    profile = make_profile(is_active=False)
    job = make_job(specializations=["DATA_ANALYST"])

    result = selector.recommend(job, [profile])

    assert result.scores == []
    assert result.recommended_profile_id is None


def test_scores_sorted_descending():
    selector = ResumeSelector()
    strong = make_profile(profile_name="cv_strong")
    weak = make_profile(
        profile_name="cv_weak",
        specialization="RETAIL_COMMERCIAL_ANALYST",
        specialization_keywords=[" unrelated "],
    )
    job = make_job(specializations=["DATA_ANALYST"])

    result = selector.recommend(job, [weak, strong])

    assert result.scores[0].profile_name == "cv_strong"
    assert result.scores[0].score >= result.scores[1].score


def test_skills_matched_via_taxonomy():
    selector = ResumeSelector()
    profile = make_profile(selected_skills=["PostgreSQL"])
    # Vacancy mentions the alias "postgres", not the canonical name
    job = make_job(description="postgres tuning required.", specializations=[])

    result = selector.recommend(job, [profile])

    assert any("PostgreSQL" in r for r in result.reasons)


def test_multi_spec_job_picks_best_profile_not_first():
    """A vacancy with several suitable specializations must pick the best
    matching profile, not the first one in the list."""
    selector = ResumeSelector()
    # Listed first but only weakly relevant to this retail-leaning job.
    generic = make_profile(
        profile_name="cv_generic",
        specialization="DATA_ANALYST",
        specialization_keywords=["generic reporting"],
        selected_skills=[],
    )
    # Better fit: retail specialization + matching domain keywords/skills.
    retail = make_profile(
        profile_name="cv_retail",
        specialization="RETAIL_COMMERCIAL_ANALYST",
        specialization_keywords=["retail analytics", "sales"],
        selected_skills=["SQL"],
    )
    job = make_job(
        title="Retail Data Analyst",
        description="Retail analytics and sales reporting in SQL.",
        specializations=["DATA_ANALYST", "RETAIL_COMMERCIAL_ANALYST"],
    )

    # Retail profile is passed SECOND; selection must still prefer it.
    result = selector.recommend(job, [generic, retail])

    assert result.recommended_profile_name == "cv_retail"
    assert result.recommended_specialization == "RETAIL_COMMERCIAL_ANALYST"
    assert result.scores[0].profile_name == "cv_retail"


def test_legacy_job_without_specializations_field():
    """Jobs created before Phase 2 may have specializations=None."""
    selector = ResumeSelector()
    profile = make_profile()
    job = make_job(specializations=None)

    result = selector.recommend(job, [profile])

    # Specialization not matched, but keywords/skills still work
    assert result.recommended_profile_name == "cv_data"
    assert result.job_specializations == []
