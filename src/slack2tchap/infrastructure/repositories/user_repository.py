"""SQLAlchemy implementation of UserRepositoryPort."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slack2tchap.domain.models import User
from slack2tchap.domain.ports import UserRepositoryPort
from slack2tchap.infrastructure.database.models import UserModel


class SqlAlchemyUserRepository(UserRepositoryPort):
    """Repository managing User entities using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, model: UserModel) -> User:
        return User(
            id=model.id,
            email=model.email,
            api_key_hash=model.api_key_hash,
            api_key_prefix=model.api_key_prefix,
            is_admin=model.is_admin,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email.strip().lower())
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_api_key_hash(self, key_hash: str) -> User | None:
        stmt = select(UserModel).where(UserModel.api_key_hash == key_hash)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def save(self, user: User) -> User:
        model = await self._session.get(UserModel, user.id)
        if model is None:
            model = UserModel(
                id=user.id,
                email=user.email.strip().lower(),
                api_key_hash=user.api_key_hash,
                api_key_prefix=user.api_key_prefix,
                is_admin=user.is_admin,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
            self._session.add(model)
        else:
            model.email = user.email.strip().lower()
            model.api_key_hash = user.api_key_hash
            model.api_key_prefix = user.api_key_prefix
            model.is_admin = user.is_admin
            model.is_active = user.is_active
            model.updated_at = user.updated_at

        await self._session.flush()
        return self._to_domain(model)

    async def delete(self, user_id: UUID) -> bool:
        model = await self._session.get(UserModel, user_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True
