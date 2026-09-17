"""Shared Matrix communication helpers and message builders."""

from typing import Any

from slack2tchap_core.domain.models import AlertMessage


def resolve_homeserver_url(configured_homeserver: str, matrix_user_id: str) -> str:
    """Resolve actual homeserver URL based on user ID domain and default homeserver."""
    if ":" in matrix_user_id:
        domain = matrix_user_id.split(":", 1)[1].strip()
        clean_hs = configured_homeserver.strip().rstrip("/")
        if not clean_hs or "www.tchap.gouv.fr" in clean_hs:
            return f"https://matrix.{domain}"
        if domain.endswith(".tchap.gouv.fr") and not clean_hs.endswith(domain):
            return f"https://matrix.{domain}"
    return configured_homeserver


def build_matrix_message_content(alert: AlertMessage) -> dict[str, Any]:
    """Construct a compliant Matrix m.room.message event dictionary from an AlertMessage."""
    return {
        "msgtype": "m.text",
        "body": alert.to_plain_text(),
        "format": "org.matrix.custom.html",
        "formatted_body": alert.to_matrix_html(),
    }
