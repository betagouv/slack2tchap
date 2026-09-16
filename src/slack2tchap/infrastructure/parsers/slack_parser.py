"""Parser for Slack and Mattermost incoming webhook payloads into Domain models."""

import re
from typing import Any

from slack2tchap.domain.models import (
    AlertAttachment,
    AlertField,
    AlertMessage,
    AlertSeverity,
)


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
    def parse(cls, payload: dict[str, Any]) -> AlertMessage:
        """Parse raw JSON dict payload from Slack / Mattermost into an AlertMessage."""
        raw_text = payload.get("text")
        cleaned_main_text = cls.clean_slack_text(str(raw_text) if raw_text is not None else None)

        channel_override = payload.get("channel")
        channel_str: str | None = str(channel_override).strip() if channel_override else None

        attachments_data = payload.get("attachments") or []
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
