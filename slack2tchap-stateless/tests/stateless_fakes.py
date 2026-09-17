"""In-memory fakes for slack2tchap-stateless tests."""

from typing import Any

from slack2tchap_core.domain.exceptions import MessageSendError
from slack2tchap_core.domain.ports import StatelessMessengerPort


class FakeStatelessMessenger(StatelessMessengerPort):
    """In-memory stateless Matrix messenger for testing."""

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []
        self.should_fail: bool = False
        self.failure_message: str = "Simulated stateless dispatch error"

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
        if self.should_fail:
            raise MessageSendError(self.failure_message)

        self.sent_messages.append(
            {
                "homeserver": homeserver,
                "user_id": user_id,
                "password": password,
                "access_token": access_token,
                "room_id": room_id,
                "formatted_body": formatted_body,
                "plain_body": plain_body,
            }
        )
        return f"$stateless_event_{len(self.sent_messages)}:matrix.agent.tchap.gouv.fr"
