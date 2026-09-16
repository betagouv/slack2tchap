"""Test suite configuration and fixtures."""

from typing import Any
from uuid import UUID

import pytest

from slack2tchap.domain.models import MatrixAccount, User, WebhookEndpoint
from slack2tchap.domain.ports import (
    MatrixAccountRepositoryPort,
    MatrixMessengerPort,
    SecretCipherPort,
    UserRepositoryPort,
    WebhookRepositoryPort,
)
from slack2tchap.infrastructure.security.cipher import AesGcmSecretCipher


class FakeMatrixMessenger(MatrixMessengerPort):
    """In-memory Matrix messenger for testing purposes."""

    def __init__(self, encrypted_rooms: set[str] | None = None) -> None:
        self.sent_messages: list[dict[str, str]] = []
        self.joined_rooms: list[str] = []
        self.encrypted_rooms: set[str] = encrypted_rooms or set()
        self.should_fail: bool = False
        self.failure_message: str = "Simulated network error"

    async def send_message(
        self,
        room_id: str,
        formatted_body: str,
        plain_body: str,
    ) -> str:
        if self.should_fail:
            from slack2tchap.domain.exceptions import MessageSendError

            raise MessageSendError(self.failure_message)

        self.sent_messages.append(
            {
                "room_id": room_id,
                "formatted_body": formatted_body,
                "plain_body": plain_body,
            }
        )
        return f"$event_{len(self.sent_messages)}:matrix.agent.tchap.gouv.fr"

    async def is_room_encrypted(self, room_id: str) -> bool:
        return room_id in self.encrypted_rooms

    async def join_room(self, room_id: str) -> None:
        self.joined_rooms.append(room_id)

    async def check_health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "user_id": "@test-bot:agent.tchap.gouv.fr",
            "device_id": "test-device",
            "homeserver": "https://matrix.agent.tchap.gouv.fr",
            "logged_in": True,
            "sync_loop_running": True,
            "rooms_count": 2,
            "store_path": "/tmp/test_store",
        }

    async def request_verification(
        self,
        target_device_id: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> tuple[str, list[tuple[str, str]], str | None]:
        return (
            "tx_fake_sas_12345",
            [
                ("🐶", "Dog"),
                ("🚀", "Rocket"),
                ("🐱", "Cat"),
                ("🌟", "Star"),
                ("🍕", "Pizza"),
                ("🎩", "Top hat"),
                ("🚲", "Bicycle"),
            ],
            target_device_id or "DEVICE_OTHER",
        )


class FakeUserRepository(UserRepositoryPort):
    """In-memory repository for User entities."""

    def __init__(self) -> None:
        self.users_by_id: dict[UUID, User] = {}

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self.users_by_id.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        lowered = email.strip().lower()
        for u in self.users_by_id.values():
            if u.email == lowered:
                return u
        return None

    async def get_by_api_key_hash(self, key_hash: str) -> User | None:
        for u in self.users_by_id.values():
            if u.api_key_hash == key_hash:
                return u
        return None

    async def save(self, user: User) -> User:
        self.users_by_id[user.id] = user
        return user

    async def delete(self, user_id: UUID) -> bool:
        if user_id in self.users_by_id:
            del self.users_by_id[user_id]
            return True
        return False


class FakeMatrixAccountRepository(MatrixAccountRepositoryPort):
    """In-memory repository for MatrixAccount entities and crypto stores."""

    def __init__(self) -> None:
        self.accounts_by_id: dict[UUID, MatrixAccount] = {}

    async def get_by_id(self, account_id: UUID) -> MatrixAccount | None:
        return self.accounts_by_id.get(account_id)

    async def get_by_matrix_user_id(self, matrix_user_id: str) -> MatrixAccount | None:
        for acc in self.accounts_by_id.values():
            if acc.matrix_user_id == matrix_user_id:
                return acc
        return None

    async def list_by_user_id(self, user_id: UUID) -> list[MatrixAccount]:
        return [acc for acc in self.accounts_by_id.values() if acc.user_id == user_id]

    async def list_all_active(self) -> list[MatrixAccount]:
        return [acc for acc in self.accounts_by_id.values() if acc.is_active]

    async def save(self, account: MatrixAccount) -> MatrixAccount:
        self.accounts_by_id[account.id] = account
        return account

    async def save_crypto_store(self, account_id: UUID, store_blob: bytes) -> None:
        if account_id in self.accounts_by_id:
            self.accounts_by_id[account_id].crypto_store_blob = store_blob

    async def delete(self, account_id: UUID) -> bool:
        if account_id in self.accounts_by_id:
            del self.accounts_by_id[account_id]
            return True
        return False


class FakeWebhookRepository(WebhookRepositoryPort):
    """In-memory repository for WebhookEndpoint entities."""

    def __init__(self) -> None:
        self.webhooks_by_id: dict[UUID, WebhookEndpoint] = {}

    async def get_by_id(self, webhook_id: UUID) -> WebhookEndpoint | None:
        return self.webhooks_by_id.get(webhook_id)

    async def list_by_user_id(self, user_id: UUID) -> list[WebhookEndpoint]:
        return [w for w in self.webhooks_by_id.values() if w.user_id == user_id]

    async def list_by_matrix_account_id(self, matrix_account_id: UUID) -> list[WebhookEndpoint]:
        return [w for w in self.webhooks_by_id.values() if w.matrix_account_id == matrix_account_id]

    async def save(self, webhook: WebhookEndpoint) -> WebhookEndpoint:
        self.webhooks_by_id[webhook.id] = webhook
        return webhook

    async def delete(self, webhook_id: UUID) -> bool:
        if webhook_id in self.webhooks_by_id:
            del self.webhooks_by_id[webhook_id]
            return True
        return False


class FakeMatrixClientManager:
    """Fake client manager that returns a FakeMatrixMessenger."""

    def __init__(self, messenger: FakeMatrixMessenger) -> None:
        self.messenger = messenger
        self.removed_clients: list[UUID] = []

    async def get_or_create_client(self, account_id: UUID) -> MatrixMessengerPort:
        return self.messenger

    async def get_client(self, account_id: UUID) -> MatrixMessengerPort:
        return self.messenger

    async def remove_client(self, account_id: UUID) -> None:
        self.removed_clients.append(account_id)

    async def start_all_clients(self) -> None:
        pass


@pytest.fixture
def fake_matrix_messenger() -> FakeMatrixMessenger:
    return FakeMatrixMessenger(encrypted_rooms={"!encrypted_room:agent.tchap.gouv.fr"})


@pytest.fixture
def fake_user_repository() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def fake_matrix_account_repository() -> FakeMatrixAccountRepository:
    return FakeMatrixAccountRepository()


@pytest.fixture
def fake_webhook_repository() -> FakeWebhookRepository:
    return FakeWebhookRepository()


@pytest.fixture
def secret_cipher() -> SecretCipherPort:
    return AesGcmSecretCipher("32_bytes_super_secret_test_key_for_cipher!")
