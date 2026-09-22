"""Unit tests for slack2tchap_core domain models."""

import pytest

from slack2tchap_core.domain.models import (
    AlertAttachment,
    AlertField,
    AlertMessage,
    AlertSeverity,
    RoomId,
)


def test_room_id_valid() -> None:
    room = RoomId("!abcdef123:agent.tchap.gouv.fr")
    assert str(room) == "!abcdef123:agent.tchap.gouv.fr"

    alias = RoomId("#my-channel:matrix.org")
    assert str(alias) == "#my-channel:matrix.org"


def test_room_id_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid Matrix Room ID"):
        RoomId("invalid-room-without-prefix")

    with pytest.raises(ValueError, match="Invalid Matrix Room ID"):
        RoomId("@user:server.fr")


def test_severity_from_slack_color() -> None:
    assert AlertSeverity.from_slack_color("good") == AlertSeverity.SUCCESS
    assert AlertSeverity.from_slack_color("#36a64f") == AlertSeverity.SUCCESS
    assert AlertSeverity.from_slack_color("warning") == AlertSeverity.WARNING
    assert AlertSeverity.from_slack_color("danger") == AlertSeverity.DANGER
    assert AlertSeverity.from_slack_color("#de4343") == AlertSeverity.DANGER
    assert AlertSeverity.from_slack_color(None) == AlertSeverity.INFO
    assert AlertSeverity.from_slack_color("unknown-color") == AlertSeverity.INFO


def test_alert_message_rendering() -> None:
    alert = AlertMessage(
        text="Service outage reported",
        severity=AlertSeverity.DANGER,
        attachments=[
            AlertAttachment(
                title="API Gateway",
                title_link="https://status.example.gouv.fr",
                text="502 Bad Gateway observed on upstream cluster",
                color="danger",
                fields=[
                    AlertField(title="Environment", value="Production", short=True),
                    AlertField(title="Impact", value="All users", short=True),
                ],
                footer="Alertmanager v0.26",
            )
        ],
    )

    plain = alert.to_plain_text()
    assert "[DANGER]" in plain
    assert "Service outage reported" in plain
    assert "**API Gateway** (https://status.example.gouv.fr)" in plain
    assert "Environment: Production" in plain
    assert "_Alertmanager v0.26_" in plain

    html_out = alert.to_matrix_html()
    assert "<strong>🔴 [DANGER]</strong>" in html_out
    assert "Service outage reported" in html_out
    assert '<a href="https://status.example.gouv.fr">API Gateway</a>' in html_out
    assert "<td><strong>Environment</strong></td><td>Production</td>" in html_out
    assert "Alertmanager v0.26" in html_out


def test_alert_message_markdown_table_and_pretext() -> None:
    table_md = "| URI | Method | Errors |\n| :--- | :--- | :--- |\n| `/api/test` | GET | 42 |"
    alert = AlertMessage(
        severity=AlertSeverity.WARNING,
        attachments=[
            AlertAttachment(
                pretext="⚠️ *High error rate detected*",
                text=f"**Environment**: `prod`\n\n{table_md}",
                color="warning",
            )
        ],
    )

    plain = alert.to_plain_text()
    assert "High error rate detected" in plain
    assert "`/api/test`" in plain

    html_out = alert.to_matrix_html()
    assert "High error rate detected" in html_out
    assert "<strong>Environment</strong>" in html_out
    assert "<code>prod</code>" in html_out
    assert "<table>" in html_out
    assert "<th" in html_out
    assert "border-left: 4px solid #daa038;" in html_out


def test_alert_attachment_title_markdown() -> None:
    alert = AlertMessage(
        severity=AlertSeverity.DANGER,
        attachments=[
            AlertAttachment(
                title="🚨 **ALERTE PROD** : Incident sur `task-scheduler`",
                title_link="https://kibana.example.gouv.fr",
                color="danger",
            )
        ],
    )

    html_out = alert.to_matrix_html()
    assert "<strong>ALERTE PROD</strong>" in html_out
    assert "<code>task-scheduler</code>" in html_out
    assert '<a href="https://kibana.example.gouv.fr">' in html_out
    assert "**ALERTE PROD**" not in html_out
