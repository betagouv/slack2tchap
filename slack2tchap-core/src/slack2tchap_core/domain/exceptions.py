"""Domain exceptions for slack2tchap."""


class DomainError(Exception):
    """Base exception for all domain-specific errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidRoomIdError(DomainError):
    """Raised when a room ID does not match expected Matrix formats or is missing."""


class UserNotFoundError(DomainError):
    """Raised when a specified user does not exist."""


class UserAlreadyExistsError(DomainError):
    """Raised when an attempt to create a user with an existing email is made."""


class WebhookNotFoundError(DomainError):
    """Raised when a webhook ID is not found or is inactive."""


class MatrixAccountNotFoundError(DomainError):
    """Raised when a specified Matrix account does not exist or is inactive."""


class InvalidApiKeyError(DomainError):
    """Raised when provided API key is invalid or unrecognized."""


class CipherError(DomainError):
    """Raised when cryptographic encryption or decryption fails."""


class MatrixClientError(DomainError):
    """Base exception for Matrix messenger communication failures."""


class RoomNotFoundError(MatrixClientError):
    """Raised when target room cannot be found or bot is not a member."""


class MessageSendError(MatrixClientError):
    """Raised when sending a message to a Matrix room fails."""


class CryptoStoreError(MatrixClientError):
    """Raised when SQLite Olm crypto store encounters an unrecoverable issue."""


class AuthenticationError(MatrixClientError):
    """Raised when authentication with Matrix homeserver fails."""


class VerificationTimeoutError(MatrixClientError):
    """Raised when waiting for interactive SAS device verification times out."""


class AccessDeniedError(DomainError):
    """Raised when a user attempts an action they are not authorized to perform."""
