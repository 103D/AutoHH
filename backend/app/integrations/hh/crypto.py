"""Encrypted-at-rest credential primitive (ADR-001 security rules).

Tokens are stored Fernet-encrypted in ``hh_accounts`` with a dedicated key
(``HH_CREDENTIALS_KEY``) that MUST be distinct from ``SECRET_KEY``. The
primitive fails closed: without a valid key nothing is encrypted or decrypted,
so plaintext tokens can never silently appear in the database.

Generate a key once per environment::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.logging import get_logger

from .exceptions import HHCryptoError

logger = get_logger(__name__)

_KEY_GENERATION_HINT = (
    "Set HH_CREDENTIALS_KEY to a Fernet key (distinct from SECRET_KEY): "
    'python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"'
)


class CredentialCipher:
    """Fernet-based symmetric cipher for OAuth tokens at rest."""

    def __init__(self, key: str | None):
        if not key:
            raise HHCryptoError(_KEY_GENERATION_HINT)
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise HHCryptoError(f"HH_CREDENTIALS_KEY is not a valid Fernet key: {exc}") from exc

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a token; empty input is rejected to avoid sentinel values."""
        if not plaintext:
            raise HHCryptoError("Refusing to encrypt an empty credential")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a token; tampered/foreign-key ciphertext fails closed."""
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise HHCryptoError(
                "Credential decryption failed: wrong HH_CREDENTIALS_KEY or corrupted data"
            ) from exc


def get_cipher() -> CredentialCipher:
    """Build a cipher from the current settings (called per operation)."""
    return CredentialCipher(settings.hh_credentials_key)
