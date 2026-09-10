"""Integration tests for deterministic HH remote-to-local linking (ADR-001 m4)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.integrations.hh.linking import HHLinkService
from app.models.application import Application
from app.models.candidate import CandidateProfile, ResumeProfile
from app.models.hh import HHAccount, HHNegotiation, HHResume
from app.models.job import Job, JobSource


async def _account(session, user_id):
    account = HHAccount(
        user_id=user_id,
        hh_user_id=f"hh-{uuid4().hex[:10]}",
        host="hh.ru",
        status="CONNECTED",
        access_token_encrypted="ciphertext-access",
        refresh_token_encrypted="ciphertext-refresh",
        scopes=[],
    )
    session.add(account)
    await session.flush()
    return account


async def _candidate(session, user_id):
    candidate = CandidateProfile(
        user_id=user_id,
        desired_positions=["Data Analyst"],
        skills=["SQL"],
        technologies={},
        languages={},
        salary_currency="KZT",
        resume_versions={},
    )
    session.add(candidate)
    await session.flush()
    return candidate


async def _job(session, *, source_type="hh_kz", external_id="vac-1"):
    source = JobSource(
        name=f"source-{source_type}-{uuid4().hex[:8]}",
        type=source_type,
        enabled=True,
        configuration={},
    )
    session.add(source)
    await session.flush()
    now = datetime.now(UTC)
    job = Job(
        source_id=source.id,
        source_type=source_type,
        external_id=external_id,
        title="Data Analyst",
        company="Company",
        description="SQL analytics",
        url=f"https://example.com/{uuid4().hex}",
        content_hash=uuid4().hex,
        url_normalized=f"https://example.com/{uuid4().hex}",
        raw_data={},
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(job)
    await session.flush()
    return job


async def _negotiation(session, account, *, remote_vacancy_id="vac-1"):
    row = HHNegotiation(
        hh_account_id=account.id,
        remote_negotiation_id=f"neg-{uuid4().hex[:10]}",
        remote_resume_id="resume-1",
        remote_vacancy_id=remote_vacancy_id,
        state_id="active",
        state_name="Active",
        messages_metadata={},
        raw_data={"id": "remote"},
        content_hash=uuid4().hex,
    )
    session.add(row)
    await session.flush()
    return row


async def _resume(session, account, remote_resume_id="resume-1"):
    row = HHResume(
        hh_account_id=account.id,
        remote_resume_id=remote_resume_id,
        title="Analyst CV",
        raw_data={"id": remote_resume_id},
        content_hash=uuid4().hex,
    )
    session.add(row)
    await session.flush()
    return row


async def _resume_profile(session, candidate):
    profile = ResumeProfile(
        candidate_profile_id=candidate.id,
        specialization="DATA_ANALYST",
        profile_name="Data analyst CV",
        selected_skills=[],
        selected_experience_ids=[],
        selected_project_ids=[],
        specialization_keywords=[],
    )
    session.add(profile)
    await session.flush()
    return profile


async def test_links_exact_hh_job_and_owned_application_idempotently(db_session, cleanup_db):
    user_id = uuid4()
    account = await _account(db_session, user_id)
    candidate = await _candidate(db_session, user_id)
    job = await _job(db_session, external_id="vac-1")
    application = Application(
        job_id=job.id,
        candidate_profile_id=candidate.id,
        status="PREPARED",
    )
    db_session.add(application)
    negotiation = await _negotiation(db_session, account, remote_vacancy_id="vac-1")
    await db_session.commit()

    service = HHLinkService(db_session)
    first = await service.link_negotiations(user_id)
    await db_session.commit()

    assert first.as_dict() == {
        "scanned": 1,
        "jobs_linked": 1,
        "applications_linked": 1,
    }
    await db_session.refresh(negotiation)
    await db_session.refresh(application)
    assert negotiation.job_id == job.id
    assert negotiation.application_id == application.id
    assert application.status == "PREPARED"  # remote state never changes local workflow

    second = await service.link_negotiations(user_id)
    assert second.as_dict() == {
        "scanned": 1,
        "jobs_linked": 0,
        "applications_linked": 0,
    }


async def test_does_not_link_non_hh_or_ambiguous_vacancy_id(db_session, cleanup_db):
    user_id = uuid4()
    account = await _account(db_session, user_id)
    non_hh = await _job(db_session, source_type="manual", external_id="shared")
    only_manual = await _negotiation(db_session, account, remote_vacancy_id="shared")

    # Even across HH sources, duplicate remote vacancy ids are ambiguous.
    await _job(db_session, source_type="hh_kz", external_id="ambiguous")
    await _job(db_session, source_type="hh_remote", external_id="ambiguous")
    ambiguous = await _negotiation(db_session, account, remote_vacancy_id="ambiguous")
    await db_session.commit()

    result = await HHLinkService(db_session).link_negotiations(user_id)
    await db_session.commit()
    assert result.as_dict() == {
        "scanned": 2,
        "jobs_linked": 0,
        "applications_linked": 0,
    }
    await db_session.refresh(only_manual)
    await db_session.refresh(ambiguous)
    assert only_manual.job_id is None
    assert ambiguous.job_id is None
    assert non_hh.id is not None


async def test_links_job_but_never_foreign_users_application(db_session, cleanup_db):
    owner_id = uuid4()
    foreign_user_id = uuid4()
    account = await _account(db_session, owner_id)
    foreign_candidate = await _candidate(db_session, foreign_user_id)
    job = await _job(db_session, external_id="vac-owner")
    foreign_application = Application(
        job_id=job.id,
        candidate_profile_id=foreign_candidate.id,
        status="DRAFT",
    )
    db_session.add(foreign_application)
    negotiation = await _negotiation(db_session, account, remote_vacancy_id="vac-owner")
    await db_session.commit()

    result = await HHLinkService(db_session).link_negotiations(owner_id)
    await db_session.commit()
    await db_session.refresh(negotiation)
    assert result.as_dict() == {
        "scanned": 1,
        "jobs_linked": 1,
        "applications_linked": 0,
    }
    assert negotiation.job_id == job.id
    assert negotiation.application_id is None


async def test_explicit_resume_profile_link_enforces_owner_and_is_idempotent(
    db_session, cleanup_db
):
    owner_id = uuid4()
    foreign_user_id = uuid4()
    account = await _account(db_session, owner_id)
    owner_candidate = await _candidate(db_session, owner_id)
    foreign_candidate = await _candidate(db_session, foreign_user_id)
    remote_resume = await _resume(db_session, account)
    owner_profile = await _resume_profile(db_session, owner_candidate)
    foreign_profile = await _resume_profile(db_session, foreign_candidate)
    await db_session.commit()

    service = HHLinkService(db_session)
    assert await service.link_resume_profile(owner_id, "resume-1", owner_profile.id) is True
    assert await service.link_resume_profile(owner_id, "resume-1", owner_profile.id) is False
    await db_session.commit()
    await db_session.refresh(remote_resume)
    assert remote_resume.resume_profile_id == owner_profile.id

    with pytest.raises(ValidationError, match="does not belong"):
        await service.link_resume_profile(owner_id, "resume-1", foreign_profile.id)
    await db_session.refresh(remote_resume)
    assert remote_resume.resume_profile_id == owner_profile.id


async def test_linker_preserves_existing_authoritative_links(db_session, cleanup_db):
    user_id = uuid4()
    account = await _account(db_session, user_id)
    candidate = await _candidate(db_session, user_id)
    linked_job = await _job(db_session, external_id="already-linked")
    linked_application = Application(
        job_id=linked_job.id,
        candidate_profile_id=candidate.id,
        status="SAVED",
    )
    db_session.add(linked_application)
    other_job = await _job(db_session, external_id="remote-now-different")
    negotiation = await _negotiation(
        db_session, account, remote_vacancy_id="remote-now-different"
    )
    negotiation.job_id = linked_job.id
    negotiation.application_id = linked_application.id
    await db_session.commit()

    result = await HHLinkService(db_session).link_negotiations(user_id)
    await db_session.commit()
    await db_session.refresh(negotiation)
    assert result.as_dict() == {
        "scanned": 1,
        "jobs_linked": 0,
        "applications_linked": 0,
    }
    assert negotiation.job_id == linked_job.id
    assert negotiation.application_id == linked_application.id
    assert other_job.id != linked_job.id
