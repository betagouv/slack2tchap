"""Integration tests for FastAPI health and public webhook routes."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from slack2tchap.domain.models import MatrixAccount, WebhookEndpoint
from slack2tchap.interfaces.api.dependencies import (
    get_matrix_account_repository,
    get_matrix_client_manager,
    get_webhook_repository,
)
from slack2tchap.main import create_app
from tests.conftest import (
    FakeMatrixAccountRepository,
    FakeMatrixClientManager,
    FakeMatrixMessenger,
    FakeWebhookRepository,
)


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["details"]["mode"] == "stateless_multi_bot"


@pytest.mark.asyncio
async def test_public_webhook_not_found(
    fake_matrix_messenger: FakeMatrixMessenger,
    fake_webhook_repository: FakeWebhookRepository,
    fake_matrix_account_repository: FakeMatrixAccountRepository,
) -> None:
    fake_client_manager = FakeMatrixClientManager(fake_matrix_messenger)
    app = create_app()
    app.dependency_overrides[get_matrix_client_manager] = lambda: fake_client_manager
    app.dependency_overrides[get_matrix_account_repository] = lambda: fake_matrix_account_repository
    app.dependency_overrides[get_webhook_repository] = lambda: fake_webhook_repository

    random_id = uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/webhook/slack/{random_id}",
            json={"text": "Hello world"},
        )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_public_webhook_slack_and_mattermost_aliases(
    fake_matrix_messenger: FakeMatrixMessenger,
    fake_webhook_repository: FakeWebhookRepository,
    fake_matrix_account_repository: FakeMatrixAccountRepository,
) -> None:
    fake_client_manager = FakeMatrixClientManager(fake_matrix_messenger)
    owner_id = uuid4()
    account = MatrixAccount(
        name="Primary Bot",
        matrix_user_id="@bot:agent.tchap.gouv.fr",
        user_id=owner_id,
    )
    await fake_matrix_account_repository.save(account)

    endpoint = WebhookEndpoint(
        name="Test Room Hook",
        matrix_room_id="!alias_room:agent.tchap.gouv.fr",
        matrix_account_id=account.id,
        user_id=owner_id,
    )
    await fake_webhook_repository.save(endpoint)

    app = create_app()
    app.dependency_overrides[get_matrix_client_manager] = lambda: fake_client_manager
    app.dependency_overrides[get_matrix_account_repository] = lambda: fake_matrix_account_repository
    app.dependency_overrides[get_webhook_repository] = lambda: fake_webhook_repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test /slack/{id} alias
        resp_slack = await client.post(
            f"/slack/{endpoint.id}",
            json={"text": "Short route alert"},
        )
        assert resp_slack.status_code == 200
        assert resp_slack.json()["room_id"] == "!alias_room:agent.tchap.gouv.fr"

        # Test /webhook/mattermost/{id} alias
        resp_mm = await client.post(
            f"/webhook/mattermost/{endpoint.id}",
            json={"text": "Mattermost route alert"},
        )
        assert resp_mm.status_code == 200
        assert resp_mm.json()["room_id"] == "!alias_room:agent.tchap.gouv.fr"

    assert len(fake_matrix_messenger.sent_messages) == 2
