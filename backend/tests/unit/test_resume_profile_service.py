"""Tests for resume profile service (task spec #12)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.schemas.resume import ResumeProfileCreate, ResumeProfileUpdate
from app.services.resume_profile import ResumeProfileService


def make_master(**kwargs) -> SimpleNamespace:
    defaults: dict = {
        "id": uuid4(),
        "skills": ["PostgreSQL", "Python", "Power BI"],
        "experience": [
            {"id": "exp_1", "company": "Corp", "title": "Analyst"},
            {"id": "exp_2", "company": "Corp2", "title": "BI Analyst"},
        ],
        "projects": [{"id": "proj_1", "name": "DW"}],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class FakeResumeRepo:
    """In-memory fake repository for ResumeProfile."""

    def __init__(self):
        self.profiles: dict[uuid4().__class__, object] = {}

    async def get(self, profile_id):
        return self.profiles.get(profile_id)

    async def list_by_candidate(self, candidate_profile_id):
        return [
            p
            for p in self.profiles.values()
            if p.candidate_profile_id == candidate_profile_id
        ]

    async def get_by_specialization(self, candidate_profile_id, specialization):
        return next(
            (
                p
                for p in self.profiles.values()
                if p.candidate_profile_id == candidate_profile_id
                and p.specialization == specialization
            ),
            None,
        )

    async def create(self, data):
        profile = SimpleNamespace(
            id=uuid4(),
            candidate_profile_id=data["candidate_profile_id"],
            **{k: v for k, v in data.items() if k != "candidate_profile_id"},
        )
        self.profiles[profile.id] = profile
        return profile

    async def update(self, profile, update_data):
        for key, value in update_data.items():
            setattr(profile, key, value)
        return profile

    async def delete(self, profile_id):
        self.profiles.pop(profile_id, None)


class FakeCandidateRepo:
    def __init__(self, master):
        self.master = master

    async def get(self, profile_id):
        return self.master if profile_id == self.master.id else None


def make_service(master: SimpleNamespace) -> ResumeProfileService:
    return ResumeProfileService(FakeResumeRepo(), FakeCandidateRepo(master))


@pytest.mark.asyncio
async def test_create_valid_profile():
    master = make_master()
    service = make_service(master)
    data = ResumeProfileCreate(
        specialization="BI_ANALYST",
        profile_name="cv_bi",
        selected_skills=["PostgreSQL", "postgres"],  # alias form allowed
        selected_experience_ids=["exp_2"],
        selected_project_ids=["proj_1"],
        specialization_keywords=["power bi", "dax"],
    )

    profile = await service.create_profile(master.id, data)

    assert profile.specialization == "BI_ANALYST"
    assert profile.profile_name == "cv_bi"


@pytest.mark.asyncio
async def test_create_with_unknown_skill_rejected():
    """References must point to master-profile facts — no invented skills."""
    master = make_master()
    service = make_service(master)
    data = ResumeProfileCreate(
        specialization="BI_ANALYST",
        profile_name="cv_bi",
        selected_skills=["Tableau"],  # not in master skills
    )

    with pytest.raises(ValidationError, match="Tableau"):
        _ = await service.create_profile(master.id, data)


@pytest.mark.asyncio
async def test_create_with_unknown_experience_rejected():
    master = make_master()
    service = make_service(master)
    data = ResumeProfileCreate(
        specialization="BI_ANALYST",
        profile_name="cv_bi",
        selected_experience_ids=["exp_999"],
    )

    with pytest.raises(ValidationError, match="exp_999"):
        _ = await service.create_profile(master.id, data)


@pytest.mark.asyncio
async def test_duplicate_specialization_rejected():
    master = make_master()
    service = make_service(master)
    data = ResumeProfileCreate(specialization="BI_ANALYST", profile_name="cv_bi")

    created = await service.create_profile(master.id, data)
    with pytest.raises(DuplicateError):
        _ = await service.create_profile(master.id, data)
    assert created is not None


@pytest.mark.asyncio
async def test_missing_master_rejected():
    service = make_service(make_master())
    data = ResumeProfileCreate(specialization="BI_ANALYST", profile_name="cv_bi")

    with pytest.raises(NotFoundError):
        _ = await service.create_profile(uuid4(), data)


@pytest.mark.asyncio
async def test_update_merges_references_for_validation():
    """Existing valid references stay valid when updating another field."""
    master = make_master()
    service = make_service(master)
    created = await service.create_profile(
        master.id,
        ResumeProfileCreate(
            specialization="BI_ANALYST",
            profile_name="cv_bi",
            selected_skills=["PostgreSQL"],
        ),
    )

    updated = await service.update_profile(
        created.id, ResumeProfileUpdate(summary="BI-focused summary")
    )

    assert updated.summary == "BI-focused summary"
    assert updated.selected_skills == ["PostgreSQL"]


@pytest.mark.asyncio
async def test_update_with_invalid_reference_rejected():
    master = make_master()
    service = make_service(master)
    created = await service.create_profile(
        master.id, ResumeProfileCreate(specialization="BI_ANALYST", profile_name="cv_bi")
    )

    with pytest.raises(ValidationError):
        _ = await service.update_profile(
            created.id,
            ResumeProfileUpdate(selected_experience_ids=["exp_missing"]),
        )
