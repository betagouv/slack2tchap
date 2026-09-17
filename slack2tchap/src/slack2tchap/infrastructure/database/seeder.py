"""Automatic seeder for the default administrator account on first application launch."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slack2tchap.core.config import Settings
from slack2tchap.infrastructure.database.models import UserModel
from slack2tchap.infrastructure.security.api_key import extract_api_key_prefix, hash_api_key

logger = logging.getLogger(__name__)


async def seed_initial_admin(
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> bool:
    """Seed initial default administrator if configured and not already present in database.

    Returns True if an admin was created, False otherwise.
    """
    if not settings.admin_email or not settings.admin_api_key:
        logger.debug(
            "No default admin configured in settings (admin_email or admin_api_key missing); skipping seeding."
        )
        return False

    raw_key = settings.admin_api_key.get_secret_value().strip()
    if not raw_key:
        return False

    admin_email = settings.admin_email.strip().lower()
    key_hash = hash_api_key(raw_key)
    key_prefix = extract_api_key_prefix(raw_key, length=12)

    async with session_maker() as session:
        stmt = select(UserModel).where(
            (UserModel.email == admin_email) | (UserModel.api_key_hash == key_hash)
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            logger.info("Default administrator (%s) already exists; skipping seeding.", admin_email)
            return False

        logger.info("Seeding initial default administrator (%s)...", admin_email)
        admin_user = UserModel(
            email=admin_email,
            api_key_hash=key_hash,
            api_key_prefix=key_prefix,
            is_admin=True,
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()
        logger.info("Initial administrator (%s) successfully seeded.", admin_email)
        return True
