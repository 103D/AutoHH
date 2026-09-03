"""Tests for ResumeProfileService CRUD + master-reference validation."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.schemas.resume import ResumeProfileCreate, ResumeProfileUpdate
from app.services.resume_profile import ResumeProfileService


def async_return(value=None):
    """Async stub: awaitable that always returns ``value``."""

    async def _call(*_args, **_kwargs):
        return value

    return _call


def make_master():
    return SimpleNamespace(
        id=uuid4(),
        skills=["PostgreSQL", "Python", "Power BI"],
        experience=[
            {"id": "exp_1", "company": "RetailCo", "title": "Analyst"},
            {"id": "exp_2", "company": "DataCo", "title": "Data Analyst"},
        ],
        projects=[{"id": "proj_1", "name": "Dashboards"}],
    )


def make_existing():
    return SimpleNamespace(
        id=uuid4(),
        candidate_profile_id=uuid4(),
        specialization="BI_ANALYST",
        profile_name="BI",
        selected_skills=["PostgreSQL"],
        selected_experience_ids=["exp_1"],
        selected_project_ids=[],
        specialization_keywords=[],
        headline=None,
        summary=None,
        generated_content=None,
        is_active=True,
    )


@pytest.fixture
def service():
    repo = SimpleNamespace(
        get=None,
        get_by_specialization=None,
        create=None,
        update=None,
        delete=None,
    )
    candidate_repo = SimpleNamespace(get=None)
    return ResumeProfileService(repo, candidate_repo), repo, candidate_repo


@pytest.mark.asyncio
async def test_create_success_maps_skill_aliases(service):
    svc, repo, candidate_repo = service
    candidate_repo.get = async_return(make_master())
    repo.get_by_specialization = async_return(None)
    repo.create = lambda data: async_return(SimpleNamespace(id=uuid4(), **data))()

    created = await svc.create_profile(
        uuid4(),
        ResumeProfileCreate(
            specialization="BI_ANALYST",
            profile_name="BI Analyst",
            selected_skills=["postgres"],  # alias of master "PostgreSQL"
            selected_experience_ids=["exp_1"],
            selected_project_ids=["proj_1"],
        ),
    )
    assert created.specialization == "BI_ANALYST"


@pytest.mark.asyncio
async def test_create_rejects_unknown_skill(service):
    svc, _, candidate_repo = service
    candidate_repo.get = async_return(make_master())

    with pytest.raises(ValidationError, match="selected_skills"):
        await svc.create_profile(
            uuid4(),
            ResumeProfileCreate(
                specialization="BI_ANALYST",
                profile_name="BI",
                selected_skills=["Tableau"],  # not in master skills
            ),
        )


@pytest.mark.asyncio
async def test_create_rejects_unknown_experience_id(service):
    svc, _, candidate_repo = service
    candidate_repo.get = async_return(make_master())

    with pytest.raises(ValidationError, match="selected_experience_ids"):
        await svc.create_profile(
            uuid4(),
            ResumeProfileCreate(
                specialization="DATA_ANALYST",
                profile_name="DA",
                selected_experience_ids=["exp_404"],
            ),
        )


@pytest.mark.asyncio
async def test_create_rejects_unknown_project_id(service):
    svc, _, candidate_repo = service
    candidate_repo.get = async_return(make_master())

    with pytest.raises(ValidationError, match="selected_project_ids"):
        await svc.create_profile(
            uuid4(),
            ResumeProfileCreate(
                specialization="DATA_ANALYST",
                profile_name="DA",
                selected_project_ids=["proj_404"],
            ),
        )


@pytest.mark.asyncio
async def test_create_rejects_duplicate_specialization(service):
    svc, repo, candidate_repo = service
    candidate_repo.get = async_return(make_master())
    repo.get_by_specialization = async_return(SimpleNamespace(id=uuid4()))

    with pytest.raises(DuplicateError):
        await svc.create_profile(
            uuid4(),
            ResumeProfileCreate(specialization="BI_ANALYST", profile_name="BI"),
        )


@pytest.mark.asyncio
async def test_create_requires_master_profile(service):
    svc, _, candidate_repo = service
    candidate_repo.get = async_return(None)

    with pytest.raises(NotFoundError):
        await svc.create_profile(
            uuid4(),
            ResumeProfileCreate(specialization="BI_ANALYST", profile_name="BI"),
        )


@pytest.mark.asyncio
async def test_update_validates_merged_references(service):
    svc, repo, candidate_repo = service
    existing = make_existing()
    candidate_repo.get = async_return(make_master())
    repo.get = async_return(existing)
    repo.update = lambda profile, data: async_return(
        SimpleNamespace(**{**vars(profile), **data})
    )()

    updated = await svc.update_profile(
        existing.id, ResumeProfileUpdate(selected_skills=["python"])
    )
    assert "python" in updated.selected_skills


@pytest.mark.asyncio
async def test_update_rejects_unknown_merged_reference(service):
    svc, repo, candidate_repo = service
    existing = make_existing()
    candidate_repo.get = async_return(make_master())
    repo.get = async_return(existing)

    with pytest.raises(ValidationError, match="selected_project_ids"):
        await svc.update_profile(
            existing.id, ResumeProfileUpdate(selected_project_ids=["proj_404"])
        )


@pytest.mark.asyncio
async def test_get_profile_404(service):
    svc, repo, _ = service
    repo.get = async_return(None)
    with pytest.raises(NotFoundError):
        await svc.get_profile(uuid4())
