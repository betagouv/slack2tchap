"""Pydantic schemas for incoming webhooks, admin management, and API responses."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SlackField(BaseModel):
    """Attachment field inside a Slack/Mattermost message."""

    title: str = Field(..., description="Field title")
    value: str = Field(..., description="Field value")
    short: bool = Field(default=False, description="Display side-by-side if short")

    model_config = ConfigDict(extra="ignore")


class SlackAttachment(BaseModel):
    """Attachment block in a Slack/Mattermost message."""

    fallback: str | None = Field(default=None, description="Plaintext summary")
    color: str | None = Field(default=None, description="Hex color or good/warning/danger")
    pretext: str | None = Field(default=None, description="Optional text preceding the attachment")
    author_name: str | None = Field(default=None, description="Author name")
    author_link: str | None = Field(default=None, description="Author profile link")
    author_icon: str | None = Field(default=None, description="Author avatar link")
    title: str | None = Field(default=None, description="Attachment title")
    title_link: str | None = Field(default=None, description="Attachment title URL link")
    text: str | None = Field(default=None, description="Attachment main body text")
    fields: list[SlackField] | None = Field(default=None, description="List of structured fields")
    footer: str | None = Field(default=None, description="Footer text")
    footer_icon: str | None = Field(default=None, description="Footer icon URL")
    ts: int | float | None = Field(default=None, description="Unix timestamp of message")

    model_config = ConfigDict(extra="ignore")


class SlackWebhookPayload(BaseModel):
    """Standard incoming webhook payload for Slack and Mattermost."""

    text: str | None = Field(default=None, description="Main message text")
    channel: str | None = Field(
        default=None,
        description="Target channel or Matrix room ID override (!room:server or #alias:server)",
    )
    username: str | None = Field(default=None, description="Custom bot username")
    icon_emoji: str | None = Field(default=None, description="Custom bot emoji")
    icon_url: str | None = Field(default=None, description="Custom bot icon URL")
    attachments: list[SlackAttachment] | None = Field(
        default=None,
        description="List of Slack attachments",
    )

    model_config = ConfigDict(extra="allow")


class WebhookResponse(BaseModel):
    """Response returned upon webhook processing."""

    ok: bool = Field(default=True, description="Slack-compatible boolean flag")
    success: bool = Field(..., description="Whether the message was successfully dispatched")
    room_id: str = Field(..., description="Target Matrix room ID")
    is_encrypted: bool = Field(
        default=False, description="Whether the target room is E2EE encrypted"
    )
    event_id: str | None = Field(
        default=None, description="Matrix event ID of the dispatched message"
    )
    error: str | None = Field(default=None, description="Error message if failed")


class MatrixAccountCreateRequest(BaseModel):
    """Request payload to register a dedicated Matrix bot account."""

    name: str = Field(..., description="Friendly name (e.g. 'Bot Supervision Prod')")
    matrix_user_id: str = Field(
        ..., description="Full Matrix user ID (e.g. '@bot:agent.tchap.gouv.fr')"
    )
    password: str | None = Field(
        default=None,
        description="Password for the bot account (will be encrypted at rest via AES-256-GCM)",
    )
    access_token: str | None = Field(
        default=None,
        description="Existing access token for the bot account (will be encrypted at rest)",
    )


class MatrixAccountResponse(BaseModel):
    """Response payload representing a registered Matrix bot account."""

    id: UUID = Field(..., description="Unique ID of the Matrix bot account")
    name: str = Field(..., description="Friendly name")
    matrix_user_id: str = Field(..., description="Full Matrix user ID")
    device_id: str = Field(..., description="Device ID assigned to this bot session")
    has_persisted_crypto_store: bool = Field(
        ..., description="Whether an E2EE SQLite store is persisted in PostgreSQL"
    )
    is_active: bool = Field(..., description="Whether this bot is active")
    created_at: str = Field(..., description="Creation ISO timestamp")


class WebhookCreateRequest(BaseModel):
    """Request payload to register a new webhook destination."""

    name: str = Field(..., description="Descriptive name (e.g. 'Alertmanager Production')")
    matrix_room_id: str = Field(
        ..., description="Target Matrix Room ID (!room:server.gouv.fr or #alias:server)"
    )
    matrix_account_id: UUID = Field(
        ..., description="ID of the registered Matrix bot account to use for sending"
    )


class WebhookDetailResponse(BaseModel):
    """Admin representation of a registered webhook endpoint."""

    id: UUID = Field(..., description="Public UUID of the webhook")
    name: str = Field(..., description="Descriptive name")
    matrix_room_id: str = Field(..., description="Target Matrix room ID")
    matrix_account_id: UUID = Field(..., description="Assigned Matrix bot account ID")
    public_url: str = Field(..., description="Full public URL to ingest Slack webhooks")
    is_active: bool = Field(..., description="Whether the webhook is actively receiving alerts")
    created_at: str = Field(..., description="Creation ISO timestamp")


class HealthResponse(BaseModel):
    """Response returned by the healthcheck endpoint."""

    status: str = Field(..., description="Gateway overall health status")
    version: str = Field(..., description="slack2tchap version")
    details: dict[str, Any] = Field(default_factory=dict, description="Operational state details")


class EmojiVerificationItem(BaseModel):
    """A single SAS verification emoji and its description."""

    emoji: str = Field(..., description="The Unicode emoji character")
    description: str = Field(..., description="The descriptive name of the emoji")


class VerificationResponse(BaseModel):
    """Response payload containing interactive SAS verification emojis."""

    status: str = Field(
        default="emojis_ready",
        description="Verification state (e.g. 'emojis_ready')",
    )
    message: str = Field(
        default="Please verify that these emojis match what is displayed in your Tchap application, then click 'They match' in Tchap.",
        description="Instructional message for the user",
    )
    account_id: UUID = Field(..., description="Matrix bot account UUID")
    transaction_id: str = Field(..., description="Matrix SAS transaction ID")
    target_device_id: str | None = Field(
        default=None, description="The device ID that partook in the verification"
    )
    emojis: list[EmojiVerificationItem] = Field(
        ..., description="List of SAS verification emojis with descriptions"
    )
    emoji_string: str = Field(
        ..., description="Joined space-separated string of the emojis for quick display"
    )


class UserCreateRequest(BaseModel):
    """Request payload to create a new user account (admin-only)."""

    email: str = Field(
        ...,
        description="Email address of the new user",
        examples=["operator@beta.gouv.fr"],
    )


class UserCreateResponse(BaseModel):
    """Response returned once after user creation, including the one-time raw API key."""

    id: UUID = Field(..., description="Unique user ID")
    email: str = Field(..., description="Email address")
    api_key_prefix: str = Field(..., description="Non-sensitive prefix of the API key for logs")
    raw_api_key: str = Field(
        ...,
        description="The generated API key. This is shown ONLY ONCE and cannot be retrieved later.",
    )
    is_admin: bool = Field(..., description="Whether the user has admin privileges")
    is_active: bool = Field(..., description="Whether the user account is active")
    created_at: str = Field(..., description="Creation ISO timestamp")
