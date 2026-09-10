"""HH account connection lifecycle (ADR-001): connect, callback, status,
disconnect, token refresh under a per-account lock.

Security rules implemented here:
- OAuth state: signed, expiring, bound to the local user, one-time (state.py);
- credentials: Fernet-encrypted with a dedicated key, never logged or
  returned to the API layer;
- refresh: single-flight per account (double-checked inside the lock); a
  dead grant moves the account to REAUTH_REQUIRED instead of retrying;
- /me verification: the callback only persists credentials that /me accepts.
"""

import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.hh.client import HHApplicantClient
from app.integrations.hh.crypto import CredentialCipher, get_cipher
from app.integrations.hh.exceptions import (
    HHAuthRequiredError,
    HHCryptoError,
    HHOAuthError,
    HHStateError,
)
from app.integrations.hh.locks import HHLockBackend, get_hh_lock_backend
from app.integrations.hh.negotiations import HHNegotiationSync
from app.integrations.hh.oauth import HHOAuthClient, generate_pkce_pair
from app.integrations.hh.resumes import HHResumeSync
from app.integrations.hh.state import OAuthStateSigner, StateStore, get_state_store
from app.integrations.hh.sync_base import SyncResult
from app.models.hh import HHAccount, HHAccountStatus
from app.repositories.hh import HHAccountRepository

logger = get_logger(__name__)

# Refresh when the access token is about to expire within this window.
TOKEN_EXPIRY_LEEWAY_SECONDS = 60


def _token_is_fresh(expires_at: datetime | None) -> bool:
    """True when the token is valid beyond the refresh leeway window."""
    return expires_at is not None and expires_at - datetime.now(UTC) > timedelta(
        seconds=TOKEN_EXPIRY_LEEWAY_SECONDS
    )


class HHAccountService:
    """Connection lifecycle for a user's HH applicant account."""

    # Per-account refresh locks (single process). Multi-worker deployments
    # replace this with a Redis lock in milestone 6 (ADR-001).
    _account_locks: dict[UUID, asyncio.Lock] = {}

    def __init__(
        self,
        session: AsyncSession,
        *,
        oauth_client: HHOAuthClient | None = None,
        cipher: CredentialCipher | None = None,
        lock_backend: HHLockBackend | None = None,
        state_store: StateStore | None = None,
    ):
        self.repo = HHAccountRepository(session)
        self.oauth = oauth_client or HHOAuthClient()
        self._cipher = cipher
        self.lock_backend = lock_backend or get_hh_lock_backend()
        self.state_store: StateStore = state_store or get_state_store()
        self._signer = OAuthStateSigner()

    @property
    def cipher(self) -> CredentialCipher:
        """Resolve lazily: read-only flows (status) work without a key."""
        if self._cipher is None:
            self._cipher = get_cipher()
        return self._cipher

    # -- connect flow ------------------------------------------------------

    async def build_authorization_url(self, user_id: UUID) -> str:
        """Start the OAuth flow: issue state + optional PKCE pair."""
        state = self._signer.issue(user_id)
        code_verifier: str | None = None
        code_challenge: str | None = None
        if settings.hh_oauth_use_pkce:
            code_verifier, code_challenge = generate_pkce_pair()
        await self.state_store.put(
            self._nonce_of(state),
            json.dumps({"user_id": str(user_id), "code_verifier": code_verifier}),
            self._signer.ttl_seconds,
        )
        url = self.oauth.build_authorization_url(state=state, code_challenge=code_challenge)
        logger.info("Started HH OAuth connect for local user %s", user_id)
        return url

    async def handle_callback(self, code: str, state: str) -> HHAccount:
        """Complete the OAuth flow: verify state, exchange code, verify /me."""
        payload = self._signer.verify(state)
        user_id = UUID(payload["user_id"])

        stored = await self.state_store.pop(self._nonce_of(state))
        if stored is None:
            raise HHStateError("OAuth state is expired or already used")
        record = json.loads(stored)
        if record.get("user_id") != str(user_id):
            raise HHStateError("OAuth state is bound to a different user")

        tokens = await self.oauth.exchange_code(
            code, code_verifier=record.get("code_verifier")
        )

        me = await self._verify_identity(tokens.access_token)
        hh_user_id = str(me["id"])

        now = datetime.now(UTC)
        account = await self.repo.upsert_connected(
            {
                "user_id": user_id,
                "hh_user_id": hh_user_id,
                "host": "hh.ru",
                "status": HHAccountStatus.CONNECTED,
                "access_token_encrypted": self.cipher.encrypt(tokens.access_token),
                "refresh_token_encrypted": self.cipher.encrypt(tokens.refresh_token),
                "access_token_expires_at": now + timedelta(seconds=tokens.expires_in),
                "scopes": [],
                "last_verified_at": now,
            }
        )
        logger.info("HH account connected: local_user=%s hh_user=%s", user_id, hh_user_id)
        return account

    async def _verify_identity(self, access_token: str) -> dict:
        """``/me`` check: the token must identify an applicant before storage."""
        client = HHApplicantClient(
            lambda _force_refresh=False: _identity_token(access_token), timeout=15.0
        )
        me = await client.get_current_user()
        if not isinstance(me, dict) or "id" not in me:
            raise HHOAuthError("Malformed /me response during verification")
        return me

    # -- status / disconnect -----------------------------------------------

    async def get_status(self, user_id: UUID) -> dict | None:
        """Connection status for the user; never includes tokens."""
        account = await self.repo.get_by_user(user_id)
        if account is None:
            return None
        return {
            "connected": account.status == HHAccountStatus.CONNECTED,
            "status": account.status,
            "hh_user_id": account.hh_user_id,
            "host": account.host,
            "token_expires_at": account.access_token_expires_at,
            "last_verified_at": account.last_verified_at,
            "last_sync_at": account.last_sync_at,
        }

    async def disconnect(self, user_id: UUID) -> None:
        """Revoke remotely (best effort) and remove the local connection."""
        account = await self.repo.get_by_user(user_id)
        if account is None:
            return
        try:
            await self.oauth.revoke_token(
                self.cipher.decrypt(account.access_token_encrypted)
            )
        except HHCryptoError:
            logger.error("Disconnect: cannot decrypt stored token to revoke")
        except HHOAuthError as exc:
            logger.warning("Disconnect: revoke not confirmed (%s), removing locally", exc)
        await self.repo.delete(account)
        logger.info("HH account disconnected for local user %s", user_id)

    # -- token management -----------------------------------------------------

    async def get_valid_access_token(
        self, user_id: UUID, *, force_refresh: bool = False
    ) -> str:
        """Return a usable access token, refreshing once if needed.

        ``force_refresh=True`` skips the freshness checks (used by the
        applicant client after a 401 to obtain a guaranteed-new token).
        """
        account = await self.repo.get_by_user(user_id)
        if account is None or account.status != HHAccountStatus.CONNECTED:
            raise HHAuthRequiredError("HH account is not connected")

        if not force_refresh and _token_is_fresh(account.access_token_expires_at):
            return self.cipher.decrypt(account.access_token_encrypted)

        lock = self._account_locks.setdefault(account.id, asyncio.Lock())
        async with lock:
            # Double-check: another coroutine may have refreshed while we waited.
            await self.repo.session.refresh(account)
            if account.status != HHAccountStatus.CONNECTED:
                raise HHAuthRequiredError("HH account requires re-authorization")
            if not force_refresh and _token_is_fresh(account.access_token_expires_at):
                return self.cipher.decrypt(account.access_token_encrypted)

            distributed_key = f"hh-account-refresh:{account.id}"
            lock_owner = secrets.token_urlsafe(16)
            acquired = await self.lock_backend.acquire(
                distributed_key,
                lock_owner,
                settings.hh_refresh_lock_ttl_seconds,
            )
            if not acquired:
                metrics.inc_hh_token_refresh("lock_timeout")
                raise HHAuthRequiredError("HH account refresh is already in progress")

            try:
                # Double-check again after the distributed lock: another worker
                # may have refreshed and committed while we waited locally.
                await self.repo.session.refresh(account)
                if account.status != HHAccountStatus.CONNECTED:
                    raise HHAuthRequiredError("HH account requires re-authorization")
                if not force_refresh and _token_is_fresh(account.access_token_expires_at):
                    return self.cipher.decrypt(account.access_token_encrypted)

                try:
                    tokens = await self.oauth.refresh_tokens(
                        self.cipher.decrypt(account.refresh_token_encrypted)
                    )
                except HHOAuthError as exc:
                    if exc.requires_reauth:
                        await self.repo.mark_status(account, HHAccountStatus.REAUTH_REQUIRED)
                        metrics.inc_hh_token_refresh("reauth_required")
                        logger.warning("HH grant is dead; account moved to REAUTH_REQUIRED")
                        raise HHAuthRequiredError(
                            "HH account requires re-authorization"
                        ) from exc
                    metrics.inc_hh_token_refresh("error")
                    raise

                now = datetime.now(UTC)
                account.access_token_encrypted = self.cipher.encrypt(tokens.access_token)
                account.refresh_token_encrypted = self.cipher.encrypt(tokens.refresh_token)
                account.access_token_expires_at = now + timedelta(seconds=tokens.expires_in)
                account.last_verified_at = now
                await self.repo.session.flush()
                metrics.inc_hh_token_refresh("success")
                logger.info("HH access token refreshed for account %s", account.id)
                return tokens.access_token
            finally:
                await self.lock_backend.release(distributed_key, lock_owner)

    def applicant_client_for(self, user_id: UUID) -> HHApplicantClient:
        """Client bound to the user's auto-refreshing token provider."""
        return HHApplicantClient(
            lambda force_refresh=False: self._token_for(user_id, force_refresh)
        )

    async def _token_for(self, user_id: UUID, force_refresh: bool) -> str:
        if not force_refresh:
            account = await self.repo.get_by_user(user_id)
            if account is not None and account.status == HHAccountStatus.CONNECTED:
                if _token_is_fresh(account.access_token_expires_at):
                    return self.cipher.decrypt(account.access_token_encrypted)
        return await self.get_valid_access_token(user_id, force_refresh=force_refresh)

    # -- read-only sync (ADR-001 milestone 3) ---------------------------------

    def _connected_account(self, account: HHAccount | None) -> HHAccount:
        if account is None or account.status != HHAccountStatus.CONNECTED:
            raise HHAuthRequiredError("HH account is not connected")
        return account

    async def sync_resumes(self, user_id: UUID) -> SyncResult:
        """Sync remote resumes for the user's connected account."""
        account = self._connected_account(await self.repo.get_by_user(user_id))
        sync = HHResumeSync(self.repo.session, account, self.applicant_client_for(user_id))
        result = await sync.run()
        await self.repo.mark_synced(account)
        return result

    async def sync_negotiations(self, user_id: UUID) -> SyncResult:
        """Sync remote active negotiations for the user's connected account."""
        account = self._connected_account(await self.repo.get_by_user(user_id))
        sync = HHNegotiationSync(
            self.repo.session, account, self.applicant_client_for(user_id)
        )
        result = await sync.run()
        await self.repo.mark_synced(account)
        return result

    async def sync_all(self, user_id: UUID) -> dict[str, SyncResult]:
        """Run both read-only syncs; each updates last_sync_at on success."""
        return {
            "resumes": await self.sync_resumes(user_id),
            "negotiations": await self.sync_negotiations(user_id),
        }

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _nonce_of(state: str) -> str:
        # The nonce is embedded in the signed payload; reuse it as the store key.
        import base64

        raw = base64.urlsafe_b64decode(state.split(".", 1)[0].encode())
        return json.loads(raw)["nonce"]


async def _identity_token(access_token: str) -> str:
    """Static provider for the one-shot /me verification client."""
    return access_token
