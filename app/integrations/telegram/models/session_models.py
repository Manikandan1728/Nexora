"""
app/integrations/telegram/models/session_models.py

[ADDITIVE] Part 2C — Session bundle models

Typed models representing the persistent and runtime states of a Telegram session.
These models ensure encrypted data and plaintext secrets do not cross boundaries.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, SecretStr


class TelegramSessionStatus(str, Enum):
    """Safe status of the session, exposed in API responses."""
    ABSENT = "absent"
    AVAILABLE = "available"
    UNREADABLE = "unreadable"
    PARTIAL = "partial"
    REVOKED = "revoked"


class TelegramSessionValidationResult(BaseModel):
    """Result of validating a session bundle's presence and integrity."""
    status: TelegramSessionStatus
    has_session_reference: bool
    has_database_key: bool
    has_files_database_key: bool
    error_code: Optional[str] = None


class EncryptedTelegramSessionBundle(BaseModel):
    """
    The encrypted form of a Telegram session, retrieved from or saved to persistence.
    Contains only ciphertext.
    """
    session_reference_encrypted: Optional[str] = None
    tdlib_database_key_encrypted: Optional[str] = None
    tdlib_files_database_key_encrypted: Optional[str] = None
    session_locator_encrypted: Optional[str] = None
    encryption_version: str = "v1"


class DecryptedTelegramSessionBundle(BaseModel):
    """
    The decrypted form of a Telegram session, held temporarily in memory.
    Must never be serialized in public API models or persisted.
    """
    session_reference: Optional[SecretStr] = None
    tdlib_database_key: Optional[SecretStr] = None
    tdlib_files_database_key: Optional[SecretStr] = None
    session_locator: Optional[SecretStr] = None

    def __repr__(self) -> str:
        """Custom repr to ensure no secrets are accidentally logged."""
        flags = [
            f"{k}={'<secret>' if getattr(self, k) else 'None'}"
            for k in self.model_fields.keys()
        ]
        return f"DecryptedTelegramSessionBundle({', '.join(flags)})"
