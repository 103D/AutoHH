"""End-to-end pipeline test (PROMPT.MD #16, Definition of Done).

manual vacancy -> normalize -> deduplicate -> persist -> matching
-> resume recommendation -> application -> status update -> history.

Runs over the real HTTP layer (ASGITransport) against the real test
database; only the AI provider is mocked (no network).
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.providers.ai.base import MatchResult as AIMatchResult
from app.providers.ai.base import SkillMatch

def make_profile_payload() -> dict:
    """Fresh payload per test (unique user_id; no cross-run state)."""
    return {
        "user_id": str(uuid4()),
        "desired_positions": ["Data Analyst"],
        "skills": ["SQL", "Python", "Tableau"],
        "technologies": {"languages": ["Python", "SQL"], "tools": ["Tableau", "Power BI"]},
        "experience_years": 3,
        "experience_level": "middle",
        "languages": {"Russian": "native", "English": "B2"},
        "location": "Almaty",
        "desired_salary_min": 400000,
        "desired_salary_max": 600000,
        "salary_currency": "KZT",
        "employment_types": ["full_time"],
        "work_formats": ["remote", "hybrid"],
        "relocation_possible": False,
        "business_trips_acceptable": True,
        "resume_versions": {
            "original": "SQL, Python, Tableau analyst with 3 years experience."
        },
    }

MANUAL_PAYLOAD = {
    "title": "Data Analyst",
    "company": "Kaspi Bank",
    "description": (
        "Build SQL dashboards and Python automation for business reporting. "
        "Retail analytics experience is a plus."
    ),
    "location": "Almaty",
    "salary_min": 500000,
    "salary_max": 800000,
    "currency": "KZT",
    "employment_type": "full_time",
    "work_format": "hybrid",
}

RESUME_PROFILE_PAYLOAD = {
    "specialization": "DATA_ANALYST",
    "profile_name": "Data Analyst CV",
    "headline": "Data Analyst | SQL & Python",
    "summary": "Analyst with 3 years of SQL reporting experience.",
    "selected_skills": ["SQL", "Python"],
    "selected_experience_ids": [],
    "selected_project_ids": [],
    "specialization_keywords": ["data analyst", "sql", "reporting"],
}


@pytest.fixture
def mock_ai(monkeypatch):
    """Deterministic AI provider: no network in E2E."""
    ai_result = AIMatchResult(
        score=78,
        recommendation="APPLY",
        matched_skills=[SkillMatch(skill="SQL", match_type="exact", confidence=1.0)],
        missing_skills=["Cohort Analysis"],
        strong_matches=["SQL", "Python"],
        concerns=[],
        reasoning_summary="Strong SQL/Python match for an analyst role.",
        tokens_used=150,
        cost_usd=0.002,
    )
    provider = MagicMock()
    provider.name = "mock-ai"
    provider.analyze_job = AsyncMock(return_value=ai_result)
    monkeypatch.setattr(
        "app.services.matching.create_ai_provider", lambda *a, **k: provider
    )
    return provider


@pytest.mark.asyncio
async def test_e2e_manual_import_to_application_history(cleanup_db, mock_ai):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Candidate profile
        r = await client.post("/api/v1/profile/", json=make_profile_payload())
        assert r.status_code == 201, r.text
        profile_id = r.json()["id"]

        # 2. Resume profile (references master skills only)
        r = await client.post(
            f"/api/v1/profile/{profile_id}/resume-profiles",
            json=RESUME_PROFILE_PAYLOAD,
        )
        assert r.status_code == 201, r.text
        resume_profile_id = r.json()["id"]

        # 3. Manual import -> created
        r = await client.post("/api/v1/jobs/manual", json=MANUAL_PAYLOAD)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "created"
        assert body["duplicate_of"] is None
        job = body["job"]
        job_id = job["id"]
        assert job["source_type"] == "manual" or job["source"] == "manual"
        assert job["specializations"] == ["DATA_ANALYST"]

        # 4. Idempotent re-import -> duplicate, same job
        r = await client.post("/api/v1/jobs/manual", json=MANUAL_PAYLOAD)
        assert r.status_code == 200, r.text
        body2 = r.json()
        assert body2["status"] == "duplicate"
        assert str(body2["duplicate_of"]) == job_id
        assert body2["job"]["id"] == job_id

        # 5. Jobs listing: exactly one manual job; get by id works
        r = await client.get("/api/v1/jobs/", params={"source": "manual"})
        assert r.status_code == 200
        assert len(r.json()) == 1
        r = await client.get(f"/api/v1/jobs/{job_id}")
        assert r.status_code == 200

        # 6. Matching: analyze (hard filters pass, mock AI merges score).
        # Explicit candidate_profile_id: the default-profile lookup returns
        # an arbitrary first profile, and other tests may have created some.
        r = await client.post(
            f"/api/v1/matching/jobs/{job_id}/analyze",
            params={"candidate_profile_id": profile_id},
        )
        assert r.status_code == 200, r.text
        match = r.json()
        assert match["score"] > 0
        assert match["hard_failures"] == []
        assert match["recommendation"]

        # 7. Resume recommendation: deterministic, explained
        r = await client.post(
            f"/api/v1/matching/jobs/{job_id}/recommend-resume",
            params={"candidate_profile_id": profile_id},
        )
        assert r.status_code == 200, r.text
        rec = r.json()
        assert str(rec["recommended_profile_id"]) == resume_profile_id
        assert rec["recommended_specialization"] == "DATA_ANALYST"
        assert rec["reasons"]

        # 8. Application lifecycle
        r = await client.post(
            "/api/v1/applications/",
            json={"job_id": job_id, "candidate_profile_id": profile_id},
        )
        assert r.status_code == 201, r.text
        application = r.json()
        application_id = application["id"]
        assert application["status"] == "DRAFT"

        r = await client.patch(
            f"/api/v1/applications/{application_id}",
            json={"status": "APPLIED", "comment": "Applied via company site"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "APPLIED"

        # 9. Immutable status history: DRAFT -> APPLIED
        r = await client.get(f"/api/v1/applications/{application_id}/history")
        assert r.status_code == 200
        history = r.json()
        assert [h["to_status"] for h in history] == ["DRAFT", "APPLIED"]

        # 10. Duplicate application is rejected
        r = await client.post(
            "/api/v1/applications/",
            json={"job_id": job_id, "candidate_profile_id": profile_id},
        )
        assert r.status_code == 409

        # The re-import stopped at dedup, so the AI was consulted exactly once.
        mock_ai.analyze_job.assert_called_once()


@pytest.mark.asyncio
async def test_e2e_manual_import_validation(cleanup_db, mock_ai):
    """Invalid manual payloads must return 422, not 500."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/api/v1/jobs/manual",
            json={"title": "Only title"},  # missing company/description
        )
        assert r.status_code == 422

        r = await client.post(
            "/api/v1/jobs/manual",
            json={
                "title": "Bad salary",
                "company": "X",
                "description": "desc",
                "salary_min": 100,
                "salary_max": 50,  # max < min
            },
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_e2e_matching_analyze_endpoint(cleanup_db, mock_ai):
    """POST /matching/analyze persists a MatchResult for a specific job."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Setup: profile + manual job
        r = await client.post("/api/v1/profile/", json=make_profile_payload())
        profile_id = r.json()["id"]
        r = await client.post("/api/v1/jobs/manual", json=MANUAL_PAYLOAD)
        job_id = r.json()["job"]["id"]

        # New endpoint: POST /matching/analyze
        r = await client.post(
            "/api/v1/matching/analyze",
            params={"job_id": job_id, "candidate_profile_id": profile_id},
        )
        assert r.status_code == 200, r.text
        match = r.json()
        assert match["score"] > 0
        assert match["recommendation"]
        assert "analyzed_at" in match

        # Result is persisted: GET /matching/jobs/{job_id}/match returns it
        r = await client.get(
            f"/api/v1/matching/jobs/{job_id}/match",
            params={"candidate_profile_id": profile_id},
        )
        assert r.status_code == 200
        assert r.json()["score"] == match["score"]


@pytest.mark.asyncio
async def test_e2e_matching_soft_match_endpoint(cleanup_db, mock_ai):
    """POST /matching/match is a lightweight deterministic match (no persistence)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Setup: profile + manual job
        r = await client.post("/api/v1/profile/", json=make_profile_payload())
        profile_id = r.json()["id"]
        r = await client.post("/api/v1/jobs/manual", json=MANUAL_PAYLOAD)
        job_id = r.json()["job"]["id"]

        # New endpoint: POST /matching/match
        r = await client.post(
            "/api/v1/matching/match",
            params={"job_id": job_id, "candidate_profile_id": profile_id},
        )
        assert r.status_code == 200, r.text
        match = r.json()
        assert 0 <= match["score"] <= 100
        assert match["recommendation"]
        assert "score_breakdown" in match
        assert "technical" in match["score_breakdown"]
        # SQL/Python/Tableau are in both profile and job description
        assert "sql" in match["matched_skills"]

        # No persistence: GET /matching/jobs/{job_id}/match returns 404
        r = await client.get(
            f"/api/v1/matching/jobs/{job_id}/match",
            params={"candidate_profile_id": profile_id},
        )
        assert r.status_code == 404
