"""Pure domain models for alerts, messages, users and matrix accounts."""

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

import markdown


class AlertSeverity(StrEnum):
    """Normalized severity level for an alert."""

    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    DANGER = "DANGER"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_slack_color(cls, color: str | None) -> "AlertSeverity":
        """Map Slack color string or hex to AlertSeverity."""
        if not color:
            return cls.INFO

        cleaned = color.strip().lower()
        if cleaned in ("good", "#36a64f", "#2eb886", "green"):
            return cls.SUCCESS
        if cleaned in ("warning", "#daa038", "#ffcc00", "yellow", "orange"):
            return cls.WARNING
        if cleaned in ("danger", "#de4343", "#a30200", "red"):
            return cls.DANGER
        return cls.INFO


@dataclass(frozen=True)
class RoomId:
    """Value object representing a Matrix Room ID or Alias."""

    value: str

    def __post_init__(self) -> None:
        trimmed = self.value.strip()
        # Matrix room IDs start with '!' or room aliases with '#'
        if not re.match(r"^[!#][a-zA-Z0-9_\.\=\-\/]+:[a-zA-Z0-9\.\-]+(?::\d+)?$", trimmed):
            raise ValueError(f"Invalid Matrix Room ID or Alias: '{self.value}'")
        object.__setattr__(self, "value", trimmed)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AlertField:
    """Key-value field in an alert attachment."""

    title: str
    value: str
    short: bool = False


@dataclass(frozen=True)
class AlertAttachment:
    """Attachment block in an alert message."""

    title: str | None = None
    title_link: str | None = None
    pretext: str | None = None
    text: str | None = None
    color: str | None = None
    fields: list[AlertField] = field(default_factory=list)
    author_name: str | None = None
    footer: str | None = None
    ts: int | None = None


@dataclass(frozen=True)
class AlertMessage:
    """Core domain notification message."""

    text: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    attachments: list[AlertAttachment] = field(default_factory=list)
    channel_override: str | None = None

    def _severity_badge(self) -> str:
        """Return an emoji and label for the severity."""
        match self.severity:
            case AlertSeverity.SUCCESS:
                return "🟢 [OK]"
            case AlertSeverity.WARNING:
                return "🟡 [WARNING]"
            case AlertSeverity.DANGER:
                return "🔴 [DANGER]"
            case AlertSeverity.CRITICAL:
                return "🚨 [CRITICAL]"
            case AlertSeverity.INFO:
                return "ℹ️ [INFO]"

    def _severity_color_hex(self) -> str:
        """Return HTML color hex for Matrix pills."""
        match self.severity:
            case AlertSeverity.SUCCESS:
                return "#2eb886"
            case AlertSeverity.WARNING:
                return "#daa038"
            case AlertSeverity.DANGER | AlertSeverity.CRITICAL:
                return "#de4343"
            case AlertSeverity.INFO:
                return "#439fe0"

    @classmethod
    def resolve_color_hex(cls, color: str | None, default_hex: str) -> str:
        """Resolve a Slack color string or keyword into a valid CSS hex color."""
        if not color:
            return default_hex
        cleaned = color.strip()
        if cleaned.startswith("#") and len(cleaned) in (4, 7):
            return cleaned
        sev = AlertSeverity.from_slack_color(cleaned)
        match sev:
            case AlertSeverity.SUCCESS:
                return "#2eb886"
            case AlertSeverity.WARNING:
                return "#daa038"
            case AlertSeverity.DANGER | AlertSeverity.CRITICAL:
                return "#de4343"
            case AlertSeverity.INFO:
                return default_hex

    def to_plain_text(self) -> str:
        """Render pure plain text message for fallback clients."""
        parts: list[str] = []
        if self.severity != AlertSeverity.INFO:
            badge = self._severity_badge()
            if self.text:
                parts.append(f"{badge} {self.text}")
            elif self.attachments:
                parts.append(badge)
        elif self.text:
            parts.append(self.text)

        for att in self.attachments:
            att_lines: list[str] = []
            if att.pretext:
                att_lines.append(att.pretext)
            if att.author_name:
                att_lines.append(f"Author: {att.author_name}")
            if att.title:
                if att.title_link:
                    att_lines.append(f"**{att.title}** ({att.title_link})")
                else:
                    att_lines.append(f"**{att.title}**")
            if att.text:
                att_lines.append(att.text)
            for f in att.fields:
                att_lines.append(f"- {f.title}: {f.value}")
            if att.footer:
                att_lines.append(f"_{att.footer}_")
            if att_lines:
                parts.append("\n".join(att_lines))

        return "\n\n".join(parts).strip()

    def to_matrix_html(self) -> str:
        """Render Matrix-compliant HTML (org.matrix.custom.html)."""
        color_hex = self._severity_color_hex()
        badge_text = html.escape(self._severity_badge())

        parts: list[str] = []
        header_html = f'<font color="{color_hex}"><strong>{badge_text}</strong></font>'

        if self.text:
            converted_text = markdown.markdown(self.text, extensions=["tables"]).strip()
            # Only prepend alert badge if severity is not standard INFO
            if self.severity != AlertSeverity.INFO:
                parts.append(f"<p>{header_html} {converted_text}</p>")
            else:
                parts.append(converted_text)
        elif not self.attachments and self.severity != AlertSeverity.INFO:
            parts.append(f"<p>{header_html}</p>")

        for att in self.attachments:
            if att.pretext:
                pretext_html = markdown.markdown(att.pretext, extensions=["tables"]).strip()
                parts.append(pretext_html)

            att_parts: list[str] = []
            if att.author_name:
                att_parts.append(f"<small>{html.escape(att.author_name)}</small>")

            if att.title:
                escaped_title = html.escape(att.title)
                if att.title_link:
                    escaped_link = html.escape(att.title_link, quote=True)
                    att_parts.append(f'<h4><a href="{escaped_link}">{escaped_title}</a></h4>')
                else:
                    att_parts.append(f"<h4>{escaped_title}</h4>")

            if att.text:
                text_html = markdown.markdown(att.text, extensions=["tables"]).strip()
                att_parts.append(text_html)

            if att.fields:
                table_rows: list[str] = []
                for f in att.fields:
                    f_title = html.escape(f.title)
                    f_val = html.escape(f.value).replace("\n", "<br />")
                    table_rows.append(
                        f"<tr><td><strong>{f_title}</strong></td><td>{f_val}</td></tr>"
                    )
                att_parts.append(f"<table><tbody>{''.join(table_rows)}</tbody></table>")

            if att.footer:
                att_parts.append(f"<small><em>{html.escape(att.footer)}</em></small>")

            if att_parts:
                att_html = "".join(att_parts)
                border_color = self.resolve_color_hex(att.color, color_hex)
                parts.append(
                    f'<blockquote style="border-left: 4px solid {border_color}; margin: 8px 0; padding-left: 8px;">'
                    f"{att_html}"
                    f"</blockquote>"
                )

        return "".join(parts)


@dataclass
class User:
    """Domain representation of an authenticated user / administrator."""

    email: str
    api_key_hash: str
    api_key_prefix: str
    id: UUID = field(default_factory=uuid4)
    is_admin: bool = False
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MatrixCredentials:
    """Cleartext credentials for a specific Matrix user (only transiently in memory)."""

    user_id: str | None = None
    password: str | None = None
    access_token: str | None = None


@dataclass
class MatrixAccount:
    """Configured Matrix bot account with encrypted credentials and persisted E2EE crypto store."""

    name: str
    matrix_user_id: str
    user_id: UUID
    id: UUID = field(default_factory=uuid4)
    device_id: str = field(default_factory=lambda: f"s2t_{uuid4().hex[:12]}")
    encrypted_password: str | None = None
    encrypted_access_token: str | None = None
    encryption_nonce: str | None = None
    crypto_store_blob: bytes | None = None
    crypto_store_updated_at: datetime | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class WebhookEndpoint:
    """Registered webhook destination with public UUID, target room, and assigned Matrix bot."""

    name: str
    matrix_room_id: str
    matrix_account_id: UUID
    user_id: UUID
    id: UUID = field(default_factory=uuid4)
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
