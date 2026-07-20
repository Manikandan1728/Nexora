"""
app/security/secrets/models.py — Versioned encrypted payload format.

[ADDITIVE] Phase 6 — DR-S3 (multi-key-id via registry lookup).

Payload wire format:
  nexora:v1:<url-safe-base64(json-bytes)>

JSON fields:
  version     : "v1"
  algorithm   : "AES-256-GCM"
  key_id      : str (identifies which key to use for decryption)
  nonce       : url-safe-base64 encoded bytes (12 bytes)
  ciphertext  : url-safe-base64 encoded bytes (ciphertext + 16-byte GCM tag)

The `version` and `algorithm` fields allow future migration to new schemes.
The `key_id` enables zero-downtime key rotation (DR-S3).
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from app.security.secrets.exceptions import SecretPayloadFormatError

_PREFIX = "nexora"
_CURRENT_VERSION = "v1"
_SUPPORTED_ALGORITHMS = frozenset({"AES-256-GCM"})

@dataclass
class EncryptedPayload:
    version: str
    algorithm: str
    key_id: str
    nonce: bytes
    ciphertext: bytes  # includes GCM authentication tag

    def serialize(self) -> str:
        """Serialize to wire format: nexora:v1:<base64(json)>"""
        inner = {
            "version": self.version,
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "nonce": base64.urlsafe_b64encode(self.nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(self.ciphertext).decode("ascii"),
        }
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(inner, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        return f"{_PREFIX}:{self.version}:{payload_b64}"

    @classmethod
    def deserialize(cls, token: str) -> "EncryptedPayload":
        """Parse from wire format. Raises SecretPayloadFormatError on any issue."""
        try:
            parts = token.split(":", 2)
            if len(parts) != 3 or parts[0] != _PREFIX:
                raise SecretPayloadFormatError(
                    "Payload must start with 'nexora:<version>:<data>'.",
                    safe_detail="invalid_prefix",
                )
            version = parts[1]
            if version != _CURRENT_VERSION:
                raise SecretPayloadFormatError(
                    f"Unsupported payload version {version!r}.",
                    safe_detail=f"unsupported_version:{version}",
                )
            inner_json = json.loads(base64.urlsafe_b64decode(parts[2] + "=="))
            for field in ("version", "algorithm", "key_id", "nonce", "ciphertext"):
                if field not in inner_json:
                    raise SecretPayloadFormatError(
                        f"Missing field {field!r} in payload.",
                        safe_detail=f"missing_field:{field}",
                    )
            algorithm = inner_json["algorithm"]
            if algorithm not in _SUPPORTED_ALGORITHMS:
                raise SecretPayloadFormatError(
                    f"Unsupported algorithm {algorithm!r}.",
                    safe_detail=f"unsupported_algorithm:{algorithm}",
                )
            return cls(
                version=inner_json["version"],
                algorithm=algorithm,
                key_id=inner_json["key_id"],
                nonce=base64.urlsafe_b64decode(inner_json["nonce"] + "=="),
                ciphertext=base64.urlsafe_b64decode(inner_json["ciphertext"] + "=="),
            )
        except SecretPayloadFormatError:
            raise
        except Exception as exc:
            raise SecretPayloadFormatError(
                "Failed to parse encrypted payload.",
                safe_detail=f"parse_error:{type(exc).__name__}",
            ) from exc
