"""Domain exceptions for slack2tchap, imported from slack2tchap_core."""

from slack2tchap_core.domain.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    CipherError,
    CryptoStoreError,
    DomainError,
    InvalidApiKeyError,
    InvalidRoomIdError,
    MatrixAccountNotFoundError,
    MatrixClientError,
    MessageSendError,
    RoomNotFoundError,
    UserAlreadyExistsError,
    UserNotFoundError,
    VerificationTimeoutError,
    WebhookNotFoundError,
)

__all__ = [
    "AccessDeniedError",
    "AuthenticationError",
    "CipherError",
    "CryptoStoreError",
    "DomainError",
    "InvalidApiKeyError",
    "InvalidRoomIdError",
    "MatrixAccountNotFoundError",
    "MatrixClientError",
    "MessageSendError",
    "RoomNotFoundError",
    "UserAlreadyExistsError",
    "UserNotFoundError",
    "VerificationTimeoutError",
    "WebhookNotFoundError",
]
