import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from slack2tchap import __version__
from slack2tchap.application.dtos import (
    CreateWebhookCommand,
    RegisterMatrixAccountCommand,
    RequestDeviceVerificationCommand,
    SendPublicWebhookCommand,
)
from slack2tchap.application.use_cases import (
    CreateWebhookUseCase,
    DeleteMatrixAccountUseCase,
    DeleteWebhookUseCase,
    ListMatrixAccountsUseCase,
    ListWebhooksUseCase,
    ProcessPublicWebhookUseCase,
    RegisterMatrixAccountUseCase,
    RequestDeviceVerificationUseCase,
)
from slack2tchap.domain.exceptions import (
    DomainError,
    InvalidRoomIdError,
    MatrixAccountNotFoundError,
    VerificationTimeoutError,
    WebhookNotFoundError,
)
from slack2tchap.domain.models import User
from slack2tchap.infrastructure.parsers.slack_parser import SlackPayloadParser
from slack2tchap.interfaces.api.dependencies import (
    get_create_webhook_use_case,
    get_current_user,
    get_delete_matrix_account_use_case,
    get_delete_webhook_use_case,
    get_list_matrix_accounts_use_case,
    get_list_webhooks_use_case,
    get_process_public_webhook_use_case,
    get_register_matrix_account_use_case,
    get_request_device_verification_use_case,
)
from slack2tchap.interfaces.api.schemas import (
    EmojiVerificationItem,
    HealthResponse,
    MatrixAccountCreateRequest,
    MatrixAccountResponse,
    SlackWebhookPayload,
    VerificationResponse,
    WebhookCreateRequest,
    WebhookDetailResponse,
    WebhookResponse,
)

logger = logging.getLogger("slack2tchap.routes")

router = APIRouter()


# ============================================================================
# SYSTEM HEALTH
# ============================================================================


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    tags=["System"],
)
async def health() -> HealthResponse:
    """Check gateway operational status."""
    return HealthResponse(
        status="healthy",
        version=__version__,
        details={"mode": "stateless_multi_bot"},
    )


# ============================================================================
# PUBLIC WEBHOOK ENDPOINTS (NO CLIENT API KEY REQUIRED)
# ============================================================================


@router.post(
    "/webhook/slack/{webhook_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive incoming Slack webhook via public UUID and forward to Matrix",
    tags=["Public Webhooks"],
)
@router.post(
    "/slack/{webhook_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Short alias for incoming Slack webhook via public UUID",
    tags=["Public Webhooks"],
)
@router.post(
    "/webhook/mattermost/{webhook_id}",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive incoming Mattermost webhook via public UUID",
    tags=["Public Webhooks"],
)
async def handle_public_webhook_by_id(
    webhook_id: UUID,
    payload: SlackWebhookPayload,
    use_case: Annotated[ProcessPublicWebhookUseCase, Depends(get_process_public_webhook_use_case)],
) -> WebhookResponse:
    """Ingest Slack/Mattermost payload using registered webhook UUID without client API keys."""
    logger.info("Received incoming webhook for endpoint UUID=%s", webhook_id)
    raw_dict = payload.model_dump(exclude_unset=True)
    alert = SlackPayloadParser.parse(raw_dict)

    try:
        result = await use_case.execute(
            SendPublicWebhookCommand(webhook_id=webhook_id, alert=alert)
        )
    except WebhookNotFoundError as err:
        logger.warning("Webhook endpoint UUID=%s not found: %s", webhook_id, err)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err.message,
        ) from err
    except Exception as exc:
        logger.exception("Unexpected error processing webhook %s: %s", webhook_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to dispatch to Matrix: {exc}",
        ) from exc

    if not result.success:
        logger.warning("Failed to dispatch alert for webhook %s: %s", webhook_id, result.error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Failed to dispatch alert to Matrix room",
        )

    logger.info(
        "Successfully processed webhook UUID=%s -> Room=%s (event_id=%s)",
        webhook_id,
        result.room_id,
        result.event_id,
    )
    return WebhookResponse(
        success=result.success,
        room_id=result.room_id,
        is_encrypted=result.is_encrypted,
        event_id=result.event_id,
        error=result.error,
    )


# ============================================================================
# ADMIN ENDPOINTS: MATRIX BOT ACCOUNTS (AUTHENTICATED VIA API KEY)
# ============================================================================


@router.post(
    "/api/v1/admin/matrix-accounts",
    response_model=MatrixAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a dedicated Matrix bot account",
    tags=["Admin Matrix Accounts"],
)
async def register_matrix_account(
    request: MatrixAccountCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[
        RegisterMatrixAccountUseCase, Depends(get_register_matrix_account_use_case)
    ],
) -> MatrixAccountResponse:
    """Register a new Matrix bot. Credentials are encrypted at rest with AES-256-GCM."""
    try:
        dto = await use_case.execute(
            RegisterMatrixAccountCommand(
                name=request.name,
                matrix_user_id=request.matrix_user_id,
                user_id=current_user.id,
                password=request.password,
                access_token=request.access_token,
            )
        )
    except DomainError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err.message,
        ) from err

    return MatrixAccountResponse(
        id=dto.id,
        name=dto.name,
        matrix_user_id=dto.matrix_user_id,
        device_id=dto.device_id,
        has_persisted_crypto_store=dto.has_persisted_crypto_store,
        is_active=dto.is_active,
        created_at=dto.created_at,
    )


@router.get(
    "/api/v1/admin/matrix-accounts",
    response_model=list[MatrixAccountResponse],
    summary="List all registered Matrix bots for the authenticated user",
    tags=["Admin Matrix Accounts"],
)
async def list_matrix_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[ListMatrixAccountsUseCase, Depends(get_list_matrix_accounts_use_case)],
) -> list[MatrixAccountResponse]:
    """Retrieve all configured Matrix bots belonging to the current user."""
    accounts = await use_case.execute(current_user.id)
    return [
        MatrixAccountResponse(
            id=acc.id,
            name=acc.name,
            matrix_user_id=acc.matrix_user_id,
            device_id=acc.device_id,
            has_persisted_crypto_store=acc.has_persisted_crypto_store,
            is_active=acc.is_active,
            created_at=acc.created_at,
        )
        for acc in accounts
    ]


@router.delete(
    "/api/v1/admin/matrix-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Matrix bot account by ID",
    tags=["Admin Matrix Accounts"],
)
async def delete_matrix_account(
    account_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[DeleteMatrixAccountUseCase, Depends(get_delete_matrix_account_use_case)],
) -> None:
    """Delete a configured Matrix bot account."""
    try:
        await use_case.execute(account_id, current_user.id)
    except MatrixAccountNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err.message,
        ) from err


# ============================================================================
# BOT VERIFICATION ENDPOINTS (INTERACTIVE SAS KEY VERIFICATION)
# ============================================================================


@router.post(
    "/verify/{bot_uuid}",
    response_model=VerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate interactive SAS device verification for a bot and return emojis",
    tags=["Bot Verification"],
)
@router.post(
    "/api/v1/matrix-accounts/{bot_uuid}/verify",
    response_model=VerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate interactive SAS device verification for a bot (RESTful alias)",
    tags=["Bot Verification"],
)
async def verify_bot_path(
    bot_uuid: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[
        RequestDeviceVerificationUseCase,
        Depends(get_request_device_verification_use_case),
    ],
    device_id: Annotated[
        str | None, Query(description="Optional target device ID to verify")
    ] = None,
    timeout_seconds: Annotated[
        int,
        Query(
            alias="timeout",
            ge=5,
            le=120,
            description="Timeout in seconds to wait for emojis",
        ),
    ] = 30,
) -> VerificationResponse:
    """Trigger an interactive SAS device verification with the bot and return the emojis."""
    try:
        dto = await use_case.execute(
            RequestDeviceVerificationCommand(
                account_id=bot_uuid,
                user_id=current_user.id,
                target_device_id=device_id,
                timeout_seconds=float(timeout_seconds),
            )
        )
    except MatrixAccountNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err.message,
        ) from err
    except VerificationTimeoutError as err:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=err.message,
        ) from err
    except DomainError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err.message,
        ) from err

    emoji_items = [EmojiVerificationItem(emoji=item[0], description=item[1]) for item in dto.emojis]
    emoji_str = " ".join(item[0] for item in dto.emojis)

    return VerificationResponse(
        status="emojis_ready",
        message=(
            "Please compare these emojis with the ones displayed on your Tchap client, "
            "then confirm in Tchap ('They match')."
        ),
        account_id=dto.account_id,
        transaction_id=dto.transaction_id,
        target_device_id=dto.target_device_id,
        emojis=emoji_items,
        emoji_string=emoji_str,
    )


@router.post(
    "/verify",
    response_model=VerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate interactive SAS device verification via bot_uuid query parameter",
    tags=["Bot Verification"],
)
async def verify_bot_query(
    bot_uuid: Annotated[UUID, Query(description="UUID of the Matrix bot account")],
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[
        RequestDeviceVerificationUseCase,
        Depends(get_request_device_verification_use_case),
    ],
    device_id: Annotated[
        str | None, Query(description="Optional target device ID to verify")
    ] = None,
    timeout_seconds: Annotated[
        int,
        Query(
            alias="timeout",
            ge=5,
            le=120,
            description="Timeout in seconds to wait for emojis",
        ),
    ] = 30,
) -> VerificationResponse:
    """Trigger an interactive SAS device verification via query param and return emojis."""
    return await verify_bot_path(
        bot_uuid=bot_uuid,
        current_user=current_user,
        use_case=use_case,
        device_id=device_id,
        timeout_seconds=timeout_seconds,
    )


# ============================================================================
# ADMIN ENDPOINTS: WEBHOOKS (AUTHENTICATED VIA API KEY)
# ============================================================================


@router.post(
    "/api/v1/admin/webhooks",
    response_model=WebhookDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new webhook destination mapped to a Matrix room and bot",
    tags=["Admin Webhooks"],
)
async def create_webhook(
    request: WebhookCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[CreateWebhookUseCase, Depends(get_create_webhook_use_case)],
) -> WebhookDetailResponse:
    """Declare a new webhook endpoint assigned to a Matrix room and configured bot."""
    try:
        dto = await use_case.execute(
            CreateWebhookCommand(
                name=request.name,
                matrix_room_id=request.matrix_room_id,
                matrix_account_id=request.matrix_account_id,
                user_id=current_user.id,
            )
        )
    except (InvalidRoomIdError, MatrixAccountNotFoundError) as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err.message,
        ) from err

    return WebhookDetailResponse(
        id=dto.id,
        name=dto.name,
        matrix_room_id=dto.matrix_room_id,
        matrix_account_id=dto.matrix_account_id,
        public_url=dto.public_url,
        is_active=dto.is_active,
        created_at=dto.created_at,
    )


@router.get(
    "/api/v1/admin/webhooks",
    response_model=list[WebhookDetailResponse],
    summary="List all webhooks owned by the authenticated user",
    tags=["Admin Webhooks"],
)
async def list_webhooks(
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[ListWebhooksUseCase, Depends(get_list_webhooks_use_case)],
) -> list[WebhookDetailResponse]:
    """Retrieve all webhooks belonging to the current user."""
    webhooks = await use_case.execute(current_user.id)
    return [
        WebhookDetailResponse(
            id=w.id,
            name=w.name,
            matrix_room_id=w.matrix_room_id,
            matrix_account_id=w.matrix_account_id,
            public_url=w.public_url,
            is_active=w.is_active,
            created_at=w.created_at,
        )
        for w in webhooks
    ]


@router.delete(
    "/api/v1/admin/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a webhook by UUID",
    tags=["Admin Webhooks"],
)
async def delete_webhook(
    webhook_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[DeleteWebhookUseCase, Depends(get_delete_webhook_use_case)],
) -> None:
    """Delete a webhook destination."""
    try:
        await use_case.execute(webhook_id, current_user.id)
    except WebhookNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err.message,
        ) from err
