"""
app/security/secrets/base.py — SecretStore protocol and health models.

[ADDITIVE] Phase 1+2. No existing code is modified.

Source-independent protocol: callers never depend on a concrete implementation.
"""
from __future__ import annotations
from enum import Enum
from typing import Protocol, runtime_checkable
from pydantic import BaseModel


class SecretStoreStatus(str, Enum):
    HEALTHY     = "healthy"
    DEGRADED    = "degraded"
    UNAVAILABLE = "unavailable"


class SecretStoreHealth(BaseModel):
    """Safe health information — never contains plaintext, keys, or nonces."""
    status: SecretStoreStatus
    provider: str
    encryption_version: str
    key_id: str | None = None
    message: str | None = None


@runtime_checkable
class SecretStore(Protocol):
    """
    Generic secret-store protocol.

    encrypt/decrypt use optional context (Additional Authenticated Data).
    DR-S4 truth table:
      enc(no-ctx) + dec(no-ctx)    → ✅
      enc(no-ctx) + dec(ctx="x")   → ❌ integrity failure
      enc(ctx="x") + dec(no-ctx)   → ❌ integrity failure
      enc(ctx="x") + dec(ctx="x")  → ✅
      enc(ctx="x") + dec(ctx="y")  → ❌ integrity failure

    delete() semantics differ by implementation:
      EnvironmentKeySecretStore: no-op (ciphertext is inline in the DB field;
        deleting the DB field deletes the secret).
      InMemorySecretStore: removes the reference from the in-memory store.
    """

    def encrypt(self, plaintext: str, *, context: str | None = None) -> str: ...
    def decrypt(self, ciphertext: str, *, context: str | None = None) -> str: ...
    def delete(self, secret_reference: str) -> None: ...
    def health_check(self) -> SecretStoreHealth: ...
