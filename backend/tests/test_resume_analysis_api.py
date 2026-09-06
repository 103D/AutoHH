"""HTTP contract tests for deterministic resume analysis."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_resume_analysis_accepts_structured_job_requirements():
    resume = """Candidate Name
candidate@example.com

Experience
Data Analyst
Example Inc
2024 - 2026
- Analyzed sales data using SQL

Skills
SQL, Python

Education
Example University
2025
"""

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/resume/analyze",
            json={
                "resume_text": resume,
                "job_requirements": [
                    {"skill": "SQL", "importance": "REQUIRED"},
                    {"skill": "MySQL", "importance": "PREFERRED"},
                ],
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["evidence"][0]["requirement"] == "SQL"
    assert body["evidence"][0]["strength"] == "explicit"
    assert body["evidence"][1]["requirement"] == "MySQL"
    assert body["evidence"][1]["strength"] == "missing"
    assert body["bullet_analysis_total"] == len(body["bullet_analysis"])
    assert body["bullet_analysis_truncated"] is False
    assert body["bullet_analysis"][0]["experience_index"] == 0
    assert body["bullet_analysis"][0]["bullet_index"] == 0
    assert body["bullet_analysis"][0]["issues"]


@pytest.mark.asyncio
async def test_resume_analysis_rejects_oversized_payload():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/resume/analyze",
            json={"resume_text": "x" * 100_001},
        )

    assert response.status_code == 422
