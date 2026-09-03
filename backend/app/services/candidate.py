from uuid import UUID

from app.core.exceptions import DuplicateError, NotFoundError
from app.models.candidate import CandidateProfile
from app.repositories.candidate import CandidateRepository
from app.schemas.candidate import CandidateProfileCreate, CandidateProfileUpdate


class CandidateService:
    """Service for candidate profile business logic."""

    def __init__(self, repository: CandidateRepository):
        self.repository = repository

    async def get_profile(self, profile_id: UUID) -> CandidateProfile:
        """Get candidate profile by ID."""
        profile = await self.repository.get(profile_id)
        if not profile:
            raise NotFoundError(f"Profile {profile_id} not found")
        return profile

    async def get_profile_by_user(self, user_id: UUID) -> CandidateProfile:
        """Get candidate profile by user ID."""
        profile = await self.repository.get_by_user_id(user_id)
        if not profile:
            raise NotFoundError(f"Profile for user {user_id} not found")
        return profile

    async def resolve_profile(self, profile_id: UUID | None) -> CandidateProfile:
        """Resolve a profile by id, or fall back to the default (single-user).

        Centralizes the "profile_id or default" resolution previously
        duplicated across services.
        """
        if profile_id:
            return await self.get_profile(profile_id)
        return await self.get_default_profile()

    async def get_default_profile(self) -> CandidateProfile:
        """Get the first candidate profile (assumes single user for now)."""
        profiles = await self.repository.get_multi(0, 1)
        if not profiles:
            raise NotFoundError("No candidate profile found. Please create a profile first.")
        return profiles[0]

    async def create_profile(self, profile_in: CandidateProfileCreate) -> CandidateProfile:
        """Create new candidate profile."""
        # Check if profile already exists for this user
        existing = await self.repository.get_by_user_id(profile_in.user_id)
        if existing:
            raise DuplicateError(f"Profile already exists for user {profile_in.user_id}")

        profile_data = profile_in.model_dump()
        return await self.repository.create(profile_data)

    async def update_profile(
        self,
        profile_id: UUID,
        profile_in: CandidateProfileUpdate,
    ) -> CandidateProfile:
        """Update candidate profile."""
        profile = await self.get_profile(profile_id)

        update_data = profile_in.model_dump(exclude_unset=True)
        return await self.repository.update(profile, update_data)

    async def delete_profile(self, profile_id: UUID) -> None:
        """Delete candidate profile."""
        profile = await self.get_profile(profile_id)
        await self.repository.delete(profile.id)
