"""Unit tests for slack2tchap_core Slack/Mattermost payload parser."""

from slack2tchap_core.domain.models import AlertSeverity
from slack2tchap_core.infrastructure.parsers.slack_parser import SlackPayloadParser


def test_parse_simple_text() -> None:
    payload = {"text": "Simple notification message"}
    alert = SlackPayloadParser.parse(payload)

    assert alert.text == "Simple notification message"
    assert alert.severity == AlertSeverity.INFO
    assert len(alert.attachments) == 0
    assert alert.channel_override is None


def test_parse_slack_link_conversion() -> None:
    payload = {
        "text": "Check dashboard at <https://grafana.internal.gouv.fr/d/123|Grafana Prod> or docs at <https://docs.gouv.fr>."
    }
    alert = SlackPayloadParser.parse(payload)

    assert "[Grafana Prod](https://grafana.internal.gouv.fr/d/123)" in alert.text
    assert "https://docs.gouv.fr" in alert.text
    assert "<https://" not in alert.text


def test_parse_special_mentions() -> None:
    payload = {"text": "<!channel> Deployment starting now <!here>"}
    alert = SlackPayloadParser.parse(payload)

    assert alert.text == "@room Deployment starting now @room"


def test_parse_attachments_with_severity_and_fields() -> None:
    payload = {
        "text": "Alert triggered",
        "channel": "!alert_room:agent.tchap.gouv.fr",
        "attachments": [
            {
                "color": "danger",
                "title": "High CPU utilization",
                "title_link": "https://monitor.gouv.fr/alerts/cpu",
                "text": "CPU exceeds 95% threshold",
                "author_name": "Prometheus",
                "fields": [
                    {"title": "Host", "value": "node-01.infra", "short": True},
                    {"title": "Current Load", "value": "98.4%", "short": True},
                ],
                "footer": "Infrastructure Monitoring",
                "ts": 1726400000,
            }
        ],
    }
    alert = SlackPayloadParser.parse(payload)

    assert alert.text == "Alert triggered"
    assert alert.channel_override == "!alert_room:agent.tchap.gouv.fr"
    assert alert.severity == AlertSeverity.DANGER
    assert len(alert.attachments) == 1

    att = alert.attachments[0]
    assert att.title == "High CPU utilization"
    assert att.title_link == "https://monitor.gouv.fr/alerts/cpu"
    assert att.author_name == "Prometheus"
    assert att.text == "CPU exceeds 95% threshold"
    assert att.color == "danger"
    assert len(att.fields) == 2
    assert att.fields[0].title == "Host"
    assert att.fields[0].value == "node-01.infra"
    assert att.fields[1].title == "Current Load"
    assert att.fields[1].value == "98.4%"
    assert att.footer == "Infrastructure Monitoring"
    assert att.ts == 1726400000


def test_parse_fallback_when_no_text_in_attachment() -> None:
    payload = {
        "attachments": [
            {
                "fallback": "Backup failed",
                "color": "warning",
            }
        ]
    }
    alert = SlackPayloadParser.parse(payload)

    assert alert.severity == AlertSeverity.WARNING
    assert len(alert.attachments) == 1
    assert alert.attachments[0].text == "Backup failed"
