"""Programmatic migration runner executing Alembic upgrade head on startup."""

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from slack2tchap.core.config import Settings
from slack2tchap.core.logging import setup_logging

logger = logging.getLogger(__name__)


def find_alembic_ini() -> Path | None:
    """Find alembic.ini either from repository root or current working directory."""
    # migrator.py is in src/slack2tchap/infrastructure/database/ (5 levels below repo root)
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    candidate_1 = repo_root / "alembic.ini"
    if candidate_1.exists():
        return candidate_1

    candidate_2 = Path.cwd() / "alembic.ini"
    if candidate_2.exists():
        return candidate_2

    return None


def apply_migrations(settings: Settings) -> None:
    """Run Alembic migrations synchronously to upgrade schema to head."""
    alembic_ini_path = find_alembic_ini()

    if alembic_ini_path is None or not alembic_ini_path.exists():
        logger.warning(
            "alembic.ini not found in project root or current directory; skipping auto-migration"
        )
        return

    logger.info("Executing automatic database migrations (alembic upgrade head)...")
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.attributes["configure_logger"] = False
    alembic_cfg.set_main_option("script_location", str(alembic_ini_path.parent / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    try:
        command.upgrade(alembic_cfg, "head")
    except Exception as exc:
        logger.error("Failed to apply automatic database migrations: %s", exc)
        raise
    finally:
        setup_logging(settings.log_level)

    logger.info("Database migrations successfully applied.")


async def run_auto_migrations(settings: Settings) -> None:
    """Asynchronous wrapper running migrations in an executor."""
    await asyncio.to_thread(apply_migrations, settings)
