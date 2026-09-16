"""Authenticated symmetric encryption at rest using AES-256-GCM."""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from slack2tchap.domain.exceptions import CipherError
from slack2tchap.domain.ports import SecretCipherPort


class AesGcmSecretCipher(SecretCipherPort):
    """AES-256-GCM authenticated cipher for encrypting sensitive credentials at rest."""

    def __init__(self, master_key_secret: str) -> None:
        if not master_key_secret:
            raise CipherError("Master encryption key cannot be empty.")

        # Ensure exact 32-byte key using SHA-256 derivation
        self._key = hashlib.sha256(master_key_secret.encode("utf-8")).digest()
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
