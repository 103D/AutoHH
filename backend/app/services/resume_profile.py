"""Resume profile CRUD with master-profile referential validation (spec #12).

A ResumeProfile must only reference facts that exist in the master
CandidateProfile: selected skills must be master skills (alias-tolerant),
selected experience/project ids must exist in the master experience/projects
lists. The service never duplicates facts.
"""

from types import SimpleNamespace
from uuid import UUID

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.models.candidate import CandidateProfile, ResumeProfile
from app.repositories.candidate import CandidateRepository, ResumeProfileRepository
from app.schemas.resume import ResumeProfileCreate, ResumeProfileUpdate
from app.services.skill_taxonomy import normalize_skill

REF_FIELDS = ("selected_skills", "selected_experience_ids", "selected_project_ids")


class ResumeProfileService:
    """Business logic for specialized resume profiles."""

    def __init__(
        self,
        repository: ResumeProfileRepository,
        candidate_repository: CandidateRepository,
    ):
        self.repository = repository
        self.candidate_repository = candidate_repository

    async def list_profiles(self, candidate_profile_id: UUID) -> list[ResumeProfile]:
        """List resume profiles of a candidate."""
        await self._get_master(candidate_profile_id)
        return await self.repository.list_by_candidate(candidate_profile_id)

    async def get_profile(self, resume_profile_id: UUID) -> ResumeProfile:
        """Get one resume profile by id."""
        profile = await self.repository.get(resume_profile_id)
        if not profile:
            raise NotFoundError(f"Resume profile {resume_profile_id} not found")
        return profile

    async def create_profile(
        self, candidate_profile_id: UUID, data: ResumeProfileCreate
    ) -> ResumeProfile:
        """Create a resume profile after master-reference validation."""
        master = await self._get_master(candidate_profile_id)
        self._validate_references(master, data)

        duplicate = await self.repository.get_by_specialization(
            candidate_profile_id, data.specialization
        )
        if duplicate is not None:
            raise DuplicateError(
                f"Resume profile for specialization {data.specialization} already exists"
            )

        profile_data = {**data.model_dump(), "candidate_profile_id": candidate_profile_id}
        return await self.repository.create(profile_data)

    async def update_profile(
        self, resume_profile_id: UUID, data: ResumeProfileUpdate
    ) -> ResumeProfile:
        """Update a resume profile; references are validated after merging."""
        profile = await self.get_profile(resume_profile_id)
        master = await self._get_master(profile.candidate_profile_id)

        update_data = data.model_dump(exclude_unset=True)
        if any(field in update_data for field in REF_FIELDS):
            merged = {field: update_data.get(field, getattr(profile, field)) for field in REF_FIELDS}
            self._validate_references(master, SimpleNamespace(**merged))

        return await self.repository.update(profile, update_data)

    async def delete_profile(self, resume_profile_id: UUID) -> None:
        """Delete a resume profile."""
        profile = await self.get_profile(resume_profile_id)
        await self.repository.delete(profile.id)

    async def _get_master(self, candidate_profile_id: UUID) -> CandidateProfile:
        master = await self.candidate_repository.get(candidate_profile_id)
        if not master:
            raise NotFoundError(f"Profile {candidate_profile_id} not found")
        return master

    @staticmethod
    def _validate_references(master: CandidateProfile, data: object) -> None:
        """Ensure every reference points to master-profile facts."""
        master_skills = {normalize_skill(s) for s in (master.skills or []) if s}
        unknown_skills = [
            s
            for s in (getattr(data, "selected_skills", None) or [])
            if normalize_skill(s) not in master_skills
        ]
        if unknown_skills:
            raise ValidationError(
                f"selected_skills not present in master profile: {sorted(set(unknown_skills))}"
            )

        experience_ids = {e.get("id") for e in (master.experience or []) if isinstance(e, dict)}
        unknown_experience = [
            i
            for i in (getattr(data, "selected_experience_ids", None) or [])
            if i not in experience_ids
        ]
        if unknown_experience:
            raise ValidationError(
                f"selected_experience_ids not present in master experience: {sorted(set(unknown_experience))}"
            )

        project_ids = {p.get("id") for p in (master.projects or []) if isinstance(p, dict)}
        unknown_projects = [
            i
            for i in (getattr(data, "selected_project_ids", None) or [])
            if i not in project_ids
        ]
        if unknown_projects:
            raise ValidationError(
                f"selected_project_ids not present in master projects: {sorted(set(unknown_projects))}"
            )
