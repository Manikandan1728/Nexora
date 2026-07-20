"""
app/security/secrets/generate_key.py — Development key-generation utility.

[ADDITIVE] Phase 12.

Usage:
    python -m app.security.secrets.generate_key

Generates a cryptographically secure 32-byte AES-256 key encoded as
base64url. Prints usage instructions. Never writes to .env automatically.
"""
from __future__ import annotations
import base64
import secrets as _secrets
import sys


def generate_aes256_key() -> str:
    """Generate a cryptographically secure 32-byte key, base64url-encoded."""
    key_bytes = _secrets.token_bytes(32)
    return base64.urlsafe_b64encode(key_bytes).decode("ascii").rstrip("=")


def main() -> None:
    key = generate_aes256_key()
    print("=" * 60)
    print("Nexora AES-256-GCM Key Generator")
    print("=" * 60)
    print()
    print("Generated key (base64url, 32 bytes / 256 bits):")
    print()
    print(f"  {key}")
    print()
    print("Add to your .env file:")
    print()
    print(f"  NEXORA_SECRET_STORE_PROVIDER=environment")
    print(f"  NEXORA_SECRET_ENCRYPTION_KEY={key}")
    print(f"  NEXORA_SECRET_KEY_ID=prod-key-1")
    print(f"  NEXORA_SECRET_ENCRYPTION_VERSION=v1")
    print()
    print("WARNINGS:")
    print("  - Store this key securely outside source control.")
    print("  - Never commit this key to Git.")
    print("  - Losing this key means encrypted secrets cannot be recovered.")
    print("  - This script does NOT modify any .env file automatically.")
    print("=" * 60)


if __name__ == "__main__":
    main()
