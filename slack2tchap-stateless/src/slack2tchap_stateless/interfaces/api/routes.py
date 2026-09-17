"""FastAPI routes for the stateless webhook gateway."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from slack2tchap_core.domain.exceptions import (
    AuthenticationError,
    CipherError,
    DomainError,
    InvalidRoomIdError,
    MessageSendError,
)
from slack2tchap_core.infrastructure.parsers.slack_parser import (
    SlackPayloadParser,
    SlackWebhookPayload,
)
from slack2tchap_stateless.application.dtos import SendStatelessWebhookCommand
from slack2tchap_stateless.application.use_cases import ProcessStatelessWebhookUseCase
from slack2tchap_stateless.interfaces.api.dependencies import (
    get_process_stateless_webhook_use_case,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def healthcheck() -> dict[str, Any]:
    """Basic health probe endpoint."""
    return {"status": "healthy", "mode": "stateless"}


@router.post(
    "/slack",
    status_code=status.HTTP_200_OK,
    tags=["Stateless Webhooks"],
    summary="Ingest incoming Slack / Mattermost webhook payload in stateless mode",
)
@router.post(
    "/webhook/slack",
    status_code=status.HTTP_200_OK,
    tags=["Stateless Webhooks"],
    include_in_schema=False,
)
async def handle_stateless_slack_webhook(
    payload: SlackWebhookPayload,
    param: Annotated[
        str,
        Query(
            description="Encrypted AES-256-GCM token containing Matrix bot username, password and channelID",
        ),
    ],
    use_case: Annotated[
        ProcessStatelessWebhookUseCase, Depends(get_process_stateless_webhook_use_case)
    ],
) -> dict[str, Any]:
    """Ingest a Slack/Mattermost alert and dispatch it directly to Matrix using credentials from the token."""
    alert = SlackPayloadParser.parse(payload)
    command = SendStatelessWebhookCommand(param_token=param, alert=alert)

    try:
        event_id = await use_case.execute(command)
        return {
            "status": "success",
            "message": "Stateless alert dispatched to Matrix room",
            "event_id": event_id,
        }
    except CipherError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or tampered stateless token: {exc}",
        ) from exc
    except InvalidRoomIdError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Matrix authentication failed: {exc}",
        ) from exc
    except MessageSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to deliver message to Matrix: {exc}",
        ) from exc
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error in stateless webhook ingestion: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing stateless alert.",
        ) from exc
