"""Tests for fully stateless Slack webhook route /slack?param={encrypted...}."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from nio import JoinResponse, LoginResponse, RoomSendResponse

from slack2tchap_core.domain.exceptions import AuthenticationError, CipherError
from slack2tchap_core.infrastructure.security.cipher import AesGcmSecretCipher
from slack2tchap_core.matrix.helpers import resolve_homeserver_url
from slack2tchap_stateless.infrastructure.matrix.messenger import (
    StatelessMatrixMessenger,
)
from slack2tchap_stateless.interfaces.api.dependencies import (
    get_secret_cipher,
    get_stateless_messenger,
)
from slack2tchap_stateless.main import create_app
from stateless_fakes import FakeStatelessMessenger

TEST_CIPHER_SECRET = "32_bytes_super_secret_test_key_for_cipher!"


# ============================================================================
# 1. CIPHER TOKEN ENCRYPTION & DECRYPTION UNIT TESTS
# ============================================================================


def test_cipher_encrypt_and_decrypt_token() -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    original_data = {
        "username": "@bot:agent.tchap.gouv.fr",
        "password": "super_secret_password_123",
        "channelID": "!myroom:agent.tchap.gouv.fr",
    }
    raw_json = json.dumps(original_data)

    token = cipher.encrypt_token(raw_json)
    assert isinstance(token, str)
    assert len(token) > 28
    assert "+" not in token
    assert "/" not in token
    assert "=" not in token

    decrypted = cipher.decrypt_token(token)
    assert json.loads(decrypted) == original_data


def test_cipher_token_randomized_nonces() -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    text = json.dumps({"test": "value"})

    token1 = cipher.encrypt_token(text)
    token2 = cipher.encrypt_token(text)
    assert token1 != token2
    assert cipher.decrypt_token(token1) == text
    assert cipher.decrypt_token(token2) == text


def test_cipher_token_tampering_fails() -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    token = cipher.encrypt_token(json.dumps({"msg": "secret"}))

    tampered = token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]
    with pytest.raises(CipherError, match="Integrity check failed"):
        cipher.decrypt_token(tampered)


def test_cipher_token_empty_and_short_fails() -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    with pytest.raises(CipherError, match="cannot be empty"):
        cipher.decrypt_token("")

    with pytest.raises(CipherError, match="payload too short"):
        cipher.decrypt_token("short_token")


# ============================================================================
# 2. STATELESS WEBHOOK ENDPOINT INTEGRATION TESTS (/slack?param=...)
# ============================================================================


@pytest.mark.asyncio
async def test_stateless_webhook_success(
    fake_stateless_messenger: FakeStatelessMessenger,
) -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    token_data = {
        "username": "@bot:agent.tchap.gouv.fr",
        "password": "bot_password_123",
        "channelID": "!room123:agent.tchap.gouv.fr",
    }
    param_token = cipher.encrypt_token(json.dumps(token_data))

    app = create_app()
    app.dependency_overrides[get_secret_cipher] = lambda: cipher
    app.dependency_overrides[get_stateless_messenger] = lambda: fake_stateless_messenger

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/slack?param={param_token}",
            json={
                "text": "Incident critique détecté",
                "attachments": [
                    {
                        "color": "danger",
                        "title": "Alerte Disque",
                        "text": "Espace disque /var/log saturé à 98%",
                    }
                ],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "success"
    assert "event_id" in data

    assert len(fake_stateless_messenger.sent_messages) == 1
    sent = fake_stateless_messenger.sent_messages[0]
    assert sent["user_id"] == "@bot:agent.tchap.gouv.fr"
    assert sent["password"] == "bot_password_123"
    assert sent["room_id"] == "!room123:agent.tchap.gouv.fr"
    assert "Incident critique" in sent["formatted_body"]
    assert "Espace disque" in sent["formatted_body"]


@pytest.mark.asyncio
async def test_stateless_webhook_with_access_token(
    fake_stateless_messenger: FakeStatelessMessenger,
) -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    token_data = {
        "username": "@bot:agent.tchap.gouv.fr",
        "access_token": "syt_token_abc123",
        "channelID": "!room123:agent.tchap.gouv.fr",
    }
    param_token = cipher.encrypt_token(json.dumps(token_data))

    app = create_app()
    app.dependency_overrides[get_secret_cipher] = lambda: cipher
    app.dependency_overrides[get_stateless_messenger] = lambda: fake_stateless_messenger

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/webhook/slack?param={param_token}",
            json={"text": "Test avec access token"},
        )

    assert resp.status_code == 200
    assert len(fake_stateless_messenger.sent_messages) == 1
    sent = fake_stateless_messenger.sent_messages[0]
    assert sent["access_token"] == "syt_token_abc123"
    assert sent["password"] is None


@pytest.mark.asyncio
async def test_stateless_webhook_with_alternative_field_names(
    fake_stateless_messenger: FakeStatelessMessenger,
) -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    token_data = {
        "login": "@alt_bot:agent.tchap.gouv.fr",
        "password": "alt_password",
        "room_id": "!alt_room:agent.tchap.gouv.fr",
    }
    param_token = cipher.encrypt_token(json.dumps(token_data))

    app = create_app()
    app.dependency_overrides[get_secret_cipher] = lambda: cipher
    app.dependency_overrides[get_stateless_messenger] = lambda: fake_stateless_messenger

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/slack?param={param_token}",
            json={"text": "Hello alternative fields"},
        )

    assert resp.status_code == 200
    sent = fake_stateless_messenger.sent_messages[0]
    assert sent["user_id"] == "@alt_bot:agent.tchap.gouv.fr"
    assert sent["room_id"] == "!alt_room:agent.tchap.gouv.fr"


@pytest.mark.asyncio
async def test_stateless_webhook_tampered_param_returns_400() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/slack?param=tampered_invalid_base64_payload",
            json={"text": "Test"},
        )

    assert resp.status_code == 400
    assert "Invalid or tampered" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_stateless_webhook_missing_param_returns_422() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/slack", json={"text": "Hello"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_stateless_webhook_missing_required_fields_returns_400() -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    token_data = {"username": "@bot:agent.tchap.gouv.fr"}
    param_token = cipher.encrypt_token(json.dumps(token_data))

    app = create_app()
    app.dependency_overrides[get_secret_cipher] = lambda: cipher

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/slack?param={param_token}",
            json={"text": "Hello"},
        )

    assert resp.status_code == 422 or resp.status_code == 400


@pytest.mark.asyncio
async def test_stateless_webhook_invalid_room_id_format_returns_422() -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    token_data = {
        "username": "@bot:agent.tchap.gouv.fr",
        "password": "pwd",
        "channel_id": "not-a-valid-matrix-room",
    }
    param_token = cipher.encrypt_token(json.dumps(token_data))

    app = create_app()
    app.dependency_overrides[get_secret_cipher] = lambda: cipher

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/slack?param={param_token}",
            json={"text": "Hello"},
        )

    assert resp.status_code == 422
    assert "Invalid Matrix Room ID" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_stateless_webhook_dispatch_failure(
    fake_stateless_messenger: FakeStatelessMessenger,
) -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    token_data = {
        "username": "@bot:agent.tchap.gouv.fr",
        "password": "pwd",
        "channel_id": "!room:agent.tchap.gouv.fr",
    }
    param_token = cipher.encrypt_token(json.dumps(token_data))

    fake_stateless_messenger.should_fail = True
    fake_stateless_messenger.failure_message = "Matrix connection timeout"

    app = create_app()
    app.dependency_overrides[get_secret_cipher] = lambda: cipher
    app.dependency_overrides[get_stateless_messenger] = lambda: fake_stateless_messenger

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/slack?param={param_token}",
            json={"text": "Hello"},
        )

    assert resp.status_code == 502
    assert "Matrix connection timeout" in resp.json()["detail"]


# ============================================================================
# 3. STATELESS MATRIX MESSENGER UNIT TESTS
# ============================================================================


def test_resolve_homeserver_url() -> None:
    default_hs = "https://matrix.agent.tchap.gouv.fr"
    # Same domain
    assert (
        resolve_homeserver_url(default_hs, "@bot:agent.tchap.gouv.fr")
        == "https://matrix.agent.tchap.gouv.fr"
    )
    # Other Tchap domain
    assert (
        resolve_homeserver_url(default_hs, "@bot:autre.tchap.gouv.fr")
        == "https://matrix.autre.tchap.gouv.fr"
    )
    # Without server domain fallback
    assert resolve_homeserver_url(default_hs, "bot") == default_hs


@pytest.mark.asyncio
async def test_stateless_matrix_messenger_lifecycle() -> None:
    messenger = StatelessMatrixMessenger(default_homeserver="https://matrix.agent.tchap.gouv.fr")

    mock_client = AsyncMock()
    mock_client.login = AsyncMock(
        return_value=LoginResponse(
            user_id="@bot:agent.tchap.gouv.fr", device_id="s2t_123", access_token="token"
        )
    )
    mock_client.join = AsyncMock(return_value=JoinResponse(room_id="!room:agent.tchap.gouv.fr"))
    mock_client.room_send = AsyncMock(
        return_value=RoomSendResponse(room_id="!room:agent.tchap.gouv.fr", event_id="$ev_12345")
    )
    mock_client.close = AsyncMock()

    with patch(
        "slack2tchap_stateless.infrastructure.matrix.messenger.AsyncClient",
        return_value=mock_client,
    ):
        event_id = await messenger.send_message(
            homeserver="https://matrix.agent.tchap.gouv.fr",
            user_id="@bot:agent.tchap.gouv.fr",
            password="secret_password",
            access_token=None,
            room_id="!room:agent.tchap.gouv.fr",
            formatted_body="<b>Alert</b>",
            plain_body="Alert",
        )

    assert event_id == "$ev_12345"
    mock_client.login.assert_awaited_once_with(password="secret_password")
    mock_client.join.assert_awaited_once_with("!room:agent.tchap.gouv.fr")
    mock_client.room_send.assert_awaited_once()
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stateless_matrix_messenger_login_failure() -> None:
    from nio import LoginError

    messenger = StatelessMatrixMessenger(default_homeserver="https://matrix.agent.tchap.gouv.fr")

    mock_client = AsyncMock()
    mock_client.login = AsyncMock(
        return_value=LoginError(message="Invalid credentials", status_code="M_FORBIDDEN")
    )
    mock_client.close = AsyncMock()

    with patch(
        "slack2tchap_stateless.infrastructure.matrix.messenger.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(AuthenticationError, match="Matrix login failed"):
            await messenger.send_message(
                homeserver="https://matrix.agent.tchap.gouv.fr",
                user_id="@bot:agent.tchap.gouv.fr",
                password="wrong_password",
                access_token=None,
                room_id="!room:agent.tchap.gouv.fr",
                formatted_body="<b>Alert</b>",
                plain_body="Alert",
            )

    mock_client.close.assert_awaited_once()


def test_stateless_settings_production_security(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pydantic import ValidationError

    from slack2tchap_stateless.core.config import DEFAULT_INSECURE_SECRET_KEY, Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # By default without environment variables or .env: defaults to production and rejects default key
    with pytest.raises(ValidationError, match="SECRET_ENCRYPTION_KEY must be explicitly set"):
        Settings()

    # In production with explicit insecure key: fails
    with pytest.raises(ValidationError, match="SECRET_ENCRYPTION_KEY must be explicitly set"):
        Settings(
            environment="production",
            secret_encryption_key=DEFAULT_INSECURE_SECRET_KEY,  # type: ignore[arg-type]
        )

    # In production with custom secure key: succeeds and environment is production
    prod_settings = Settings(
        secret_encryption_key="custom_production_key_32_bytes_long!",  # type: ignore[arg-type]
    )
    assert prod_settings.environment == "production"

    # In development mode: default key is accepted
    dev_settings = Settings(
        environment="development",
    )
    assert dev_settings.environment == "development"


@pytest.mark.asyncio
async def test_stateless_webhook_text_format(
    fake_stateless_messenger: FakeStatelessMessenger,
) -> None:
    cipher = AesGcmSecretCipher(TEST_CIPHER_SECRET)
    token_data = {
        "username": "@bot:agent.tchap.gouv.fr",
        "password": "bot_password_123",
        "channelID": "!room123:agent.tchap.gouv.fr",
    }
    param_token = cipher.encrypt_token(json.dumps(token_data))

    app = create_app()
    app.dependency_overrides[get_secret_cipher] = lambda: cipher
    app.dependency_overrides[get_stateless_messenger] = lambda: fake_stateless_messenger

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test with format=text query param
        resp = await client.post(
            f"/slack?param={param_token}&format=text",
            json={"text": "Alert text format"},
        )
        assert resp.status_code == 200
        assert resp.text == "ok"
        assert resp.headers["content-type"].startswith("text/plain")

        # Test with Accept: text/plain header
        resp_header = await client.post(
            f"/slack?param={param_token}",
            headers={"Accept": "text/plain"},
            json={"text": "Alert accept header"},
        )
        assert resp_header.status_code == 200
        assert resp_header.text == "ok"
        assert resp_header.headers["content-type"].startswith("text/plain")
