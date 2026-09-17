"""FastAPI dependency injection for slack2tchap-stateless."""

from typing import Annotated

from fastapi import Depends

from slack2tchap_core.domain.ports import SecretCipherPort, StatelessMessengerPort
from slack2tchap_core.infrastructure.security.cipher import AesGcmSecretCipher
from slack2tchap_stateless.application.use_cases import ProcessStatelessWebhookUseCase
from slack2tchap_stateless.core.config import Settings, get_settings
from slack2tchap_stateless.infrastructure.matrix.messenger import StatelessMatrixMessenger


def get_secret_cipher(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SecretCipherPort:
    """Provide AES-GCM cipher initialized with master encryption key."""
    return AesGcmSecretCipher(settings.secret_encryption_key.get_secret_value())


def get_stateless_messenger(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StatelessMessengerPort:
    """Provide stateless ephemeral Matrix messenger."""
    return StatelessMatrixMessenger(
        default_homeserver=settings.matrix_homeserver,
        auto_join=settings.matrix_auto_join,
    )


def get_process_stateless_webhook_use_case(
    cipher: Annotated[SecretCipherPort, Depends(get_secret_cipher)],
    messenger: Annotated[StatelessMessengerPort, Depends(get_stateless_messenger)],
) -> ProcessStatelessWebhookUseCase:
    """Provide initialized ProcessStatelessWebhookUseCase."""
    return ProcessStatelessWebhookUseCase(
        cipher=cipher,
        stateless_messenger=messenger,
    )
