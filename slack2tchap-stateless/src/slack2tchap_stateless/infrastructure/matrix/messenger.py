"""Stateless ephemeral Matrix message dispatcher without persistent store."""

import logging
import ssl
from typing import Any, cast

import certifi
from nio import AsyncClient, JoinError, LoginError, RoomSendError, RoomSendResponse

from slack2tchap_core.domain.exceptions import AuthenticationError, MessageSendError
from slack2tchap_core.domain.ports import StatelessMessengerPort
from slack2tchap_core.matrix.helpers import resolve_homeserver_url

logger = logging.getLogger(__name__)


class StatelessMatrixMessenger(StatelessMessengerPort):
    """Dispatches unencrypted Matrix alerts on the fly via an ephemeral, transient client."""

    def __init__(self, default_homeserver: str, auto_join: bool = True) -> None:
        self._default_homeserver = default_homeserver
        self._auto_join = auto_join

    async def send_message(
        self,
        homeserver: str,
        user_id: str,
        password: str | None,
        access_token: str | None,
        room_id: str,
        formatted_body: str,
        plain_body: str,
    ) -> str:
        """Create a transient client, log in, send unencrypted message, and close immediately."""
        clean_user_id = user_id.strip()
        clean_room_id = room_id.strip()

        hs_url = homeserver.strip() if homeserver else ""
        if not hs_url:
            hs_url = resolve_homeserver_url(self._default_homeserver, clean_user_id)

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        client = AsyncClient(
            homeserver=hs_url,
            user=clean_user_id,
            ssl=cast(Any, ssl_ctx),
        )

        try:
            # 1. Authenticate (password or access_token)
            if password:
                logger.debug("Stateless bot %s logging in to %s...", clean_user_id, hs_url)
                resp = await client.login(password=password)
                if isinstance(resp, LoginError):
                    raise AuthenticationError(
                        f"Matrix login failed for {clean_user_id}: {resp.message}"
                    )
            elif access_token:
                client.access_token = access_token
                client.user_id = clean_user_id
            else:
                raise AuthenticationError("Neither password nor access_token provided.")

            # 2. Join room if auto_join enabled
            if self._auto_join:
                join_resp = await client.join(clean_room_id)
                if isinstance(join_resp, JoinError):
                    logger.debug(
                        "Join room %s returned %s (bot may already be a member)",
                        clean_room_id,
                        join_resp.message,
                    )

            # 3. Send unencrypted message
            content = {
                "msgtype": "m.text",
                "body": plain_body,
                "format": "org.matrix.custom.html",
                "formatted_body": formatted_body,
            }

            logger.info(
                "Stateless bot %s sending message to room %s...", clean_user_id, clean_room_id
            )
            send_resp = await client.room_send(
                room_id=clean_room_id,
                message_type="m.room.message",
                content=content,
            )

            if isinstance(send_resp, RoomSendError):
                raise MessageSendError(
                    f"Failed to dispatch to {clean_room_id}: {send_resp.message}"
                )

            event_id = cast_event_id(send_resp)
            logger.info("Stateless alert delivered to %s (event_id=%s)", clean_room_id, event_id)
            return event_id
        finally:
            await client.close()


def cast_event_id(send_resp: RoomSendResponse | RoomSendError) -> str:
    """Helper to cleanly extract event_id from RoomSendResponse."""
    if isinstance(send_resp, RoomSendResponse):
        return str(send_resp.event_id)
    return ""
