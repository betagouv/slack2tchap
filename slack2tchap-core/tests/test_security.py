"""Unit tests for slack2tchap_core cryptographic security components."""

import pytest

from slack2tchap_core.domain.exceptions import CipherError
from slack2tchap_core.infrastructure.security.api_key import (
    extract_api_key_prefix,
    hash_api_key,
    verify_api_key,
)
from slack2tchap_core.infrastructure.security.cipher import AesGcmSecretCipher


def test_api_key_hashing_and_verification() -> None:
    raw_key = "s2t_live_m7m8eI6a8AXfqqfkZHKVLQlmL9U8F08axYlK5Zhd-S8"
    key_hash = hash_api_key(raw_key)

    assert len(key_hash) == 64  # SHA-256 is 64 hex characters
    assert verify_api_key(raw_key, key_hash) is True
    assert verify_api_key("s2t_live_wrong_key", key_hash) is False


def test_api_key_hashing_with_instance_pepper() -> None:
    raw_key = "s2t_live_m7m8eI6a8AXfqqfkZHKVLQlmL9U8F08axYlK5Zhd-S8"
    pepper_a = "instance_secret_pepper_aaaaa_32bytes!"
    pepper_b = "instance_secret_pepper_bbbbb_32bytes!"

    hash_default = hash_api_key(raw_key)
    hash_a = hash_api_key(raw_key, pepper=pepper_a)
    hash_b = hash_api_key(raw_key, pepper=pepper_b)

    # Hashes must differ across different instance peppers
    assert hash_a != hash_b
    assert hash_a != hash_default
    assert hash_b != hash_default

    # Verification must succeed only with the matching pepper
    assert verify_api_key(raw_key, hash_a, pepper=pepper_a) is True
    assert verify_api_key(raw_key, hash_a, pepper=pepper_b) is False
    assert verify_api_key(raw_key, hash_a) is False


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


def test_aes_gcm_token_encrypt_decrypt() -> None:
    cipher = AesGcmSecretCipher("master_secret_encryption_key_32_bytes_long!")
    plaintext = '{"username": "@bot:matrix.org", "channel": "!room:matrix.org"}'

    token = cipher.encrypt_token(plaintext)
    assert isinstance(token, str)
    assert "=" not in token  # URL-safe without padding

    decrypted = cipher.decrypt_token(token)
    assert decrypted == plaintext


def test_aes_gcm_token_tampering() -> None:
    cipher = AesGcmSecretCipher("master_secret_encryption_key_32_bytes_long!")
    token = cipher.encrypt_token("hello world")

    # Tamper with token
    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    with pytest.raises(CipherError):
        cipher.decrypt_token(tampered)
