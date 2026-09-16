"""Main entrypoint and ASGI lifespan application for slack2tchap."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from slack2tchap import __version__
from slack2tchap.core.config import Settings, get_settings
from slack2tchap.core.logging import setup_logging
from slack2tchap.infrastructure.database.migrator import run_auto_migrations
from slack2tchap.infrastructure.database.seeder import seed_initial_admin
from slack2tchap.infrastructure.database.session import create_engine_and_sessionmaker
from slack2tchap.infrastructure.matrix.manager import MatrixClientManager
from slack2tchap.infrastructure.security.cipher import AesGcmSecretCipher
from slack2tchap.interfaces.api.routes import router

logger = logging.getLogger("slack2tchap")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage initialization and teardown of external resources (DB, Migrations, Matrix)."""
    settings: Settings = get_settings()
    setup_logging(settings.log_level)

    logger.info(
        "Starting slack2tchap gateway v%s in %s environment (Option A: 100%% Stateless)",
        __version__,
        settings.environment,
    )

    # 1. Initialize Database connection & run automatic migrations
    db_engine, session_maker = create_engine_and_sessionmaker(settings.database_url)
    app.state.db_engine = db_engine
    app.state.db_sessionmaker = session_maker

    try:
        await run_auto_migrations(settings)
    except Exception as exc:
        logger.error("Automatic database migration encountered a fatal issue: %s", exc)
        raise

    # 2. Automatically seed default administrator account on first launch
    try:
        await seed_initial_admin(session_maker, settings)
    except Exception as exc:
        logger.error("Automatic admin seeding failed: %s", exc)
        raise

    # 3. Instantiate stateless multi-bot Matrix client manager
    cipher = AesGcmSecretCipher(settings.secret_encryption_key.get_secret_value())
    client_manager = MatrixClientManager(
        session_maker=session_maker,
        cipher=cipher,
        homeserver=settings.matrix_homeserver,
        auto_join=settings.matrix_auto_join,
    )

    app.state.matrix_client_manager = client_manager
    logger.info("Stateless Matrix client manager initialized.")

    yield

    logger.info("Shutting down slack2tchap gateway...")
    try:
        await client_manager.shutdown()
    except Exception as exc:
        logger.error("Error while closing Matrix clients and persisting stores: %s", exc)

    try:
        await db_engine.dispose()
        logger.info("Database engine connections released.")
    except Exception as exc:
        logger.error("Error while disposing database engine: %s", exc)


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    application = FastAPI(
        title="slack2tchap Webhook Gateway",
        description="Passerelle sécurisée stateless entre webhooks Slack / Mattermost et salons Matrix / Tchap avec support E2EE et persistance PostgreSQL",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )

    application.include_router(router)
    return application


app = create_app()


def run() -> None:
    """CLI / PyInstaller entrypoint."""
    settings = get_settings()
    setup_logging(settings.log_level)
    uvicorn.run(
        "slack2tchap.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    run()
