"""SQLAlchemy implementation of MatrixAccountRepositoryPort."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slack2tchap.domain.models import MatrixAccount
from slack2tchap.domain.ports import MatrixAccountRepositoryPort
from slack2tchap.infrastructure.database.models import MatrixAccountModel


class SqlAlchemyMatrixAccountRepository(MatrixAccountRepositoryPort):
    """Repository managing Matrix bot account entities and their persisted E2EE state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, model: MatrixAccountModel) -> MatrixAccount:
        return MatrixAccount(
            id=model.id,
            name=model.name,
            matrix_user_id=model.matrix_user_id,
            device_id=model.device_id,
            user_id=model.user_id,
            encrypted_password=model.encrypted_password,
            encrypted_access_token=model.encrypted_access_token,
            encryption_nonce=model.encryption_nonce,
            crypto_store_blob=model.crypto_store_blob,
            crypto_store_updated_at=model.crypto_store_updated_at,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def get_by_id(self, account_id: UUID) -> MatrixAccount | None:
        stmt = select(MatrixAccountModel).where(MatrixAccountModel.id == account_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_matrix_user_id(self, matrix_user_id: str) -> MatrixAccount | None:
        stmt = select(MatrixAccountModel).where(
            MatrixAccountModel.matrix_user_id == matrix_user_id.strip()
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_user_id(self, user_id: UUID) -> list[MatrixAccount]:
        stmt = (
            select(MatrixAccountModel)
            .where(MatrixAccountModel.user_id == user_id)
            .order_by(MatrixAccountModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def list_all_active(self) -> list[MatrixAccount]:
        stmt = (
            select(MatrixAccountModel)
            .where(MatrixAccountModel.is_active.is_(True))
            .order_by(MatrixAccountModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def save(self, account: MatrixAccount) -> MatrixAccount:
        model = await self._session.get(MatrixAccountModel, account.id)
        if model is None:
            model = MatrixAccountModel(
                id=account.id,
                name=account.name,
                matrix_user_id=account.matrix_user_id.strip(),
                device_id=account.device_id,
                user_id=account.user_id,
                encrypted_password=account.encrypted_password,
                encrypted_access_token=account.encrypted_access_token,
                encryption_nonce=account.encryption_nonce,
                crypto_store_blob=account.crypto_store_blob,
                crypto_store_updated_at=account.crypto_store_updated_at,
                is_active=account.is_active,
                created_at=account.created_at,
                updated_at=account.updated_at,
            )
            self._session.add(model)
        else:
            model.name = account.name
            model.matrix_user_id = account.matrix_user_id.strip()
            model.device_id = account.device_id
            model.encrypted_password = account.encrypted_password
            model.encrypted_access_token = account.encrypted_access_token
            model.encryption_nonce = account.encryption_nonce
            model.crypto_store_blob = account.crypto_store_blob
            model.crypto_store_updated_at = account.crypto_store_updated_at
            model.is_active = account.is_active
            model.updated_at = account.updated_at

        await self._session.flush()
        return self._to_domain(model)

    async def save_crypto_store(self, account_id: UUID, store_blob: bytes) -> None:
        model = await self._session.get(MatrixAccountModel, account_id)
        if model is not None:
            model.crypto_store_blob = store_blob
            model.crypto_store_updated_at = datetime.now(UTC)
            await self._session.flush()

    async def delete(self, account_id: UUID) -> bool:
        model = await self._session.get(MatrixAccountModel, account_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True
