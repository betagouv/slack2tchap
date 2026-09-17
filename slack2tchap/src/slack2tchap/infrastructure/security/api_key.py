"""API key hashing utilities for slack2tchap bound to instance SECRET_ENCRYPTION_KEY."""

from slack2tchap.core.config import get_settings
from slack2tchap_core.infrastructure.security.api_key import (
    DEFAULT_API_KEY_SALT,
    extract_api_key_prefix,
)
from slack2tchap_core.infrastructure.security.api_key import (
    hash_api_key as core_hash_api_key,
)
from slack2tchap_core.infrastructure.security.api_key import (
    verify_api_key as core_verify_api_key,
)


def hash_api_key(raw_key: str, pepper: str | bytes | None = None) -> str:
    """Compute HMAC hash using instance SECRET_ENCRYPTION_KEY as secret pepper by default."""
    if pepper is None:
        try:
            pepper = get_settings().secret_encryption_key.get_secret_value()
        except Exception:
            pepper = None
    return core_hash_api_key(raw_key, pepper=pepper)


def verify_api_key(raw_key: str, expected_hash: str, pepper: str | bytes | None = None) -> bool:
    """Verify API key using instance SECRET_ENCRYPTION_KEY as secret pepper by default."""
    if pepper is None:
        try:
            pepper = get_settings().secret_encryption_key.get_secret_value()
        except Exception:
            pepper = None
    return core_verify_api_key(raw_key, expected_hash, pepper=pepper)


__all__ = [
    "DEFAULT_API_KEY_SALT",
    "extract_api_key_prefix",
    "hash_api_key",
    "verify_api_key",
]
