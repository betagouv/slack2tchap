"""Main entrypoint and ASGI lifespan application for slack2tchap-stateless."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from slack2tchap_stateless import __version__
from slack2tchap_stateless.core.config import Settings, get_settings
from slack2tchap_stateless.core.logging import setup_logging
from slack2tchap_stateless.interfaces.api.routes import router

logger = logging.getLogger("slack2tchap_stateless")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage initialization and teardown of stateless microservice."""
    settings: Settings = get_settings()
    setup_logging(settings.log_level)

    logger.info(
        "Starting slack2tchap-stateless gateway v%s in %s mode (zero database)",
        __version__,
        settings.environment,
    )
    yield
    logger.info("Shutting down slack2tchap-stateless gateway...")


def create_app() -> FastAPI:
    """Application factory for slack2tchap-stateless."""
    settings = get_settings()

    application = FastAPI(
        title="slack2tchap Stateless Webhook Gateway",
        description="Passerelle webhook 100% Stateless Slack vers Matrix / Tchap sans base de données",
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
        "slack2tchap_stateless.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    run()
