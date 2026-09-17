"""Cryptographic hashing and validation utilities for API keys."""

import hashlib
import hmac


def hash_api_key(raw_key: str) -> str:
    """Compute SHA-256 hexadecimal hash of a raw API key.

    For high-entropy API keys (256 bits of cryptographic randomness), SHA-256
    is the standard industry recommendation (RFC / Stripe / GitHub pattern)
    as brute-force resistance is guaranteed by high entropy without requiring
    expensive KDF CPU stretching.
    """
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def extract_api_key_prefix(raw_key: str, length: int = 12) -> str:
    """Extract public non-sensitive prefix of the API key for display/logging."""
    cleaned = raw_key.strip()
    return cleaned[:length] + "..." if len(cleaned) > length else cleaned


def verify_api_key(raw_key: str, expected_hash: str) -> bool:
    """Verify an incoming API key against its stored SHA-256 hash using constant-time comparison."""
    computed_hash = hash_api_key(raw_key)
    return hmac.compare_digest(computed_hash, expected_hash)
