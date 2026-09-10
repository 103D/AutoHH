"""HH integration exceptions (ADR-001 error semantics).

Error mapping contract:
- timeout/429/5xx  -> :class:`HHTransientError` (transient, bounded retries done)
- invalid/expired access token after a single refresh-retry
                   -> :class:`HHAuthRequiredError`
- invalid refresh token / revoked grant -> account moves to REAUTH_REQUIRED
- 403 permission/business-rule errors   -> :class:`HHPermissionError` (permanent)
- malformed remote payload              -> :class:`HHParseError` (skip item)
"""

from app.core.exceptions import JobHunterException


class HHIntegrationError(JobHunterException):
    """Base exception for the HH applicant integration bounded context."""


class HHCryptoError(HHIntegrationError):
    """Credential encryption primitive is missing or misconfigured."""


class HHOAuthError(HHIntegrationError):
    """OAuth endpoint refused the request (exchange/refresh/revoke).

    ``requires_reauth=True`` means the grant itself is gone (invalid_grant,
    revoked token): the user must re-run the connect flow. It does NOT mean
    the account should be retried in the background (ADR-001).
    """

    def __init__(self, message: str, *, requires_reauth: bool = False):
        super().__init__(message)
        self.requires_reauth = requires_reauth


class HHStateError(HHIntegrationError):
    """OAuth state is invalid, expired, already used or bound to another user."""


class HHTransientError(HHIntegrationError):
    """Remote HH API was unavailable (timeout/429/5xx) after bounded retries."""


class HHPermissionError(HHIntegrationError):
    """HH API returned 403: permanent business/permission error, not retryable."""


class HHAuthRequiredError(HHIntegrationError):
    """No usable token: account missing, disconnected or REAUTH_REQUIRED."""


class HHApiError(HHIntegrationError):
    """HH API returned an unexpected client-error response (e.g. 400)."""


class HHAlreadyAppliedError(HHIntegrationError):
    """Remote reports the (resume, vacancy) pair already has a negotiation.

    Idempotent success per ADR-001 m5: the caller should resolve the existing
    remote negotiation instead of treating this as a failure.
    """


class HHParseError(HHIntegrationError):
    """Remote payload could not be parsed as the expected JSON shape."""
