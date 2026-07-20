"""
app/security/secrets/validation.py — Key validation utilities.
[ADDITIVE] Phase 5. DR-S2: fail-fast on missing/malformed key.
"""
from __future__ import annotations
import base64
from app.security.secrets.exceptions import SecretStoreConfigurationError

_REQUIRED_KEY_BYTES = 32  # AES-256 requires 32 bytes


def decode_and_validate_key(raw: str | None, var_name: str = "NEXORA_SECRET_ENCRYPTION_KEY") -> bytes:
    """
    Decode and validate a base64url-encoded 32-byte AES-256 key.

    Raises SecretStoreConfigurationError (DR-S2: fail-fast) for:
      - Missing/None key
      - Whitespace-only key
      - Invalid base64
      - Wrong length after decoding
    Never logs the key value.
    """
    if not raw or not raw.strip():
        raise SecretStoreConfigurationError(
            f"{var_name} is required but not set.",
            safe_detail="missing_key",
        )
    raw = raw.strip()
    try:
        key_bytes = base64.urlsafe_b64decode(raw + "==")
    except Exception:
        raise SecretStoreConfigurationError(
            f"{var_name} is not valid base64url encoding.",
            safe_detail="invalid_base64",
        )
    if len(key_bytes) != _REQUIRED_KEY_BYTES:
        raise SecretStoreConfigurationError(
            f"{var_name} must decode to exactly {_REQUIRED_KEY_BYTES} bytes "
            f"(AES-256). Got {len(key_bytes)} bytes.",
            safe_detail=f"wrong_key_length:{len(key_bytes)}",
        )
    return key_bytes
