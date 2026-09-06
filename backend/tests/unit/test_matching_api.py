"""Unit tests for matching API error and validation semantics."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.matching import adapt_resume
from app.schemas.matching import ResumeAdaptRequest


class _AIProvider:
    def __init__(self, adapted_resume: str):
        self.adapted_resume = adapted_resume

    async def adapt_resume(self, **_kwargs):
        return self.adapted_resume


@pytest.mark.asyncio
async def test_adapt_resume_preserves_job_not_found_status():
    service = SimpleNamespace(
        job_repository=SimpleNamespace(get=lambda _job_id: _async(None)),
        ai_provider=_AIProvider("unused"),
    )

    with pytest.raises(HTTPException) as error:
        await adapt_resume(
            ResumeAdaptRequest(job_id=uuid4(), resume_text="Original resume text " * 4),
            service,
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_adapt_resume_rejects_unsupported_generated_content():
    job = SimpleNamespace(
        id=uuid4(),
        title="Data Analyst",
        description="SQL and Python",
    )
    service = SimpleNamespace(
        job_repository=SimpleNamespace(get=lambda _job_id: _async(job)),
        ai_provider=_AIProvider(
            "Data Analyst with Python and Kubernetes. " * 3
        ),
    )

    with pytest.raises(HTTPException) as error:
        await adapt_resume(
            ResumeAdaptRequest(
                job_id=job.id,
                resume_text="Data Analyst with Python experience. " * 3,
            ),
            service,
        )

    assert error.value.status_code == 422
    assert "unsupported" in str(error.value.detail).lower()


async def _async(value):
    return value
