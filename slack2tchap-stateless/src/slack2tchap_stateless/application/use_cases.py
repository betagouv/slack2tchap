"""Application use cases for stateless webhook processing."""

import json
import logging
from typing import Any

from slack2tchap_core.domain.exceptions import (
    CipherError,
    DomainError,
    InvalidRoomIdError,
)
from slack2tchap_core.domain.models import RoomId
from slack2tchap_core.domain.ports import SecretCipherPort, StatelessMessengerPort
from slack2tchap_stateless.application.dtos import SendStatelessWebhookCommand

logger = logging.getLogger(__name__)


class ProcessStatelessWebhookUseCase:
    """Decrypts token parameters, validates destination, and dispatches message on the fly."""

    def __init__(
        self,
        cipher: SecretCipherPort,
        stateless_messenger: StatelessMessengerPort,
    ) -> None:
        self._cipher = cipher
        self._messenger = stateless_messenger

    async def execute(self, command: SendStatelessWebhookCommand) -> str:
        """Execute the stateless alert delivery workflow."""
        # 1. Decrypt token containing username, password, channelID
        try:
            decrypted_json_str = self._cipher.decrypt_token(command.param_token)
            payload: dict[str, Any] = json.loads(decrypted_json_str)
        except (CipherError, json.JSONDecodeError) as exc:
            logger.warning("Stateless token decryption failed: %s", exc)
            raise CipherError("Invalid or corrupted stateless token.") from exc

        # 2. Extract and validate credentials & channel
        username = str(
            payload.get("username") or payload.get("login") or payload.get("user_id") or ""
        ).strip()
        password = payload.get("password")
        password_str: str | None = str(password).strip() if password else None
        access_token = payload.get("access_token")
        access_token_str: str | None = str(access_token).strip() if access_token else None

        channel_id_raw = (
            command.alert.channel_override
            or payload.get("channelID")
            or payload.get("channel_id")
            or payload.get("room_id")
        )
        if not channel_id_raw:
            raise InvalidRoomIdError("No target room ID found in token or payload.")

        try:
            target_room = RoomId(str(channel_id_raw).strip())
        except ValueError as exc:
            raise InvalidRoomIdError(f"Target room ID is invalid: {exc}") from exc

        if not username:
            raise DomainError("Missing username/login in stateless token.")
        if not password_str and not access_token_str:
            raise DomainError("Missing password or access_token in stateless token.")

        homeserver = str(payload.get("homeserver") or "").strip()

        # 3. Format message content and dispatch via transient Matrix client
        formatted_html = command.alert.to_matrix_html()
        plain_text = command.alert.to_plain_text()

        logger.info(
            "Dispatching stateless alert for bot %s to room %s...", username, target_room.value
        )

        event_id = await self._messenger.send_message(
            homeserver=homeserver,
            user_id=username,
            password=password_str,
            access_token=access_token_str,
            room_id=target_room.value,
            formatted_body=formatted_html,
            plain_body=plain_text,
        )

        logger.info("Stateless alert successfully delivered (event_id=%s)", event_id)
        return event_id
