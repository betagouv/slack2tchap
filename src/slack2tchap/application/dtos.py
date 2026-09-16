"""Data Transfer Objects (DTOs) for application workflows."""

from dataclasses import dataclass
from uuid import UUID

from slack2tchap.domain.models import AlertMessage


@dataclass(frozen=True)
class SendAlertCommand:
    """Command payload to trigger sending an alert."""

    alert: AlertMessage
    target_room_id: str | None = None


@dataclass(frozen=True)
class SendPublicWebhookCommand:
    """Command payload for an alert received via a public webhook UUID."""

    webhook_id: UUID
    alert: AlertMessage


@dataclass(frozen=True)
class AlertResultDTO:
    """Execution result for sending an alert."""

    success: bool
    room_id: str
    is_encrypted: bool
    event_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RegisterMatrixAccountCommand:
    """Command to register a dedicated Matrix bot account."""

    name: str
    matrix_user_id: str
    user_id: UUID
    password: str | None = None
    access_token: str | None = None


@dataclass(frozen=True)
class MatrixAccountDTO:
    """DTO representing a registered Matrix bot account."""

    id: UUID
    name: str
    matrix_user_id: str
    device_id: str
    user_id: UUID
    has_persisted_crypto_store: bool
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class CreateWebhookCommand:
    """Command payload to create a new webhook endpoint."""

    name: str
    matrix_room_id: str
    matrix_account_id: UUID
    user_id: UUID


@dataclass(frozen=True)
class WebhookDTO:
    """DTO representing a webhook destination."""

    id: UUID
    name: str
    matrix_room_id: str
    matrix_account_id: UUID
    user_id: UUID
    public_url: str
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class UserDTO:
    """DTO representing a registered user."""

    id: UUID
    email: str
    api_key_prefix: str
    is_admin: bool
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class RequestDeviceVerificationCommand:
    """Command payload to initiate interactive device verification for a Matrix bot."""

    account_id: UUID
    user_id: UUID
    target_device_id: str | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class DeviceVerificationDTO:
    """DTO representing the result of an interactive SAS verification request."""

    account_id: UUID
    transaction_id: str
    target_device_id: str | None
    emojis: list[tuple[str, str]]


@dataclass(frozen=True)
class CreateUserCommand:
    """Command payload to create a new user account (admin-only)."""

    email: str


@dataclass(frozen=True)
class UserCreatedDTO:
    """DTO returned once after user creation, including the one-time raw API key."""

    id: UUID
    email: str
    api_key_prefix: str
    raw_api_key: str
    is_admin: bool
    is_active: bool
    created_at: str
