"""Integration tests for public UUID webhook routing and admin multi-bot management."""

import pytest
from httpx import ASGITransport, AsyncClient

from fakes import (
    FakeMatrixAccountRepository,
    FakeMatrixClientManager,
    FakeMatrixMessenger,
    FakeUserRepository,
    FakeWebhookRepository,
)
from slack2tchap.domain.models import User
from slack2tchap.infrastructure.security.api_key import hash_api_key
from slack2tchap.interfaces.api.dependencies import (
    get_matrix_account_repository,
    get_matrix_client_manager,
    get_user_repository,
    get_webhook_repository,
)
from slack2tchap.main import create_app


@pytest.mark.asyncio
async def test_full_flow_matrix_account_and_public_webhook(
    fake_matrix_messenger: FakeMatrixMessenger,
    fake_webhook_repository: FakeWebhookRepository,
    fake_matrix_account_repository: FakeMatrixAccountRepository,
    fake_user_repository: FakeUserRepository,
) -> None:
    # 1. Create admin user
    raw_key = "s2t_live_secret_admin_key_99999"
    admin_user = User(
        email="admin@tchap.gouv.fr",
        api_key_hash=hash_api_key(raw_key),
        api_key_prefix="s2t_live_sec...",
        is_admin=True,
    )
    await fake_user_repository.save(admin_user)

    fake_client_manager = FakeMatrixClientManager(fake_matrix_messenger)

    app = create_app()
    app.dependency_overrides[get_matrix_client_manager] = lambda: fake_client_manager
    app.dependency_overrides[get_matrix_account_repository] = lambda: fake_matrix_account_repository
    app.dependency_overrides[get_webhook_repository] = lambda: fake_webhook_repository
    app.dependency_overrides[get_user_repository] = lambda: fake_user_repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2. Register a Matrix Bot account
        bot_resp = await client.post(
            "/api/v1/admin/matrix-accounts",
            headers={"X-API-Key": raw_key},
            json={
                "name": "Bot Alertmanager",
                "matrix_user_id": "@bot-alertmanager:agent.tchap.gouv.fr",
                "password": "bot_password_123",
            },
        )
        assert bot_resp.status_code == 201
        bot_data = bot_resp.json()
        bot_id = bot_data["id"]
        assert bot_data["matrix_user_id"] == "@bot-alertmanager:agent.tchap.gouv.fr"

        # 3. Create a Webhook assigned to this bot
        webhook_resp = await client.post(
            "/api/v1/admin/webhooks",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={
                "name": "Production Alerts Webhook",
                "matrix_room_id": "!prod_room:agent.tchap.gouv.fr",
                "matrix_account_id": bot_id,
            },
        )
        assert webhook_resp.status_code == 201
        webhook_data = webhook_resp.json()
        webhook_id = webhook_data["id"]
        assert f"/webhook/slack/{webhook_id}" in webhook_data["public_url"]

        # 4. Ingest public webhook without ANY authentication header
        alert_resp = await client.post(
            f"/webhook/slack/{webhook_id}",
            json={
                "text": "Disk space critically low on srv-db-01",
                "attachments": [
                    {
                        "color": "danger",
                        "title": "Storage Alert",
                        "fields": [{"title": "Usage", "value": "98%"}],
                    }
                ],
            },
        )
        assert alert_resp.status_code == 200
        alert_data = alert_resp.json()
        assert alert_data["success"] is True
        assert alert_data["room_id"] == "!prod_room:agent.tchap.gouv.fr"
        assert len(fake_matrix_messenger.sent_messages) == 1

        # 5. Short alias /slack/{webhook_id}
        short_resp = await client.post(
            f"/slack/{webhook_id}",
            json={"text": "Short route alert"},
        )
        assert short_resp.status_code == 200

        # 6. List and Delete Webhook
        list_resp = await client.get(
            "/api/v1/admin/webhooks",
            headers={"X-API-Key": raw_key},
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        del_resp = await client.delete(
            f"/api/v1/admin/webhooks/{webhook_id}",
            headers={"X-API-Key": raw_key},
        )
        assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_admin_routes_require_valid_api_key(
    fake_user_repository: FakeUserRepository,
    fake_matrix_account_repository: FakeMatrixAccountRepository,
    fake_webhook_repository: FakeWebhookRepository,
) -> None:
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: fake_user_repository
    app.dependency_overrides[get_matrix_account_repository] = lambda: fake_matrix_account_repository
    app.dependency_overrides[get_webhook_repository] = lambda: fake_webhook_repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Without headers -> 401
        res1 = await client.get("/api/v1/admin/matrix-accounts")
        assert res1.status_code == 401

        # With invalid key -> 401
        res2 = await client.get(
            "/api/v1/admin/matrix-accounts", headers={"X-API-Key": "s2t_live_fake"}
        )
        assert res2.status_code == 401


@pytest.mark.asyncio
async def test_verify_matrix_bot_endpoint(
    fake_matrix_messenger: FakeMatrixMessenger,
    fake_matrix_account_repository: FakeMatrixAccountRepository,
    fake_user_repository: FakeUserRepository,
) -> None:
    from slack2tchap.domain.models import MatrixAccount

    raw_key = "s2t_live_secret_admin_key_99999"
    admin_user = User(
        email="admin@tchap.gouv.fr",
        api_key_hash=hash_api_key(raw_key),
        api_key_prefix="s2t_live_sec...",
        is_admin=True,
    )
    await fake_user_repository.save(admin_user)

    account = MatrixAccount(
        name="Test Verification Bot",
        matrix_user_id="@bot:agent.tchap.gouv.fr",
        device_id="s2t_test_device",
        user_id=admin_user.id,
        encrypted_password="enc_password",
        encryption_nonce="nonce12345",
    )
    await fake_matrix_account_repository.save(account)

    fake_client_manager = FakeMatrixClientManager(fake_matrix_messenger)

    app = create_app()
    app.dependency_overrides[get_matrix_client_manager] = lambda: fake_client_manager
    app.dependency_overrides[get_matrix_account_repository] = lambda: fake_matrix_account_repository
    app.dependency_overrides[get_user_repository] = lambda: fake_user_repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Calling /verify without API key -> 401 Unauthorized
        unauth_resp = await client.post(f"/verify/{account.id}")
        assert unauth_resp.status_code == 401

        # 2. Calling with another user's API key -> 404 Not Found (ownership check)
        other_user = User(
            email="other@tchap.gouv.fr",
            api_key_hash=hash_api_key("other_key_secret_123"),
            api_key_prefix="other_key_...",
            is_admin=False,
        )
        await fake_user_repository.save(other_user)
        wrong_owner_resp = await client.post(
            f"/verify/{account.id}",
            headers={"X-API-Key": "other_key_secret_123"},
        )
        assert wrong_owner_resp.status_code == 404
        assert "not found or you do not own it" in wrong_owner_resp.json()["detail"]

        # 3. Calling with the bot owner's API key -> 200 OK
        resp = await client.post(
            f"/verify/{account.id}",
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "emojis_ready"
        assert data["account_id"] == str(account.id)
        assert data["transaction_id"] == "tx_fake_sas_12345"
        assert len(data["emojis"]) == 7
        assert data["emojis"][0]["emoji"] == "🐶"
        assert "🐶" in data["emoji_string"]

        # 4. Calling /verify with query parameter and Bearer Authorization
        resp_query = await client.post(
            f"/verify?bot_uuid={account.id}",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert resp_query.status_code == 200
        assert resp_query.json()["transaction_id"] == "tx_fake_sas_12345"

        # 5. Calling with unknown account ID -> 404
        from uuid import uuid4

        unknown_id = uuid4()
        resp_404 = await client.post(
            f"/verify/{unknown_id}",
            headers={"X-API-Key": raw_key},
        )
        assert resp_404.status_code == 404
