"""Integration tests for SQLAlchemy repositories against an async SQLite database."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slack2tchap.domain.models import MatrixAccount, User, WebhookEndpoint
from slack2tchap.infrastructure.database.models import Base
from slack2tchap.infrastructure.repositories.matrix_account_repository import (
    SqlAlchemyMatrixAccountRepository,
)
from slack2tchap.infrastructure.repositories.user_repository import SqlAlchemyUserRepository
from slack2tchap.infrastructure.repositories.webhook_repository import SqlAlchemyWebhookRepository
from slack2tchap.infrastructure.security.api_key import hash_api_key


@pytest.fixture
async def async_db_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield session_maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_repository_crud(async_db_sessionmaker) -> None:
    raw_key = "s2t_live_test_user_key_12345"
    key_hash = hash_api_key(raw_key)

    async with async_db_sessionmaker() as session:
        repo = SqlAlchemyUserRepository(session)

        # 1. Create user
        user = User(
            email="developer@tchap.gouv.fr",
            api_key_hash=key_hash,
            api_key_prefix="s2t_live_tes...",
            is_admin=False,
            is_active=True,
        )
        saved = await repo.save(user)
        await session.commit()
        assert saved.id == user.id

    async with async_db_sessionmaker() as session:
        repo = SqlAlchemyUserRepository(session)

        # 2. Retrieve by ID
        by_id = await repo.get_by_id(user.id)
        assert by_id is not None
        assert by_id.email == "developer@tchap.gouv.fr"

        # 3. Retrieve by email (case-insensitive)
        by_email = await repo.get_by_email("DEVELOPER@tchap.gouv.fr")
        assert by_email is not None
        assert by_email.id == user.id

        # 4. Retrieve by API key hash
        by_hash = await repo.get_by_api_key_hash(key_hash)
        assert by_hash is not None
        assert by_hash.id == user.id

        # 5. Non-existent returns None
        assert await repo.get_by_id(uuid4()) is None
        assert await repo.get_by_email("unknown@tchap.gouv.fr") is None
        assert await repo.get_by_api_key_hash("invalid_hash") is None

        # 6. Update user
        by_id.is_admin = True
        by_id.email = "updated@tchap.gouv.fr"
        await repo.save(by_id)
        await session.commit()

    async with async_db_sessionmaker() as session:
        repo = SqlAlchemyUserRepository(session)
        updated = await repo.get_by_id(user.id)
        assert updated is not None
        assert updated.is_admin is True
        assert updated.email == "updated@tchap.gouv.fr"


@pytest.mark.asyncio
async def test_matrix_account_repository_crud(async_db_sessionmaker) -> None:
    # Seed user first (foreign key requirement)
    async with async_db_sessionmaker() as session:
        user_repo = SqlAlchemyUserRepository(session)
        user = User(
            email="botowner@tchap.gouv.fr",
            api_key_hash=hash_api_key("bot_owner_key_123"),
            api_key_prefix="bot_owner...",
        )
        await user_repo.save(user)
        await session.commit()

    async with async_db_sessionmaker() as session:
        account_repo = SqlAlchemyMatrixAccountRepository(session)

        # 1. Save MatrixAccount
        account = MatrixAccount(
            name="Monitoring Bot",
            matrix_user_id="@monitoring:agent.tchap.gouv.fr",
            user_id=user.id,
            encrypted_password="enc_password_xyz",
            encryption_nonce="nonce_123",
            is_active=True,
        )
        saved = await account_repo.save(account)
        await session.commit()
        assert saved.id == account.id

    async with async_db_sessionmaker() as session:
        account_repo = SqlAlchemyMatrixAccountRepository(session)

        # 2. Get by ID and matrix_user_id
        by_id = await account_repo.get_by_id(account.id)
        assert by_id is not None
        assert by_id.name == "Monitoring Bot"

        by_uid = await account_repo.get_by_matrix_user_id("@monitoring:agent.tchap.gouv.fr")
        assert by_uid is not None
        assert by_uid.id == account.id

        # 3. List by user_id and list_all_active
        user_accounts = await account_repo.list_by_user_id(user.id)
        assert len(user_accounts) == 1
        assert user_accounts[0].id == account.id

        active_accounts = await account_repo.list_all_active()
        assert len(active_accounts) == 1

        # 4. Save and read crypto store blob
        test_blob = b"fake_tar_gz_sqlite_crypto_store_blob_content"
        await account_repo.save_crypto_store(account.id, test_blob)
        await session.commit()

    async with async_db_sessionmaker() as session:
        account_repo = SqlAlchemyMatrixAccountRepository(session)
        with_blob = await account_repo.get_by_id(account.id)
        assert with_blob is not None
        assert with_blob.crypto_store_blob == test_blob
        assert with_blob.crypto_store_updated_at is not None

        # 5. Delete account
        deleted = await account_repo.delete(account.id)
        assert deleted is True
        await session.commit()

        # Non-existent delete returns False
        assert await account_repo.delete(account.id) is False


@pytest.mark.asyncio
async def test_webhook_repository_crud(async_db_sessionmaker) -> None:
    # Seed user and matrix account
    async with async_db_sessionmaker() as session:
        user_repo = SqlAlchemyUserRepository(session)
        user = User(
            email="webhookowner@tchap.gouv.fr",
            api_key_hash=hash_api_key("hook_key_123"),
            api_key_prefix="hook_key...",
        )
        await user_repo.save(user)

        account_repo = SqlAlchemyMatrixAccountRepository(session)
        account = MatrixAccount(
            name="Dispatch Bot",
            matrix_user_id="@dispatch:agent.tchap.gouv.fr",
            user_id=user.id,
        )
        await account_repo.save(account)
        await session.commit()

    async with async_db_sessionmaker() as session:
        hook_repo = SqlAlchemyWebhookRepository(session)

        # 1. Save Webhook
        webhook = WebhookEndpoint(
            name="Grafana Alerts",
            matrix_room_id="!grafana_room:agent.tchap.gouv.fr",
            matrix_account_id=account.id,
            user_id=user.id,
        )
        saved = await hook_repo.save(webhook)
        await session.commit()
        assert saved.id == webhook.id

    async with async_db_sessionmaker() as session:
        hook_repo = SqlAlchemyWebhookRepository(session)

        # 2. Get by ID
        by_id = await hook_repo.get_by_id(webhook.id)
        assert by_id is not None
        assert by_id.name == "Grafana Alerts"
        assert by_id.matrix_room_id == "!grafana_room:agent.tchap.gouv.fr"

        # 3. List by user_id
        hooks = await hook_repo.list_by_user_id(user.id)
        assert len(hooks) == 1
        assert hooks[0].id == webhook.id

        # 4. Update webhook
        by_id.name = "Grafana Alerts Renamed"
        by_id.is_active = False
        await hook_repo.save(by_id)
        await session.commit()

    async with async_db_sessionmaker() as session:
        hook_repo = SqlAlchemyWebhookRepository(session)
        updated = await hook_repo.get_by_id(webhook.id)
        assert updated is not None
        assert updated.name == "Grafana Alerts Renamed"
        assert updated.is_active is False

        # 5. Delete webhook
        deleted = await hook_repo.delete(webhook.id)
        assert deleted is True
        await session.commit()

        assert await hook_repo.delete(webhook.id) is False
        assert await hook_repo.get_by_id(webhook.id) is None
