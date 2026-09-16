"""Application use cases for sending alerts and managing webhooks and matrix bots."""

import hashlib
import logging
import re
import secrets
from uuid import UUID

from slack2tchap.application.dtos import (
    AlertResultDTO,
    CreateUserCommand,
    CreateWebhookCommand,
    DeviceVerificationDTO,
    MatrixAccountDTO,
    RegisterMatrixAccountCommand,
    RequestDeviceVerificationCommand,
    SendAlertCommand,
    SendPublicWebhookCommand,
    UserCreatedDTO,
    WebhookDTO,
)
from slack2tchap.domain.exceptions import (
    DomainError,
    InvalidApiKeyError,
    InvalidRoomIdError,
    MatrixAccountNotFoundError,
    MatrixClientError,
    UserAlreadyExistsError,
    WebhookNotFoundError,
)
from slack2tchap.domain.models import (
    MatrixAccount,
    RoomId,
    User,
    WebhookEndpoint,
)
from slack2tchap.domain.ports import (
    MatrixAccountRepositoryPort,
    MatrixClientManagerPort,
    MatrixMessengerPort,
    SecretCipherPort,
    UserRepositoryPort,
    WebhookRepositoryPort,
)

logger = logging.getLogger(__name__)


class RegisterMatrixAccountUseCase:
    """Use case to configure a new Matrix bot account with encrypted credentials."""

    def __init__(
        self,
        account_repo: MatrixAccountRepositoryPort,
        cipher: SecretCipherPort,
    ) -> None:
        self._account_repo = account_repo
        self._cipher = cipher

    async def execute(self, command: RegisterMatrixAccountCommand) -> MatrixAccountDTO:
        cleaned_user_id = command.matrix_user_id.strip()
        if not re.match(r"^@[a-zA-Z0-9_\.\=\-\/]+:[a-zA-Z0-9\.\-]+(?::\d+)?$", cleaned_user_id):
            raise DomainError(
                f"Invalid Matrix User ID: '{command.matrix_user_id}'. Must be full ID e.g. @bot:agent.tchap.gouv.fr"
            )

        if not command.password and not command.access_token:
            raise DomainError(
                "Either password or access_token must be provided for Matrix bot authentication."
            )

        enc_pass: str | None = None
        enc_token: str | None = None
        nonce: str | None = None

        if command.password:
            enc_pass, nonce = self._cipher.encrypt(command.password)
        elif command.access_token:
            enc_token, nonce = self._cipher.encrypt(command.access_token)

        account = MatrixAccount(
            name=command.name.strip(),
            matrix_user_id=cleaned_user_id,
            user_id=command.user_id,
            encrypted_password=enc_pass,
            encrypted_access_token=enc_token,
            encryption_nonce=nonce,
        )

        saved = await self._account_repo.save(account)
        return MatrixAccountDTO(
            id=saved.id,
            name=saved.name,
            matrix_user_id=saved.matrix_user_id,
            device_id=saved.device_id,
            user_id=saved.user_id,
            has_persisted_crypto_store=bool(saved.crypto_store_blob is not None),
            is_active=saved.is_active,
            created_at=saved.created_at.isoformat(),
        )


class ListMatrixAccountsUseCase:
    """Use case to list all configured Matrix bots for a user."""

    def __init__(self, account_repo: MatrixAccountRepositoryPort) -> None:
        self._account_repo = account_repo

    async def execute(self, user_id: UUID) -> list[MatrixAccountDTO]:
        accounts = await self._account_repo.list_by_user_id(user_id)
        return [
            MatrixAccountDTO(
                id=acc.id,
                name=acc.name,
                matrix_user_id=acc.matrix_user_id,
                device_id=acc.device_id,
                user_id=acc.user_id,
                has_persisted_crypto_store=bool(acc.crypto_store_blob is not None),
                is_active=acc.is_active,
                created_at=acc.created_at.isoformat(),
            )
            for acc in accounts
        ]


class DeleteMatrixAccountUseCase:
    """Use case to remove a Matrix bot account."""

    def __init__(self, account_repo: MatrixAccountRepositoryPort) -> None:
        self._account_repo = account_repo

    async def execute(self, account_id: UUID, user_id: UUID) -> bool:
        account = await self._account_repo.get_by_id(account_id)
        if account is None or account.user_id != user_id:
            raise MatrixAccountNotFoundError(f"Matrix account {account_id} not found.")
        return await self._account_repo.delete(account_id)


class ProcessPublicWebhookUseCase:
    """Use case to ingest an alert via public webhook UUID and dispatch using the mapped Matrix bot."""

    def __init__(
        self,
        webhook_repo: WebhookRepositoryPort,
        client_manager: MatrixClientManagerPort,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._client_manager = client_manager

    async def execute(self, command: SendPublicWebhookCommand) -> AlertResultDTO:
        webhook = await self._webhook_repo.get_by_id(command.webhook_id)
        if webhook is None or not webhook.is_active:
            raise WebhookNotFoundError(f"Webhook {command.webhook_id} not found or is inactive.")

        target_room = webhook.matrix_room_id

        # Get or restore active Matrix client for the assigned bot
        messenger = await self._client_manager.get_or_create_client(webhook.matrix_account_id)

        try:
            is_encrypted = await messenger.is_room_encrypted(target_room)
            plain_body = command.alert.to_plain_text()
            formatted_body = command.alert.to_matrix_html()

            event_id = await messenger.send_message(
                room_id=target_room,
                formatted_body=formatted_body,
                plain_body=plain_body,
            )

            logger.info(
                "Successfully dispatched public webhook=%s to room=%s (event_id=%s)",
                webhook.id,
                target_room,
                event_id,
            )

            return AlertResultDTO(
                success=True,
                room_id=target_room,
                is_encrypted=is_encrypted,
                event_id=event_id,
            )
        except MatrixClientError as exc:
            return AlertResultDTO(
                success=False,
                room_id=target_room,
                is_encrypted=False,
                error=exc.message,
            )


class CreateWebhookUseCase:
    """Use case to declare a new webhook endpoint mapping to a Matrix room and bot."""

    def __init__(
        self,
        webhook_repo: WebhookRepositoryPort,
        account_repo: MatrixAccountRepositoryPort,
        public_base_url: str,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._account_repo = account_repo
        self._public_base_url = public_base_url.rstrip("/")

    async def execute(self, command: CreateWebhookCommand) -> WebhookDTO:
        # Validate Matrix room ID format
        try:
            room_vo = RoomId(command.matrix_room_id)
            valid_room_id = str(room_vo)
        except ValueError as exc:
            raise InvalidRoomIdError(str(exc)) from exc

        # Ensure assigned Matrix account exists and belongs to user
        account = await self._account_repo.get_by_id(command.matrix_account_id)
        if account is None or account.user_id != command.user_id or not account.is_active:
            raise MatrixAccountNotFoundError(
                f"Matrix account {command.matrix_account_id} not found or not active."
            )

        webhook = WebhookEndpoint(
            name=command.name.strip(),
            matrix_room_id=valid_room_id,
            matrix_account_id=command.matrix_account_id,
            user_id=command.user_id,
        )

        saved = await self._webhook_repo.save(webhook)
        public_url = f"{self._public_base_url}/webhook/slack/{saved.id}"

        return WebhookDTO(
            id=saved.id,
            name=saved.name,
            matrix_room_id=saved.matrix_room_id,
            matrix_account_id=saved.matrix_account_id,
            user_id=saved.user_id,
            public_url=public_url,
            is_active=saved.is_active,
            created_at=saved.created_at.isoformat(),
        )


class ListWebhooksUseCase:
    """Use case to list all webhooks belonging to a user."""

    def __init__(
        self,
        webhook_repo: WebhookRepositoryPort,
        public_base_url: str,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._public_base_url = public_base_url.rstrip("/")

    async def execute(self, user_id: UUID) -> list[WebhookDTO]:
        endpoints = await self._webhook_repo.list_by_user_id(user_id)
        return [
            WebhookDTO(
                id=ep.id,
                name=ep.name,
                matrix_room_id=ep.matrix_room_id,
                matrix_account_id=ep.matrix_account_id,
                user_id=ep.user_id,
                public_url=f"{self._public_base_url}/webhook/slack/{ep.id}",
                is_active=ep.is_active,
                created_at=ep.created_at.isoformat(),
            )
            for ep in endpoints
        ]


class DeleteWebhookUseCase:
    """Use case to delete a webhook."""

    def __init__(self, webhook_repo: WebhookRepositoryPort) -> None:
        self._webhook_repo = webhook_repo

    async def execute(self, webhook_id: UUID, user_id: UUID) -> bool:
        webhook = await self._webhook_repo.get_by_id(webhook_id)
        if webhook is None or webhook.user_id != user_id:
            raise WebhookNotFoundError(f"Webhook {webhook_id} not found.")
        return await self._webhook_repo.delete(webhook_id)


class AuthenticateApiKeyUseCase:
    """Use case to authenticate an incoming API key against stored SHA-256 hashes."""

    def __init__(self, user_repo: UserRepositoryPort) -> None:
        self._user_repo = user_repo

    async def execute(self, raw_api_key: str) -> User:
        if not raw_api_key or not raw_api_key.strip():
            raise InvalidApiKeyError("API key cannot be empty.")

        key_hash = hashlib.sha256(raw_api_key.strip().encode("utf-8")).hexdigest()
        user = await self._user_repo.get_by_api_key_hash(key_hash)

        if user is None or not user.is_active:
            raise InvalidApiKeyError("Invalid API key or inactive account.")

        return user


class CreateUserUseCase:
    """Use case to create a new user account with a generated API key (admin-only)."""

    API_KEY_PREFIX = "s2t_live_"

    def __init__(self, user_repo: UserRepositoryPort) -> None:
        self._user_repo = user_repo

    async def execute(self, command: CreateUserCommand) -> UserCreatedDTO:
        normalized_email = command.email.strip().lower()

        existing = await self._user_repo.get_by_email(normalized_email)
        if existing is not None:
            raise UserAlreadyExistsError(f"A user with email '{normalized_email}' already exists.")

        raw_key = f"{self.API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        key_prefix = raw_key[:16] + "..."

        user = User(
            email=normalized_email,
            api_key_hash=key_hash,
            api_key_prefix=key_prefix,
            is_admin=False,
            is_active=True,
        )

        saved = await self._user_repo.save(user)

        return UserCreatedDTO(
            id=saved.id,
            email=saved.email,
            api_key_prefix=saved.api_key_prefix,
            raw_api_key=raw_key,
            is_admin=saved.is_admin,
            is_active=saved.is_active,
            created_at=saved.created_at.isoformat(),
        )


class SendAlertUseCase:
    """Helper use case for direct room sending when messenger is explicitly supplied."""

    def __init__(
        self,
        messenger: MatrixMessengerPort,
        default_room_id: str | None = None,
    ) -> None:
        self._messenger = messenger
        self._default_room_id = default_room_id

    async def execute(self, command: SendAlertCommand) -> AlertResultDTO:
        target_room_str = command.target_room_id or self._default_room_id
        if not target_room_str:
            return AlertResultDTO(
                success=False,
                room_id="",
                is_encrypted=False,
                error="No target Matrix room specified and no default room configured.",
            )

        try:
            room_id = RoomId(target_room_str)
        except ValueError as exc:
            return AlertResultDTO(
                success=False,
                room_id=target_room_str,
                is_encrypted=False,
                error=str(exc),
            )

        try:
            is_encrypted = await self._messenger.is_room_encrypted(room_id.value)
            event_id = await self._messenger.send_message(
                room_id=room_id.value,
                formatted_body=command.alert.to_matrix_html(),
                plain_body=command.alert.to_plain_text(),
            )
            return AlertResultDTO(
                success=True,
                room_id=room_id.value,
                is_encrypted=is_encrypted,
                event_id=event_id,
            )
        except Exception as exc:
            return AlertResultDTO(
                success=False,
                room_id=room_id.value,
                is_encrypted=False,
                error=str(exc),
            )


class RequestDeviceVerificationUseCase:
    """Use case to initiate interactive SAS device verification for a Matrix bot."""

    def __init__(
        self,
        account_repo: MatrixAccountRepositoryPort,
        client_manager: MatrixClientManagerPort,
    ) -> None:
        self._account_repo = account_repo
        self._client_manager = client_manager

    async def execute(self, command: RequestDeviceVerificationCommand) -> DeviceVerificationDTO:
        account = await self._account_repo.get_by_id(command.account_id)
        if not account or not account.is_active or account.user_id != command.user_id:
            raise MatrixAccountNotFoundError(
                f"Matrix bot account {command.account_id} not found or you do not own it."
            )

        client = await self._client_manager.get_client(command.account_id)
        tx_id, emojis, target_device = await client.request_verification(
            target_device_id=command.target_device_id,
            timeout_seconds=command.timeout_seconds,
        )

        return DeviceVerificationDTO(
            account_id=command.account_id,
            transaction_id=tx_id,
            target_device_id=target_device,
            emojis=emojis,
        )
