"""Unit tests for cryptographic security components (API keys and AES-GCM cipher)."""

import pytest

from slack2tchap.domain.exceptions import CipherError
from slack2tchap.infrastructure.security.api_key import (
    extract_api_key_prefix,
    hash_api_key,
    verify_api_key,
)
from slack2tchap.infrastructure.security.cipher import AesGcmSecretCipher


def test_api_key_hashing_and_verification() -> None:
    raw_key = "s2t_live_m7m8eI6a8AXfqqfkZHKVLQlmL9U8F08axYlK5Zhd-S8"
    key_hash = hash_api_key(raw_key)

    assert len(key_hash) == 64  # SHA-256 is 64 hex characters
    assert verify_api_key(raw_key, key_hash) is True
    assert verify_api_key("s2t_live_wrong_key", key_hash) is False


def test_api_key_prefix_extraction() -> None:
    raw_key = "s2t_live_m7m8eI6a8AXfqqfkZHKVLQlmL9U8F08axYlK5Zhd-S8"
    prefix = extract_api_key_prefix(raw_key, length=12)

    assert prefix == "s2t_live_m7m..."


def test_aes_gcm_cipher_encrypt_decrypt() -> None:
    cipher = AesGcmSecretCipher("master_secret_encryption_key_32_bytes_long!")
    plaintext = "super_confidential_matrix_bot_password_123"

    ciphertext_b64, nonce_b64 = cipher.encrypt(plaintext)

    assert ciphertext_b64 != plaintext
    assert nonce_b64 is not None

    decrypted = cipher.decrypt(ciphertext_b64, nonce_b64)
    assert decrypted == plaintext


def test_aes_gcm_nonce_uniqueness() -> None:
    cipher = AesGcmSecretCipher("master_secret_encryption_key_32_bytes_long!")
    plaintext = "identical_message"

    c1, n1 = cipher.encrypt(plaintext)
    c2, n2 = cipher.encrypt(plaintext)

    # Even with identical plaintext, nonces and ciphertexts must differ
    assert n1 != n2
    assert c1 != c2

    assert cipher.decrypt(c1, n1) == plaintext
    assert cipher.decrypt(c2, n2) == plaintext


def test_aes_gcm_tamper_detection() -> None:
    cipher = AesGcmSecretCipher("master_secret_encryption_key_32_bytes_long!")
    ciphertext_b64, nonce_b64 = cipher.encrypt("secret")

    # Corrupt ciphertext
    tampered_bytes = bytearray(ciphertext_b64.encode("ascii"))
    tampered_bytes[5] = ord("A") if tampered_bytes[5] != ord("A") else ord("B")
    tampered_b64 = tampered_bytes.decode("ascii")

    with pytest.raises(CipherError, match="Integrity check failed|Decryption failed"):
        cipher.decrypt(tampered_b64, nonce_b64)


def test_aes_gcm_wrong_key_fails() -> None:
    cipher1 = AesGcmSecretCipher("key_one_secret_32_bytes_master_key!!")
    cipher2 = AesGcmSecretCipher("key_two_secret_32_bytes_master_key!!")

    ciphertext_b64, nonce_b64 = cipher1.encrypt("confidential")

    with pytest.raises(CipherError, match="Integrity check failed|Decryption failed"):
        cipher2.decrypt(ciphertext_b64, nonce_b64)


def test_production_environment_rejects_default_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import ValidationError

    from slack2tchap.core.config import DEFAULT_INSECURE_SECRET_KEY, Settings

    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    # In production with default key: must raise ValidationError
    with pytest.raises(ValidationError, match="SECRET_ENCRYPTION_KEY must be explicitly set"):
        Settings(
            environment="production",
            secret_encryption_key=DEFAULT_INSECURE_SECRET_KEY,  # type: ignore[arg-type]
        )

    # In production with custom secure key: valid
    s = Settings(
        environment="production",
        secret_encryption_key="custom_production_secure_master_key_256!!",  # type: ignore[arg-type]
    )
    assert s.environment == "production"
