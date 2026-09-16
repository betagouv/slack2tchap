"""Comprehensive access control tests for admin-only routes and per-user isolation."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from slack2tchap.application.dtos import CreateUserCommand
from slack2tchap.application.use_cases import CreateUserUseCase
from slack2tchap.domain.exceptions import UserAlreadyExistsError
from slack2tchap.domain.models import MatrixAccount, User, WebhookEndpoint
from slack2tchap.infrastructure.security.api_key import hash_api_key
from slack2tchap.interfaces.api.dependencies import (
    get_matrix_account_repository,
    get_matrix_client_manager,
    get_user_repository,
    get_webhook_repository,
)
from slack2tchap.main import create_app
from tests.conftest import (
    FakeMatrixAccountRepository,
    FakeMatrixClientManager,
    FakeMatrixMessenger,
    FakeUserRepository,
    FakeWebhookRepository,
)

# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

ADMIN_RAW_KEY = "s2t_live_admin_test_key_access_ctrl"
USER_A_RAW_KEY = "s2t_live_user_a_key_access_ctrl"
USER_B_RAW_KEY = "s2t_live_user_b_key_access_ctrl"


def _make_admin(repo: FakeUserRepository) -> User:
    admin = User(
        email="admin@tchap.gouv.fr",
        api_key_hash=hash_api_key(ADMIN_RAW_KEY),
        api_key_prefix="s2t_live_admi...",
        is_admin=True,
    )
    repo.users_by_id[admin.id] = admin
    return admin


def _make_user(repo: FakeUserRepository, email: str, raw_key: str) -> User:
    user = User(
        email=email,
        api_key_hash=hash_api_key(raw_key),
        api_key_prefix=raw_key[:16] + "...",
        is_admin=False,
    )
    repo.users_by_id[user.id] = user
    return user


def _make_app(
    user_repo: FakeUserRepository,
    account_repo: FakeMatrixAccountRepository,
    webhook_repo: FakeWebhookRepository,
    messenger: FakeMatrixMessenger | None = None,
) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: user_repo
    app.dependency_overrides[get_matrix_account_repository] = lambda: account_repo
    app.dependency_overrides[get_webhook_repository] = lambda: webhook_repo
    if messenger is not None:
        mgr = FakeMatrixClientManager(messenger)
        app.dependency_overrides[get_matrix_client_manager] = lambda: mgr
    return app


# ===========================================================================
# 1. ADMIN-ONLY USER CREATION ROUTE
# ===========================================================================


@pytest.mark.asyncio
async def test_admin_creates_user_returns_201_with_api_key() -> None:
    """Admin can create a user and receives the one-time raw API key."""
    user_repo = FakeUserRepository()
    _make_admin(user_repo)
    app = _make_app(user_repo, FakeMatrixAccountRepository(), FakeWebhookRepository())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/admin/users",
            headers={"X-API-Key": ADMIN_RAW_KEY},
            json={"email": "newuser@beta.gouv.fr"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@beta.gouv.fr"
    assert data["is_admin"] is False
    assert data["is_active"] is True
    assert data["raw_api_key"].startswith("s2t_live_")
    assert data["api_key_prefix"].endswith("...")
    assert data["id"]
    assert data["created_at"]


@pytest.mark.asyncio
async def test_non_admin_cannot_create_user_returns_403() -> None:
    """A regular user (non-admin) receives 403 Forbidden."""
    user_repo = FakeUserRepository()
    _make_admin(user_repo)
    user_a = _make_user(user_repo, "usera@beta.gouv.fr", USER_A_RAW_KEY)
    assert not user_a.is_admin

    app = _make_app(user_repo, FakeMatrixAccountRepository(), FakeWebhookRepository())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/admin/users",
            headers={"X-API-Key": USER_A_RAW_KEY},
            json={"email": "another@beta.gouv.fr"},
        )

    assert resp.status_code == 403
    assert "Admin privileges required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unauthenticated_cannot_create_user_returns_401() -> None:
    """No API key at all → 401 Unauthorized."""
    app = _make_app(FakeUserRepository(), FakeMatrixAccountRepository(), FakeWebhookRepository())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/admin/users",
            json={"email": "nope@beta.gouv.fr"},
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_cannot_create_duplicate_user_returns_409() -> None:
    """Creating a user with an existing email returns 409 Conflict."""
    user_repo = FakeUserRepository()
    _make_admin(user_repo)
    _make_user(user_repo, "existing@beta.gouv.fr", "s2t_live_existing_key")

    app = _make_app(user_repo, FakeMatrixAccountRepository(), FakeWebhookRepository())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/admin/users",
            headers={"X-API-Key": ADMIN_RAW_KEY},
            json={"email": "existing@beta.gouv.fr"},
        )

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_created_user_can_authenticate_with_returned_key() -> None:
    """The API key returned at creation time is usable for authentication."""
    user_repo = FakeUserRepository()
    _make_admin(user_repo)
    app = _make_app(user_repo, FakeMatrixAccountRepository(), FakeWebhookRepository())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user
        create_resp = await client.post(
            "/api/v1/admin/users",
            headers={"X-API-Key": ADMIN_RAW_KEY},
            json={"email": "newguy@beta.gouv.fr"},
        )
        assert create_resp.status_code == 201
        new_key = create_resp.json()["raw_api_key"]

        # Authenticate with the returned key to list matrix accounts (empty list)
        list_resp = await client.get(
            "/api/v1/admin/matrix-accounts",
            headers={"X-API-Key": new_key},
        )
        assert list_resp.status_code == 200
        assert list_resp.json() == []


# ===========================================================================
# 2. CROSS-USER ISOLATION: MATRIX BOT ACCOUNTS
# ===========================================================================


@pytest.mark.asyncio
async def test_user_cannot_list_other_users_bots() -> None:
    """User A cannot see User B's Matrix bot accounts."""
    user_repo = FakeUserRepository()
    account_repo = FakeMatrixAccountRepository()
    _make_user(user_repo, "a@beta.gouv.fr", USER_A_RAW_KEY)
    user_b = _make_user(user_repo, "b@beta.gouv.fr", USER_B_RAW_KEY)

    # Create an account owned by User B
    bot_b = MatrixAccount(
        name="Bot B",
        matrix_user_id="@bot-b:agent.tchap.gouv.fr",
        user_id=user_b.id,
    )
    await account_repo.save(bot_b)

    app = _make_app(user_repo, account_repo, FakeWebhookRepository())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User A lists accounts → should see empty list
        resp_a = await client.get(
            "/api/v1/admin/matrix-accounts",
            headers={"X-API-Key": USER_A_RAW_KEY},
        )
        assert resp_a.status_code == 200
        assert resp_a.json() == []

        # User B lists accounts → should see their bot
        resp_b = await client.get(
            "/api/v1/admin/matrix-accounts",
            headers={"X-API-Key": USER_B_RAW_KEY},
        )
        assert resp_b.status_code == 200
        assert len(resp_b.json()) == 1
        assert resp_b.json()[0]["id"] == str(bot_b.id)


@pytest.mark.asyncio
async def test_user_cannot_delete_other_users_bot() -> None:
    """User A cannot delete User B's bot → 404."""
    user_repo = FakeUserRepository()
    account_repo = FakeMatrixAccountRepository()
    _make_user(user_repo, "a@beta.gouv.fr", USER_A_RAW_KEY)
    user_b = _make_user(user_repo, "b@beta.gouv.fr", USER_B_RAW_KEY)

    bot_b = MatrixAccount(
        name="Bot B",
        matrix_user_id="@bot-b:agent.tchap.gouv.fr",
        user_id=user_b.id,
    )
    await account_repo.save(bot_b)

    app = _make_app(user_repo, account_repo, FakeWebhookRepository())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User A tries to delete Bot B → 404
        resp = await client.delete(
            f"/api/v1/admin/matrix-accounts/{bot_b.id}",
            headers={"X-API-Key": USER_A_RAW_KEY},
        )
        assert resp.status_code == 404

        # Bot B still exists
        assert await account_repo.get_by_id(bot_b.id) is not None


# ===========================================================================
# 3. CROSS-USER ISOLATION: WEBHOOKS
# ===========================================================================


@pytest.mark.asyncio
async def test_user_cannot_list_other_users_webhooks() -> None:
    """User A cannot see User B's webhooks."""
    user_repo = FakeUserRepository()
    webhook_repo = FakeWebhookRepository()
    _make_user(user_repo, "a@beta.gouv.fr", USER_A_RAW_KEY)
    user_b = _make_user(user_repo, "b@beta.gouv.fr", USER_B_RAW_KEY)

    webhook_b = WebhookEndpoint(
        name="Webhook B",
        matrix_room_id="!room_b:agent.tchap.gouv.fr",
        matrix_account_id=uuid4(),
        user_id=user_b.id,
    )
    await webhook_repo.save(webhook_b)

    app = _make_app(user_repo, FakeMatrixAccountRepository(), webhook_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_a = await client.get(
            "/api/v1/admin/webhooks",
            headers={"X-API-Key": USER_A_RAW_KEY},
        )
        assert resp_a.status_code == 200
        assert resp_a.json() == []

        resp_b = await client.get(
            "/api/v1/admin/webhooks",
            headers={"X-API-Key": USER_B_RAW_KEY},
        )
        assert resp_b.status_code == 200
        assert len(resp_b.json()) == 1


@pytest.mark.asyncio
async def test_user_cannot_delete_other_users_webhook() -> None:
    """User A cannot delete User B's webhook → 404."""
    user_repo = FakeUserRepository()
    webhook_repo = FakeWebhookRepository()
    _make_user(user_repo, "a@beta.gouv.fr", USER_A_RAW_KEY)
    user_b = _make_user(user_repo, "b@beta.gouv.fr", USER_B_RAW_KEY)

    webhook_b = WebhookEndpoint(
        name="Webhook B",
        matrix_room_id="!room_b:agent.tchap.gouv.fr",
        matrix_account_id=uuid4(),
        user_id=user_b.id,
    )
    await webhook_repo.save(webhook_b)

    app = _make_app(user_repo, FakeMatrixAccountRepository(), webhook_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete(
            f"/api/v1/admin/webhooks/{webhook_b.id}",
            headers={"X-API-Key": USER_A_RAW_KEY},
        )
        assert resp.status_code == 404

        # Webhook still exists
        assert await webhook_repo.get_by_id(webhook_b.id) is not None


@pytest.mark.asyncio
async def test_user_cannot_create_webhook_with_other_users_bot() -> None:
    """User A cannot create a webhook referencing User B's bot → 422."""
    user_repo = FakeUserRepository()
    account_repo = FakeMatrixAccountRepository()
    webhook_repo = FakeWebhookRepository()
    _make_user(user_repo, "a@beta.gouv.fr", USER_A_RAW_KEY)
    user_b = _make_user(user_repo, "b@beta.gouv.fr", USER_B_RAW_KEY)

    bot_b = MatrixAccount(
        name="Bot B",
        matrix_user_id="@bot-b:agent.tchap.gouv.fr",
        user_id=user_b.id,
    )
    await account_repo.save(bot_b)

    app = _make_app(user_repo, account_repo, webhook_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/admin/webhooks",
            headers={"X-API-Key": USER_A_RAW_KEY},
            json={
                "name": "Sneaky Webhook",
                "matrix_room_id": "!room:agent.tchap.gouv.fr",
                "matrix_account_id": str(bot_b.id),
            },
        )
        assert resp.status_code == 422
        assert "not found or not active" in resp.json()["detail"]


# ===========================================================================
# 4. CROSS-USER ISOLATION: BOT VERIFICATION
# ===========================================================================


@pytest.mark.asyncio
async def test_user_cannot_verify_other_users_bot() -> None:
    """User A cannot trigger verification on User B's bot → 404."""
    user_repo = FakeUserRepository()
    account_repo = FakeMatrixAccountRepository()
    messenger = FakeMatrixMessenger()
    _make_user(user_repo, "a@beta.gouv.fr", USER_A_RAW_KEY)
    user_b = _make_user(user_repo, "b@beta.gouv.fr", USER_B_RAW_KEY)

    bot_b = MatrixAccount(
        name="Bot B",
        matrix_user_id="@bot-b:agent.tchap.gouv.fr",
        user_id=user_b.id,
    )
    await account_repo.save(bot_b)

    app = _make_app(user_repo, account_repo, FakeWebhookRepository(), messenger)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/matrix-accounts/{bot_b.id}/verify",
            headers={"X-API-Key": USER_A_RAW_KEY},
        )
        assert resp.status_code == 404
        assert "not found or you do not own it" in resp.json()["detail"]


# ===========================================================================
# 5. UNIT TESTS: CreateUserUseCase
# ===========================================================================


@pytest.mark.asyncio
async def test_create_user_use_case_generates_api_key() -> None:
    """CreateUserUseCase returns a UserCreatedDTO with a valid API key."""
    user_repo = FakeUserRepository()
    use_case = CreateUserUseCase(user_repo=user_repo)

    dto = await use_case.execute(CreateUserCommand(email="test@beta.gouv.fr"))

    assert dto.email == "test@beta.gouv.fr"
    assert dto.raw_api_key.startswith("s2t_live_")
    assert len(dto.raw_api_key) > 20
    assert dto.api_key_prefix.endswith("...")
    assert dto.is_admin is False
    assert dto.is_active is True

    # Verify the user is persisted with correct hash
    saved_user = await user_repo.get_by_id(dto.id)
    assert saved_user is not None
    assert saved_user.email == "test@beta.gouv.fr"


@pytest.mark.asyncio
async def test_create_user_use_case_rejects_duplicate_email() -> None:
    """CreateUserUseCase raises UserAlreadyExistsError for duplicate email."""
    user_repo = FakeUserRepository()
    use_case = CreateUserUseCase(user_repo=user_repo)

    await use_case.execute(CreateUserCommand(email="dup@beta.gouv.fr"))

    with pytest.raises(UserAlreadyExistsError, match="already exists"):
        await use_case.execute(CreateUserCommand(email="dup@beta.gouv.fr"))


@pytest.mark.asyncio
async def test_create_user_use_case_normalizes_email() -> None:
    """CreateUserUseCase lowercases and strips email."""
    user_repo = FakeUserRepository()
    use_case = CreateUserUseCase(user_repo=user_repo)

    dto = await use_case.execute(CreateUserCommand(email="  Admin@Beta.Gouv.FR  "))
    assert dto.email == "admin@beta.gouv.fr"


@pytest.mark.asyncio
async def test_create_user_use_case_generates_unique_keys() -> None:
    """Two users get different API keys."""
    user_repo = FakeUserRepository()
    use_case = CreateUserUseCase(user_repo=user_repo)

    dto1 = await use_case.execute(CreateUserCommand(email="user1@beta.gouv.fr"))
    dto2 = await use_case.execute(CreateUserCommand(email="user2@beta.gouv.fr"))

    assert dto1.raw_api_key != dto2.raw_api_key
    assert dto1.id != dto2.id
