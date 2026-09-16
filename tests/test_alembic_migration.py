"""Integration test for Alembic migration execution and admin seeding."""

import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slack2tchap.core.config import Settings
from slack2tchap.infrastructure.database.seeder import seed_initial_admin
from slack2tchap.infrastructure.security.api_key import hash_api_key


def test_alembic_schema_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    # Use temporary sqlite database for migration test
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
        sqlite_url = f"sqlite:///{tmp_db.name}"

        monkeypatch.setenv("DATABASE_URL", sqlite_url)

        from slack2tchap.core.config import get_settings

        get_settings.cache_clear()

        project_root = Path(__file__).resolve().parent.parent
        alembic_ini_path = project_root / "alembic.ini"

        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)

        # Run migration
        command.upgrade(alembic_cfg, "head")

        # Verify tables in SQLite database
        engine = create_engine(sqlite_url)
        with engine.connect() as conn:
            tables = (
                conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                .scalars()
                .all()
            )
            assert "users" in tables
            assert "matrix_accounts" in tables
            assert "webhooks" in tables
        engine.dispose()


@pytest.mark.asyncio
async def test_seed_initial_admin_on_first_launch() -> None:
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    from slack2tchap.infrastructure.database.models import Base

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    raw_admin_key = "s2t_live_test_admin_key_for_migration_seed_12345"
    admin_email = "superadmin@tchap.gouv.fr"

    settings = Settings(
        admin_email=admin_email,
        admin_api_key=raw_admin_key,  # type: ignore[arg-type]
    )

    # First launch: should seed
    created = await seed_initial_admin(session_maker, settings)
    assert created is True

    # Check user in DB
    async with session_maker() as session:
        result = await session.execute(
            text(
                "SELECT email, api_key_hash, api_key_prefix, is_admin FROM users WHERE email = :email"
            ),
            {"email": admin_email},
        )
        user_row = result.fetchone()
        assert user_row is not None
        assert user_row[0] == admin_email
        assert user_row[1] == hash_api_key(raw_admin_key)
        assert user_row[3] == 1

    # Second launch (idempotent): should NOT duplicate or fail
    second_created = await seed_initial_admin(session_maker, settings)
    assert second_created is False

    await async_engine.dispose()
