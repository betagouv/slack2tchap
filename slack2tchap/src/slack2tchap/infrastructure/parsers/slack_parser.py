"""Slack/Mattermost payload parser for slack2tchap, imported from slack2tchap_core."""

from slack2tchap_core.infrastructure.parsers.slack_parser import (
    AttachmentPayload,
    FieldPayload,
    SlackPayloadParser,
    SlackWebhookPayload,
)

__all__ = [
    "AttachmentPayload",
    "FieldPayload",
    "SlackPayloadParser",
    "SlackWebhookPayload",
]
