"""Domain models for slack2tchap, imported from slack2tchap_core."""

from slack2tchap_core.domain.models import (
    AlertAttachment,
    AlertField,
    AlertMessage,
    AlertSeverity,
    MatrixAccount,
    MatrixCredentials,
    RoomId,
    User,
    WebhookEndpoint,
)

__all__ = [
    "AlertAttachment",
    "AlertField",
    "AlertMessage",
    "AlertSeverity",
    "MatrixAccount",
    "MatrixCredentials",
    "RoomId",
    "User",
    "WebhookEndpoint",
]
