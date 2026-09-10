"""HH account API schemas (ADR-001).

None of these models ever expose tokens — only status, identifiers and
timestamps. Tokens stay encrypted at rest and server-side only.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class HHConnectStartResponse(BaseModel):
    """The URL the user must open to authorize the app on hh.ru."""

    authorize_url: str


class HHAccountStatusResponse(BaseModel):
    """Connection status without any credential material."""

    connected: bool = False
    status: str | None = None
    hh_user_id: str | None = None
    host: str | None = None
    token_expires_at: datetime | None = None
    last_verified_at: datetime | None = None
    last_sync_at: datetime | None = None


class HHCallbackResponse(HHAccountStatusResponse):
    """Result of the OAuth callback (same shape as status, connected)."""


class HHSyncCounts(BaseModel):
    """Counters of one read-only sync run."""

    fetched: int = 0
    upserted: int = 0
    skipped: int = 0


class HHSyncResponse(BaseModel):
    """Result of a manual resume + negotiation sync."""

    resumes: HHSyncCounts = HHSyncCounts()
    negotiations: HHSyncCounts = HHSyncCounts()


class HHLinkResponse(BaseModel):
    """Counts from deterministic HH negotiation-to-local linking."""

    scanned: int = 0
    jobs_linked: int = 0
    applications_linked: int = 0


class HHApplyRequest(BaseModel):
    """One explicit apply: a synced resume against one remote vacancy."""

    remote_resume_id: str
    remote_vacancy_id: str
    message: str | None = None


class HHApplyResponse(BaseModel):
    applied: bool
    duplicate: bool = False
    remote_negotiation_id: str | None = None


class HHResumeLinkRequest(BaseModel):
    """Explicit mapping from one synced HH resume to a local ResumeProfile."""

    resume_profile_id: UUID


class HHResumeLinkResponse(BaseModel):
    remote_resume_id: str
    resume_profile_id: UUID
    linked: bool
