"""Test suite configuration and fixtures for slack2tchap."""

import os

# Ensure default development environment variables are set before importing app/config
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault(
    "SECRET_ENCRYPTION_KEY",
    "32_bytes_super_secret_test_key_for_cipher!",
)

import pytest

from fakes import (
    FakeMatrixAccountRepository,
    FakeMatrixClientManager,
    FakeMatrixMessenger,
    FakeUserRepository,
    FakeWebhookRepository,
)
from slack2tchap.domain.ports import SecretCipherPort
from slack2tchap.infrastructure.security.cipher import AesGcmSecretCipher


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
def fake_matrix_client_manager(
    fake_matrix_messenger: FakeMatrixMessenger,
) -> FakeMatrixClientManager:
    return FakeMatrixClientManager(fake_matrix_messenger)


@pytest.fixture
def secret_cipher() -> SecretCipherPort:
    return AesGcmSecretCipher("32_bytes_super_secret_test_key_for_cipher!")
