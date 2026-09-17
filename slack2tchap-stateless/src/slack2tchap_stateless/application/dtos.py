"""Application Data Transfer Objects for slack2tchap-stateless."""

from dataclasses import dataclass

from slack2tchap_core.domain.models import AlertMessage


@dataclass(frozen=True)
class SendStatelessWebhookCommand:
    """Command carrying an encrypted credentials token and the alert message to dispatch."""

    param_token: str
    alert: AlertMessage
