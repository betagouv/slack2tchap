"""FastAPI dependency injection providers."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from slack2tchap.application.use_cases import (
    AuthenticateApiKeyUseCase,
    CreateUserUseCase,
    CreateWebhookUseCase,
    DeleteMatrixAccountUseCase,
    DeleteWebhookUseCase,
    ListMatrixAccountsUseCase,
    ListWebhooksUseCase,
    ProcessPublicWebhookUseCase,
    RegisterMatrixAccountUseCase,
    RequestDeviceVerificationUseCase,
)
from slack2tchap.core.config import Settings, get_settings
from slack2tchap.domain.exceptions import InvalidApiKeyError
from slack2tchap.domain.models import User
from slack2tchap.domain.ports import (
    MatrixAccountRepositoryPort,
    SecretCipherPort,
    UserRepositoryPort,
    WebhookRepositoryPort,
)
from slack2tchap.infrastructure.matrix.manager import MatrixClientManager
from slack2tchap.infrastructure.repositories.matrix_account_repository import (
    SqlAlchemyMatrixAccountRepository,
)
from slack2tchap.infrastructure.repositories.user_repository import SqlAlchemyUserRepository
from slack2tchap.infrastructure.repositories.webhook_repository import SqlAlchemyWebhookRepository
from slack2tchap.infrastructure.security.cipher import AesGcmSecretCipher


def get_matrix_client_manager(request: Request) -> MatrixClientManager:
    """Retrieve initialized MatrixClientManager from application state."""
    manager = getattr(request.app.state, "matrix_client_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Matrix client manager is not initialized",
        )
    return manager  # type: ignore[no-any-return]


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session per request."""
    session_maker = getattr(request.app.state, "db_sessionmaker", None)
    if session_maker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not initialized",
        )
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRepositoryPort:
    return SqlAlchemyUserRepository(session)


def get_matrix_account_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MatrixAccountRepositoryPort:
    return SqlAlchemyMatrixAccountRepository(session)


def get_webhook_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WebhookRepositoryPort:
    return SqlAlchemyWebhookRepository(session)


def get_cipher(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SecretCipherPort:
    return AesGcmSecretCipher(settings.secret_encryption_key.get_secret_value())


async def get_current_user(
    user_repo: Annotated[UserRepositoryPort, Depends(get_user_repository)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> User:
    """Authenticate incoming request using API Key (X-API-Key or Bearer token)."""
    raw_key: str | None = None

    if x_api_key and x_api_key.strip():
        raw_key = x_api_key.strip()
    elif authorization and authorization.startswith("Bearer "):
        raw_key = authorization.removeprefix("Bearer ").strip()

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key in X-API-Key or Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_use_case = AuthenticateApiKeyUseCase(user_repo)
    try:
        return await auth_use_case.execute(raw_key)
    except InvalidApiKeyError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from err


async def get_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure authenticated user has admin privileges, raising 403 otherwise."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return current_user


def get_create_user_use_case(
    user_repo: Annotated[UserRepositoryPort, Depends(get_user_repository)],
) -> CreateUserUseCase:
    return CreateUserUseCase(user_repo=user_repo)


def get_register_matrix_account_use_case(
    account_repo: Annotated[MatrixAccountRepositoryPort, Depends(get_matrix_account_repository)],
    cipher: Annotated[SecretCipherPort, Depends(get_cipher)],
) -> RegisterMatrixAccountUseCase:
    return RegisterMatrixAccountUseCase(account_repo=account_repo, cipher=cipher)


def get_list_matrix_accounts_use_case(
    account_repo: Annotated[MatrixAccountRepositoryPort, Depends(get_matrix_account_repository)],
) -> ListMatrixAccountsUseCase:
    return ListMatrixAccountsUseCase(account_repo=account_repo)


def get_delete_matrix_account_use_case(
    account_repo: Annotated[MatrixAccountRepositoryPort, Depends(get_matrix_account_repository)],
) -> DeleteMatrixAccountUseCase:
    return DeleteMatrixAccountUseCase(account_repo=account_repo)


def get_process_public_webhook_use_case(
    webhook_repo: Annotated[WebhookRepositoryPort, Depends(get_webhook_repository)],
    client_manager: Annotated[MatrixClientManager, Depends(get_matrix_client_manager)],
) -> ProcessPublicWebhookUseCase:
    return ProcessPublicWebhookUseCase(
        webhook_repo=webhook_repo,
        client_manager=client_manager,
    )


def get_create_webhook_use_case(
    webhook_repo: Annotated[WebhookRepositoryPort, Depends(get_webhook_repository)],
    account_repo: Annotated[MatrixAccountRepositoryPort, Depends(get_matrix_account_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CreateWebhookUseCase:
    return CreateWebhookUseCase(
        webhook_repo=webhook_repo,
        account_repo=account_repo,
        public_base_url=settings.public_base_url,
    )


def get_list_webhooks_use_case(
    webhook_repo: Annotated[WebhookRepositoryPort, Depends(get_webhook_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ListWebhooksUseCase:
    return ListWebhooksUseCase(
        webhook_repo=webhook_repo,
        public_base_url=settings.public_base_url,
    )


def get_delete_webhook_use_case(
    webhook_repo: Annotated[WebhookRepositoryPort, Depends(get_webhook_repository)],
) -> DeleteWebhookUseCase:
    return DeleteWebhookUseCase(webhook_repo)


def get_request_device_verification_use_case(
    account_repo: Annotated[MatrixAccountRepositoryPort, Depends(get_matrix_account_repository)],
    client_manager: Annotated[MatrixClientManager, Depends(get_matrix_client_manager)],
) -> RequestDeviceVerificationUseCase:
    return RequestDeviceVerificationUseCase(
        account_repo=account_repo,
        client_manager=client_manager,
    )
