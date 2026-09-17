"""Authenticated symmetric encryption at rest using AES-256-GCM."""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from slack2tchap_core.domain.exceptions import CipherError
from slack2tchap_core.domain.ports import SecretCipherPort

# Fixed application salt for PBKDF2 master key derivation
MASTER_KEY_KDF_SALT = b"slack2tchap-master-cipher-kdf-salt-v1"
MASTER_KEY_KDF_ITERATIONS = 100_000


class AesGcmSecretCipher(SecretCipherPort):
    """AES-256-GCM authenticated cipher for encrypting sensitive credentials at rest and tokens."""

    def __init__(self, master_key_secret: str) -> None:
        if not master_key_secret:
            raise CipherError("Master encryption key cannot be empty.")

        # Robust PBKDF2-HMAC-SHA256 key derivation (100,000 iterations)
        # Prevents brute-force on human passphrases and satisfies CodeQL KDF requirements.
        self._key = hashlib.pbkdf2_hmac(
            "sha256",
            master_key_secret.encode("utf-8"),
            MASTER_KEY_KDF_SALT,
            iterations=MASTER_KEY_KDF_ITERATIONS,
        )
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plaintext: str) -> tuple[str, str]:
        """Encrypt plaintext into Base64 ciphertext with unique 96-bit nonce."""
        if not plaintext:
            return "", ""

        try:
            # 96-bit (12 bytes) standard nonce for AES-GCM
            nonce = os.urandom(12)
            ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

            ciphertext_b64 = base64.b64encode(ciphertext).decode("ascii")
            nonce_b64 = base64.b64encode(nonce).decode("ascii")
            return ciphertext_b64, nonce_b64
        except Exception as exc:
            raise CipherError(f"Encryption failed: {exc}") from exc

    def decrypt(self, ciphertext_b64: str, nonce_b64: str) -> str:
        """Decrypt Base64 ciphertext using unique nonce, validating authentication tag."""
        if not ciphertext_b64 or not nonce_b64:
            return ""

        try:
            ciphertext = base64.b64decode(ciphertext_b64.encode("ascii"))
            nonce = base64.b64decode(nonce_b64.encode("ascii"))

            decrypted_bytes = self._aesgcm.decrypt(nonce, ciphertext, None)
            return decrypted_bytes.decode("utf-8")
        except InvalidTag as exc:
            raise CipherError(
                "Integrity check failed: ciphertext has been tampered with or key is invalid."
            ) from exc
        except Exception as exc:
            raise CipherError(f"Decryption failed: {exc}") from exc

    def encrypt_token(self, plaintext: str) -> str:
        """Encrypt plaintext into a URL-safe compact string containing 12-byte nonce + ciphertext + tag."""
        if not plaintext:
            return ""

        try:
            nonce = os.urandom(12)
            ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
            # Combine nonce and ciphertext+tag, encode as URL-safe base64 without padding
            combined = nonce + ciphertext
            return base64.urlsafe_b64encode(combined).decode("ascii").rstrip("=")
        except Exception as exc:
            raise CipherError(f"Token encryption failed: {exc}") from exc

    def decrypt_token(self, token: str) -> str:
        """Decrypt a URL-safe compact token, extracting nonce and validating authentication tag."""
        if not token or not token.strip():
            raise CipherError("Encrypted token cannot be empty.")

        try:
            raw_token = token.strip()
            # Restore base64 padding if needed
            padding = len(raw_token) % 4
            if padding:
                raw_token += "=" * (4 - padding)

            raw_bytes = base64.urlsafe_b64decode(raw_token.encode("ascii"))
            # Minimum length: 12 bytes nonce + 16 bytes tag = 28 bytes
            if len(raw_bytes) < 28:
                raise CipherError("Invalid token length: payload too short.")

            nonce = raw_bytes[:12]
            ciphertext = raw_bytes[12:]
            decrypted_bytes = self._aesgcm.decrypt(nonce, ciphertext, None)
            return decrypted_bytes.decode("utf-8")
        except InvalidTag as exc:
            raise CipherError(
                "Integrity check failed: token has been tampered with or key is invalid."
            ) from exc
        except CipherError:
            raise
        except Exception as exc:
            raise CipherError(f"Token decryption failed: {exc}") from exc
