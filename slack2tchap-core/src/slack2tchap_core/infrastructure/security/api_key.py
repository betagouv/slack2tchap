"""Cryptographic hashing and validation utilities for API keys."""

import hashlib
import hmac

# Public application domain salt used when no instance secret pepper is supplied (e.g. standalone CLI)
DEFAULT_API_KEY_SALT = b"slack2tchap_api_key_salt_v1"


def hash_api_key(raw_key: str, pepper: str | bytes | None = None) -> str:
    """Compute HMAC-SHA256 hexadecimal hash of a raw API key.

    When `pepper` is provided (typically the server's SECRET_ENCRYPTION_KEY),
    the hash is cryptographically bound to that specific deployment instance.
    Even if an attacker dumps the SQL database, they cannot verify or attack
    stored hashes without the server's secret master key.
    """
    key_bytes = (
        pepper.encode("utf-8") if isinstance(pepper, str) else (pepper or DEFAULT_API_KEY_SALT)
    )
    return hmac.new(
        key_bytes,
        raw_key.strip().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def extract_api_key_prefix(raw_key: str, length: int = 12) -> str:
    """Extract public non-sensitive prefix of the API key for display/logging."""
    cleaned = raw_key.strip()
    return cleaned[:length] + "..." if len(cleaned) > length else cleaned


def verify_api_key(raw_key: str, expected_hash: str, pepper: str | bytes | None = None) -> bool:
    """Verify an incoming API key against its stored hash using constant-time comparison."""
    computed_hash = hash_api_key(raw_key, pepper=pepper)
    return hmac.compare_digest(computed_hash, expected_hash)
