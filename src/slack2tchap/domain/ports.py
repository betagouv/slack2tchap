"""Domain ports / interfaces for external communication and persistence."""

from typing import Any, Protocol
from uuid import UUID

from slack2tchap.domain.models import MatrixAccount, User, WebhookEndpoint


class MatrixMessengerPort(Protocol):
    """Port interface for Matrix messaging operations."""

    async def send_message(
        self,
        room_id: str,
        formatted_body: str,
        plain_body: str,
    ) -> str:
        """Send a message to a Matrix room (encrypted if room is encrypted)."""
        ...

    async def is_room_encrypted(self, room_id: str) -> bool:
        """Check whether a given room has encryption enabled."""
        ...

    async def join_room(self, room_id: str) -> None:
        """Join a room by its ID or alias."""
        ...

    async def check_health(self) -> dict[str, Any]:
        """Verify client connection and return status details."""
        ...

    async def request_verification(
        self,
        target_device_id: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> tuple[str, list[tuple[str, str]], str | None]:
        """Request or await interactive SAS key verification, returning (tx_id, emojis, target_device_id)."""
        ...


class MatrixClientManagerPort(Protocol):
    """Port interface for managing dynamic multi-tenant Matrix client sessions."""

    async def get_or_create_client(self, account_id: UUID) -> MatrixMessengerPort:
        """Retrieve active Matrix client or initialize one restoring its state."""
        ...

    async def get_client(self, account_id: UUID) -> MatrixMessengerPort:
        """Retrieve active Matrix client."""
        ...

    async def remove_client(self, account_id: UUID) -> None:
        """Close and remove an active Matrix client session."""
        ...


class UserRepositoryPort(Protocol):
    """Port interface for User persistence operations."""

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Find user by unique ID."""
        ...

    async def get_by_email(self, email: str) -> User | None:
        """Find user by email address."""
        ...

    async def get_by_api_key_hash(self, key_hash: str) -> User | None:
        """Find user by SHA-256 hash of their API key."""
        ...

    async def save(self, user: User) -> User:
        """Create or update a user entity."""
        ...

    async def delete(self, user_id: UUID) -> bool:
        """Delete a user by ID."""
        ...


class MatrixAccountRepositoryPort(Protocol):
    """Port interface for MatrixAccount persistence and crypto-store blob operations."""

    async def get_by_id(self, account_id: UUID) -> MatrixAccount | None:
        """Retrieve matrix account by unique ID."""
        ...

    async def get_by_matrix_user_id(self, matrix_user_id: str) -> MatrixAccount | None:
        """Retrieve matrix account by Matrix User ID."""
        ...

    async def list_by_user_id(self, user_id: UUID) -> list[MatrixAccount]:
        """List all matrix bot accounts configured by a user."""
        ...

    async def list_all_active(self) -> list[MatrixAccount]:
        """List all active matrix bot accounts."""
        ...

    async def save(self, account: MatrixAccount) -> MatrixAccount:
        """Create or update a matrix bot account."""
        ...

    async def save_crypto_store(self, account_id: UUID, store_blob: bytes) -> None:
        """Update the persisted E2EE SQLite crypto-store blob in PostgreSQL."""
        ...

    async def delete(self, account_id: UUID) -> bool:
        """Delete a matrix account by ID."""
        ...


class WebhookRepositoryPort(Protocol):
    """Port interface for WebhookEndpoint persistence operations."""

    async def get_by_id(self, webhook_id: UUID) -> WebhookEndpoint | None:
        """Retrieve webhook endpoint by public UUID."""
        ...

    async def list_by_user_id(self, user_id: UUID) -> list[WebhookEndpoint]:
        """List all webhooks belonging to a user."""
        ...

    async def list_by_matrix_account_id(self, matrix_account_id: UUID) -> list[WebhookEndpoint]:
        """List all webhooks configured for a specific matrix bot account."""
        ...

    async def save(self, webhook: WebhookEndpoint) -> WebhookEndpoint:
        """Create or update a webhook entity."""
        ...

    async def delete(self, webhook_id: UUID) -> bool:
        """Delete a webhook by its UUID."""
        ...


class SecretCipherPort(Protocol):
    """Port interface for symmetric AEAD encryption / decryption at rest."""

    def encrypt(self, plaintext: str) -> tuple[str, str]:
        """Encrypt plaintext and return (ciphertext_base64, nonce_base64)."""
        ...

    def decrypt(self, ciphertext_b64: str, nonce_b64: str) -> str:
        """Decrypt ciphertext with nonce and return plaintext string."""
        ...
