"""Parser and schemas for Slack and Mattermost incoming webhook payloads."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from slack2tchap_core.domain.models import (
    AlertAttachment,
    AlertField,
    AlertMessage,
    AlertSeverity,
)


class FieldPayload(BaseModel):
    """Slack attachment field item."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., description="Title of the field item")
    value: str = Field(..., description="Value of the field item")
    short: bool = Field(default=False, description="Whether value is short")


class AttachmentPayload(BaseModel):
    """Slack attachment block."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, description="Attachment title")
    title_link: str | None = Field(default=None, description="URL hyperlink for title")
    text: str | None = Field(default=None, description="Attachment main body")
    fallback: str | None = Field(default=None, description="Fallback plain text description")
    color: str | None = Field(
        default=None, description="Color indicator (hex #36a64f or keyword good/warning/danger)"
    )
    author_name: str | None = Field(default=None, description="Small author label")
    footer: str | None = Field(default=None, description="Small footer text")
    ts: int | None = Field(default=None, description="Epoch timestamp")
    fields: list[FieldPayload] = Field(default_factory=list, description="Key-value fields")


class SlackWebhookPayload(BaseModel):
    """Standard incoming webhook payload conforming to Slack / Mattermost format."""

    model_config = ConfigDict(extra="ignore")

    text: str | None = Field(
        default=None,
        description="Main text message content",
        examples=["Serveur de production injoignable."],
    )
    attachments: list[AttachmentPayload] = Field(
        default_factory=list,
        description="Optional list of rich attachment sections",
    )
    channel: str | None = Field(
        default=None,
        description="Target Matrix Room ID or alias override (!room:matrix.org)",
    )
    username: str | None = Field(
        default=None,
        description="Sender nickname override (for Slack compatibility)",
    )
    icon_emoji: str | None = Field(default=None, description="Sender emoji icon")
    icon_url: str | None = Field(default=None, description="Sender image icon URL")


class SlackPayloadParser:
    """Transforms Slack / Mattermost webhook payloads into pure domain AlertMessage."""

    # Regex for Slack mrkdwn links: <https://example.com|Title> or <https://example.com>
    SLACK_LINK_WITH_TITLE_RE = re.compile(r"<([^|>]+)\|([^>]+)>")
    SLACK_BARE_LINK_RE = re.compile(r"<([^|>]+)>")
    SLACK_SPECIAL_RE = re.compile(r"<!(here|channel|everyone)>")

    @classmethod
    def clean_slack_text(cls, text: str | None) -> str:
        """Convert Slack mrkdwn specific tokens into standard Markdown."""
        if not text:
            return ""

        # Replace <!here>, <!channel>, <!everyone> with @room
        converted = cls.SLACK_SPECIAL_RE.sub(r"@room", text)

        # Replace <URL|Title> with [Title](URL)
        converted = cls.SLACK_LINK_WITH_TITLE_RE.sub(r"[\2](\1)", converted)

        # Replace bare links <URL> with URL
        converted = cls.SLACK_BARE_LINK_RE.sub(r"\1", converted)

        return converted.strip()

    @classmethod
    def parse(cls, payload: dict[str, Any] | SlackWebhookPayload) -> AlertMessage:
        """Parse raw JSON dict or Pydantic payload from Slack / Mattermost into an AlertMessage."""
        data: dict[str, Any] = payload.model_dump() if isinstance(payload, BaseModel) else payload

        raw_text = data.get("text")
        cleaned_main_text = cls.clean_slack_text(str(raw_text) if raw_text is not None else None)

        channel_override = data.get("channel")
        channel_str: str | None = str(channel_override).strip() if channel_override else None

        attachments_data = data.get("attachments") or []
        attachments: list[AlertAttachment] = []
        highest_severity = AlertSeverity.INFO

        if isinstance(attachments_data, list):
            for item in attachments_data:
                if not isinstance(item, dict):
                    continue

                color = str(item.get("color", "")).strip() if item.get("color") else None
                severity = AlertSeverity.from_slack_color(color)
                if severity != AlertSeverity.INFO:
                    highest_severity = severity

                title = str(item.get("title")).strip() if item.get("title") else None
                title_link = str(item.get("title_link")).strip() if item.get("title_link") else None

                att_text = cls.clean_slack_text(
                    str(item.get("text")) if item.get("text") is not None else None
                )
                if not att_text and item.get("fallback"):
                    att_text = cls.clean_slack_text(str(item.get("fallback")))

                author_name = (
                    str(item.get("author_name")).strip() if item.get("author_name") else None
                )
                footer = str(item.get("footer")).strip() if item.get("footer") else None

                ts_raw = item.get("ts")
                ts: int | None = None
                if ts_raw is not None:
                    try:
                        ts = int(ts_raw)
                    except (ValueError, TypeError):
                        pass

                raw_fields = item.get("fields") or []
                fields: list[AlertField] = []
                if isinstance(raw_fields, list):
                    for f in raw_fields:
                        if isinstance(f, dict) and "title" in f and "value" in f:
                            f_title = str(f.get("title", "")).strip()
                            f_val = cls.clean_slack_text(str(f.get("value", "")))
                            f_short = bool(f.get("short", False))
                            fields.append(
                                AlertField(
                                    title=f_title,
                                    value=f_val,
                                    short=f_short,
                                )
                            )

                attachments.append(
                    AlertAttachment(
                        title=title,
                        title_link=title_link,
                        text=att_text if att_text else None,
                        color=color,
                        fields=fields,
                        author_name=author_name,
                        footer=footer,
                        ts=ts,
                    )
                )

        return AlertMessage(
            text=cleaned_main_text,
            severity=highest_severity,
            attachments=attachments,
            channel_override=channel_str,
        )
