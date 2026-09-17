"""Test fixtures for slack2tchap-stateless."""

import os
from collections.abc import AsyncGenerator

# Ensure default development environment variables are set before importing app/config
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault(
    "SECRET_ENCRYPTION_KEY",
    "32_bytes_super_secret_test_key_for_cipher!",
)

import pytest
from httpx import ASGITransport, AsyncClient

from slack2tchap_core.domain.ports import SecretCipherPort
from slack2tchap_core.infrastructure.security.cipher import AesGcmSecretCipher
from slack2tchap_stateless.application.use_cases import ProcessStatelessWebhookUseCase
from slack2tchap_stateless.core.config import Settings, get_settings
from slack2tchap_stateless.interfaces.api.dependencies import (
    get_process_stateless_webhook_use_case,
    get_secret_cipher,
    get_stateless_messenger,
)
from slack2tchap_stateless.main import app
from stateless_fakes import FakeStatelessMessenger

TEST_SECRET_KEY = "32_bytes_super_secret_test_key_for_cipher!"


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="test",
        secret_encryption_key=TEST_SECRET_KEY,  # type: ignore[arg-type]
        matrix_homeserver="https://matrix.agent.tchap.gouv.fr",
        matrix_auto_join=True,
    )


@pytest.fixture
def secret_cipher() -> SecretCipherPort:
    return AesGcmSecretCipher(TEST_SECRET_KEY)


@pytest.fixture
def fake_stateless_messenger() -> FakeStatelessMessenger:
    return FakeStatelessMessenger()


@pytest.fixture
async def client(
    test_settings: Settings,
    secret_cipher: SecretCipherPort,
    fake_stateless_messenger: FakeStatelessMessenger,
) -> AsyncGenerator[AsyncClient, None]:
    use_case = ProcessStatelessWebhookUseCase(
        cipher=secret_cipher,
        stateless_messenger=fake_stateless_messenger,
    )

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_secret_cipher] = lambda: secret_cipher
    app.dependency_overrides[get_stateless_messenger] = lambda: fake_stateless_messenger
    app.dependency_overrides[get_process_stateless_webhook_use_case] = lambda: use_case

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
