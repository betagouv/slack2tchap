"""SQLAlchemy implementation of WebhookRepositoryPort."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slack2tchap.domain.models import WebhookEndpoint
from slack2tchap.domain.ports import WebhookRepositoryPort
from slack2tchap.infrastructure.database.models import WebhookModel


class SqlAlchemyWebhookRepository(WebhookRepositoryPort):
    """Repository managing WebhookEndpoint entities using SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, model: WebhookModel) -> WebhookEndpoint:
        return WebhookEndpoint(
            id=model.id,
            name=model.name,
            matrix_room_id=model.matrix_room_id,
            matrix_account_id=model.matrix_account_id,
            user_id=model.user_id,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def get_by_id(self, webhook_id: UUID) -> WebhookEndpoint | None:
        stmt = select(WebhookModel).where(WebhookModel.id == webhook_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_user_id(self, user_id: UUID) -> list[WebhookEndpoint]:
        stmt = (
            select(WebhookModel)
            .where(WebhookModel.user_id == user_id)
            .order_by(WebhookModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def save(self, webhook: WebhookEndpoint) -> WebhookEndpoint:
        model = await self._session.get(WebhookModel, webhook.id)

        if model is None:
            model = WebhookModel(
                id=webhook.id,
                name=webhook.name,
                matrix_room_id=webhook.matrix_room_id,
                matrix_account_id=webhook.matrix_account_id,
                user_id=webhook.user_id,
                is_active=webhook.is_active,
                created_at=webhook.created_at,
                updated_at=webhook.updated_at,
            )
            self._session.add(model)
        else:
            model.name = webhook.name
            model.matrix_room_id = webhook.matrix_room_id
            model.matrix_account_id = webhook.matrix_account_id
            model.is_active = webhook.is_active
            model.updated_at = webhook.updated_at

        await self._session.flush()
        return self._to_domain(model)

    async def delete(self, webhook_id: UUID) -> bool:
        model = await self._session.get(WebhookModel, webhook_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True
