"""
app/security/secrets/factory.py — Single construction point for SecretStore.
[ADDITIVE] Phase 10.
"""
from __future__ import annotations
import logging
from app.security.secrets.base import SecretStore
from app.security.secrets.exceptions import SecretStoreConfigurationError

logger = logging.getLogger(__name__)

_KNOWN_PROVIDERS = frozenset({"environment", "memory"})


def create_secret_store(
    provider: str,
    raw_key: str | None = None,
    key_id: str = "dev-key-1",
    encryption_version: str = "v1",
) -> SecretStore:
    """
    Construct the appropriate SecretStore implementation.

    Args:
        provider:           "environment" or "memory".
        raw_key:            Base64url-encoded 32-byte key (required for "environment").
        key_id:             Key identifier for the payload (DR-S3).
        encryption_version: Payload version tag (currently "v1").

    Raises:
        SecretStoreConfigurationError: Unknown provider or missing key.

    The "memory" provider must never be selected via an accidental typo in
    production — it requires an explicit NEXORA_SECRET_STORE_PROVIDER=memory
    environment variable, and is documented as test-only.
    """
    p = provider.strip().lower()
    if p not in _KNOWN_PROVIDERS:
        raise SecretStoreConfigurationError(
            f"Unknown secret store provider {provider!r}. "
            f"Supported: {sorted(_KNOWN_PROVIDERS)}.",
            safe_detail=f"unknown_provider:{provider}",
        )

    if p == "memory":
        from app.security.secrets.in_memory import InMemorySecretStore
        logger.warning(
            "SecretStore: using in-memory provider (test-only — not for production)."
        )
        return InMemorySecretStore()

    if p == "environment":
        from app.security.secrets.environment_key import EnvironmentKeySecretStore
        store = EnvironmentKeySecretStore.from_env(raw_key=raw_key, key_id=key_id)
        logger.info(
            "SecretStore: environment provider initialized. key_id=%r version=%s",
            key_id, encryption_version,
        )
        return store

    # Should never reach here given the set check above, but be explicit:
    raise SecretStoreConfigurationError(
        f"Provider {provider!r} is not implemented.",
        safe_detail=f"unimplemented_provider:{provider}",
    )
