"""Unit tests for SendAlertUseCase."""

import pytest

from fakes import FakeMatrixMessenger
from slack2tchap.application.dtos import SendAlertCommand
from slack2tchap.application.use_cases import SendAlertUseCase
from slack2tchap.domain.models import AlertMessage, AlertSeverity


@pytest.mark.asyncio
async def test_send_alert_success_with_default_room(
    fake_matrix_messenger: FakeMatrixMessenger,
) -> None:
    use_case = SendAlertUseCase(
        messenger=fake_matrix_messenger,
        default_room_id="!default_room:agent.tchap.gouv.fr",
    )

    alert = AlertMessage(text="Application successfully deployed", severity=AlertSeverity.SUCCESS)
    command = SendAlertCommand(alert=alert)

    result = await use_case.execute(command)

    assert result.success is True
    assert result.room_id == "!default_room:agent.tchap.gouv.fr"
    assert result.is_encrypted is False
    assert result.event_id is not None
    assert len(fake_matrix_messenger.sent_messages) == 1
    assert (
        "Application successfully deployed" in fake_matrix_messenger.sent_messages[0]["plain_body"]
    )


@pytest.mark.asyncio
async def test_send_alert_target_room_override(fake_matrix_messenger: FakeMatrixMessenger) -> None:
    use_case = SendAlertUseCase(
        messenger=fake_matrix_messenger,
        default_room_id="!default:agent.tchap.gouv.fr",
    )

    alert = AlertMessage(text="Targeted alert")
    command = SendAlertCommand(
        alert=alert,
        target_room_id="!custom_room:agent.tchap.gouv.fr",
    )

    result = await use_case.execute(command)

    assert result.success is True
    assert result.room_id == "!custom_room:agent.tchap.gouv.fr"
    assert fake_matrix_messenger.sent_messages[0]["room_id"] == "!custom_room:agent.tchap.gouv.fr"


@pytest.mark.asyncio
async def test_send_alert_encrypted_room(fake_matrix_messenger: FakeMatrixMessenger) -> None:
    encrypted_room = "!encrypted_room:agent.tchap.gouv.fr"
    use_case = SendAlertUseCase(
        messenger=fake_matrix_messenger,
        default_room_id=encrypted_room,
    )

    alert = AlertMessage(text="Confidential alert", severity=AlertSeverity.WARNING)
    command = SendAlertCommand(alert=alert)

    result = await use_case.execute(command)

    assert result.success is True
    assert result.room_id == encrypted_room
    assert result.is_encrypted is True


@pytest.mark.asyncio
async def test_send_alert_missing_room_fails(fake_matrix_messenger: FakeMatrixMessenger) -> None:
    use_case = SendAlertUseCase(
        messenger=fake_matrix_messenger,
        default_room_id=None,
    )

    alert = AlertMessage(text="Lost alert without room")
    command = SendAlertCommand(alert=alert)

    result = await use_case.execute(command)

    assert result.success is False
    assert result.room_id == ""
    assert "No target Matrix room specified" in (result.error or "")
    assert len(fake_matrix_messenger.sent_messages) == 0


@pytest.mark.asyncio
async def test_send_alert_invalid_room_format(fake_matrix_messenger: FakeMatrixMessenger) -> None:
    use_case = SendAlertUseCase(
        messenger=fake_matrix_messenger,
        default_room_id="not-a-valid-matrix-room-id",
    )

    alert = AlertMessage(text="Bad room format")
    command = SendAlertCommand(alert=alert)

    result = await use_case.execute(command)

    assert result.success is False
    assert "Invalid Matrix Room ID" in (result.error or "")
    assert len(fake_matrix_messenger.sent_messages) == 0


@pytest.mark.asyncio
async def test_send_alert_messenger_failure(fake_matrix_messenger: FakeMatrixMessenger) -> None:
    fake_matrix_messenger.should_fail = True
    fake_matrix_messenger.failure_message = "Matrix homeserver 504 Gateway Timeout"

    use_case = SendAlertUseCase(
        messenger=fake_matrix_messenger,
        default_room_id="!room:agent.tchap.gouv.fr",
    )

    alert = AlertMessage(text="Alert during outage")
    command = SendAlertCommand(alert=alert)

    result = await use_case.execute(command)

    assert result.success is False
    assert "504 Gateway Timeout" in (result.error or "")
