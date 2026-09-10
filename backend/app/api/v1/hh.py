"""HH account endpoints (ADR-001 milestones 1-2): connect/callback/status/
disconnect. All queries are scoped by the current user; responses never
contain token material."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db
from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.integrations.hh.accounts import HHAccountService
from app.integrations.hh.apply import HHApplyService
from app.integrations.hh.exceptions import (
    HHAuthRequiredError,
    HHCryptoError,
    HHOAuthError,
    HHParseError,
    HHPermissionError,
    HHStateError,
    HHTransientError,
)
from app.integrations.hh.linking import HHLinkService
from app.schemas.hh import (
    HHAccountStatusResponse,
    HHApplyRequest,
    HHApplyResponse,
    HHCallbackResponse,
    HHConnectStartResponse,
    HHLinkResponse,
    HHResumeLinkRequest,
    HHResumeLinkResponse,
    HHSyncCounts,
    HHSyncResponse,
)

router = APIRouter(prefix="/hh", tags=["hh-account"])


@router.post("/oauth/start", response_model=HHConnectStartResponse)
async def start_oauth_connect(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> HHConnectStartResponse:
    """Begin the OAuth connect flow; the user opens the returned URL."""
    service = HHAccountService(session)
    try:
        authorize_url = await service.build_authorization_url(user_id)
    except HHOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return HHConnectStartResponse(authorize_url=authorize_url)


@router.get("/oauth/callback", response_model=HHCallbackResponse)
async def oauth_callback(
    code: str,
    state: str,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> HHCallbackResponse:
    """OAuth redirect target: verify state, exchange code, verify /me, store."""
    service = HHAccountService(session)
    try:
        await service.handle_callback(code, state)
    except HHStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except HHCryptoError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except HHOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    account_status = await service.get_status(user_id)
    return HHCallbackResponse(**(account_status or {"connected": False}))


@router.get("/status", response_model=HHAccountStatusResponse)
async def get_connection_status(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> HHAccountStatusResponse:
    """Current HH connection status (no credential material)."""
    account_status = await HHAccountService(session).get_status(user_id)
    return HHAccountStatusResponse(**(account_status or {"connected": False}))


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_account(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Revoke and remove the stored HH connection."""
    await HHAccountService(session).disconnect(user_id)


@router.post("/sync", response_model=HHSyncResponse)
async def sync_remote_data(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> HHSyncResponse:
    """Explicit read-only sync of remote resumes and active negotiations."""
    service = HHAccountService(session)
    try:
        results = await service.sync_all(user_id)
    except HHAuthRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except HHTransientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except HHParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return HHSyncResponse(
        resumes=HHSyncCounts(**results["resumes"].as_dict()),
        negotiations=HHSyncCounts(**results["negotiations"].as_dict()),
    )


@router.post("/link", response_model=HHLinkResponse)
async def link_remote_negotiations(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> HHLinkResponse:
    """Link synced HH negotiations to proven local Job/Application records.

    Uses only exact HH vacancy ids and owner-scoped applications. It never
    creates an application or maps the remote negotiation state to a local
    application status.
    """
    try:
        result = await HHLinkService(session).link_negotiations(user_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return HHLinkResponse(**result.as_dict())


@router.put(
    "/resumes/{remote_resume_id}/link",
    response_model=HHResumeLinkResponse,
)
async def link_remote_resume(
    remote_resume_id: str,
    data: HHResumeLinkRequest,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> HHResumeLinkResponse:
    """Explicitly attach a synced HH resume to an owned ResumeProfile."""
    try:
        changed = await HHLinkService(session).link_resume_profile(
            user_id, remote_resume_id, data.resume_profile_id
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    return HHResumeLinkResponse(
        remote_resume_id=remote_resume_id,
        resume_profile_id=data.resume_profile_id,
        linked=changed,
    )


@router.post("/apply", response_model=HHApplyResponse)
async def apply_to_vacancy(
    data: HHApplyRequest,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> HHApplyResponse:
    """Explicit apply: one synced resume against one remote vacancy.

    Guarded by the durable (account, resume, vacancy) triple: a repeated call
    never issues a second remote POST. Never creates or mutates the local
    Application workflow.
    """
    service = HHApplyService(session)
    try:
        result = await service.apply(
            user_id, data.remote_resume_id, data.remote_vacancy_id, data.message
        )
    except HHAuthRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except DuplicateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except HHPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except HHTransientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return HHApplyResponse(
        applied=result.applied,
        duplicate=result.duplicate,
        remote_negotiation_id=result.remote_negotiation_id,
    )
