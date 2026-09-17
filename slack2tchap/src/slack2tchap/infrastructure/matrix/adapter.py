"""Matrix-nio adapter implementing MatrixMessengerPort with full E2EE support."""

import asyncio
import logging
import ssl
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import certifi
from nio import (
    AsyncClient,
    AsyncClientConfig,
    InviteMemberEvent,
    JoinError,
    KeyVerificationCancel,
    KeyVerificationKey,
    KeyVerificationMac,
    KeyVerificationStart,
    LoginError,
    MatrixRoom,
    RoomSendError,
    RoomSendResponse,
    SyncError,
    ToDeviceError,
    ToDeviceMessage,
    UnknownToDeviceEvent,
)

from slack2tchap.domain.exceptions import (
    AuthenticationError,
    CryptoStoreError,
    MatrixClientError,
    MessageSendError,
    RoomNotFoundError,
    VerificationTimeoutError,
)
from slack2tchap.domain.ports import MatrixMessengerPort
from slack2tchap.infrastructure.matrix.patches import apply_matrix_nio_patches

logger = logging.getLogger(__name__)

# Apply matrix-nio SAS commitment patch (issue #570)
apply_matrix_nio_patches()


class MatrixNioAdapter(MatrixMessengerPort):
    """Adapter wrapping matrix-nio AsyncClient with Olm/Megolm encryption and SQLite persistence."""

    def __init__(
        self,
        homeserver: str,
        user_id: str,
        device_id: str,
        store_path: Path,
        store_passphrase: str,
        password: str | None = None,
        access_token: str | None = None,
        auto_join: bool = True,
        on_verified: Callable[[], Awaitable[None]] | None = None,
        on_store_changed: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._homeserver = homeserver
        self._user_id = user_id
        self._device_id = device_id
        self._store_path = store_path
        self._store_passphrase = store_passphrase
        self._password = password
        self._access_token = access_token
        self._auto_join = auto_join
        self._on_verified = on_verified
        self._on_store_changed = on_store_changed

        # Enforce SQLite store persistence
        if not self._store_path:
            raise CryptoStoreError("Store path must be specified to persist cryptographic keys.")

        self._store_path.mkdir(parents=True, exist_ok=True)

        client_config = AsyncClientConfig(
            max_limit_exceeded=0,
            max_timeouts=0,
            store_sync_tokens=True,
            encryption_enabled=True,
        )

        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._client = AsyncClient(
            homeserver=self._homeserver,
            user=self._user_id,
            device_id=self._device_id,
            store_path=str(self._store_path),
            config=client_config,
            ssl=cast(Any, ssl_context),
        )

        self._sync_task: asyncio.Task[None] | None = None
        self._is_started = False
        self._is_verifying: bool = False
        self._pending_verification_request: dict[str, Any] | None = None
        self._pending_verification_start: KeyVerificationStart | None = None
        self._current_verification_future: (
            asyncio.Future[tuple[str, list[tuple[str, str]], str | None]] | None
        ) = None
        self._latest_verification_result: (
            tuple[str, list[tuple[str, str]], str | None, float] | None
        ) = None

    async def _notify_store_changed(self) -> None:
        """Trigger persistence hook whenever the SQLite crypto store might have been updated."""
        if self._on_store_changed:
            try:
                await self._on_store_changed()
            except Exception as exc:
                logger.warning("Error in on_store_changed notification: %s", exc)

    async def start(self) -> None:
        """Initialize client, authenticate, load Olm store, and start background sync."""
        if self._is_started:
            return

        logger.info(
            "Initializing Matrix client for %s (device: %s)", self._user_id, self._device_id
        )

        # Authenticate via token or password
        if self._access_token:
            self._client.access_token = self._access_token
            self._client.user_id = self._user_id
            self._client.device_id = self._device_id
            logger.info("Configured Matrix client with provided access token")
        elif self._password:
            logger.info("Authenticating with Matrix homeserver via password")
            resp = await self._client.login(
                password=self._password,
                device_name=self._device_id,
            )
            if isinstance(resp, LoginError):
                raise AuthenticationError(
                    f"Failed to authenticate with Matrix homeserver: {resp.message} (status: {resp.status_code})"
                )
            logger.info("Successfully logged in as %s", self._user_id)
        else:
            raise AuthenticationError(
                "Neither password nor access_token was provided for Matrix authentication."
            )

        # Ensure SQLite crypto store is loaded with authenticated credentials
        try:
            self._client.load_store()
        except Exception as exc:
            logger.warning("Error loading crypto store after login: %s", exc)

        # Upload E2EE device identity and one-time keys to Matrix homeserver
        if self._client.should_upload_keys:
            logger.info("Uploading E2EE device and one-time keys to Matrix homeserver...")
            await self._client.keys_upload()
            logger.info("E2EE keys successfully uploaded to homeserver.")

        if self._client.olm:
            fingerprint = self._client.olm.account.identity_keys.get("ed25519", "unknown")
            logger.info(
                "E2EE active: device_id=%s, ed25519_fingerprint=%s",
                self._client.device_id,
                fingerprint,
            )

        # Register auto-join callback if enabled
        if self._auto_join:
            # Cast event filter due to matrix-nio event inheritance typing limitation
            self._client.add_event_callback(self._on_invite, cast(Any, InviteMemberEvent))
            logger.info("Registered auto-join handler on invite")

        # Register to-device callbacks for interactive device verification (SAS)
        self._client.add_to_device_callback(
            cast(Any, self._on_to_device),
            cast(
                Any,
                (
                    KeyVerificationStart,
                    KeyVerificationKey,
                    KeyVerificationMac,
                    KeyVerificationCancel,
                    UnknownToDeviceEvent,
                ),
            ),
        )
        logger.info("Registered to-device verification handlers (SAS)")

        # Initial sync to populate room list and crypto keys
        logger.info("Performing initial Matrix sync...")
        sync_resp = await self._client.sync(timeout=30000, full_state=True)
        if isinstance(sync_resp, SyncError):
            logger.warning("Initial sync returned error: %s", sync_resp.message)
        else:
            logger.info("Initial sync completed. Known rooms: %d", len(self._client.rooms))

        # Re-check key upload after initial sync
        if self._client.should_upload_keys:
            await self._client.keys_upload()

        # Launch background continuous sync loop
        self._sync_task = asyncio.create_task(self._sync_loop(), name="matrix-sync-loop")
        self._is_started = True
        await self._notify_store_changed()

    async def _on_invite(self, room: MatrixRoom, event: Any) -> None:
        """Callback to automatically accept room invitations."""
        if not self._auto_join:
            return

        # Check if the invite event targets our user
        if event.state_key == self._user_id:
            logger.info("Received invitation to room %s, accepting...", room.room_id)
            join_resp = await self._client.join(room.room_id)
            if isinstance(join_resp, JoinError):
                logger.error("Failed to auto-join room %s: %s", room.room_id, join_resp.message)
            else:
                logger.info("Successfully joined room %s on invitation", room.room_id)
                await self._notify_store_changed()

    async def _send_verification_ready(
        self, recipient: str, recipient_device: str, tx_id: str
    ) -> None:
        """Send m.key.verification.ready to accept an incoming verification request."""
        logger.info(
            "Sending m.key.verification.ready to device %s (tx: %s)...",
            recipient_device,
            tx_id,
        )
        ready_msg = ToDeviceMessage(
            type="m.key.verification.ready",
            recipient=recipient,
            recipient_device=recipient_device,
            content={
                "from_device": self._device_id,
                "methods": ["m.sas.v1"],
                "transaction_id": tx_id,
            },
        )
        resp = await self._client.to_device(ready_msg)
        if isinstance(resp, ToDeviceError):
            logger.error("Failed to send m.key.verification.ready: %s", resp)

    async def _accept_verification(self, transaction_id: str) -> None:
        """Accept incoming KeyVerificationStart."""
        logger.info("Accepting SAS verification start offer (tx: %s)...", transaction_id)
        resp = await self._client.accept_key_verification(transaction_id)
        if isinstance(resp, ToDeviceError):
            logger.error("accept_key_verification failed: %s", resp)

    async def _on_to_device(self, event: Any) -> None:
        """Handle to-device interactive key verification (SAS) events."""
        try:
            if isinstance(event, UnknownToDeviceEvent):
                # Handle m.key.verification.request from modern Element / Tchap clients
                if event.type == "m.key.verification.request" and event.sender == self._user_id:
                    content: dict[str, Any] = event.source.get("content", {})
                    from_device = content.get("from_device")
                    tx_id = content.get("transaction_id")
                    if from_device and tx_id:
                        logger.info(
                            "Received verification request from device %s (tx: %s)",
                            from_device,
                            tx_id,
                        )
                        self._latest_verification_result = None
                        self._pending_verification_request = {
                            "sender": event.sender,
                            "from_device": from_device,
                            "transaction_id": tx_id,
                            "timestamp": time.time(),
                        }
                        if self._is_verifying:
                            await self._send_verification_ready(event.sender, from_device, tx_id)
                        else:
                            logger.info(
                                "Verification request saved. Waiting for /verify API call to proceed..."
                            )
                elif event.type == "m.key.verification.done":
                    logger.info(
                        "Received m.key.verification.done from device %s (tx: %s)",
                        event.sender,
                        event.source.get("content", {}).get("transaction_id"),
                    )

            elif isinstance(event, KeyVerificationStart):
                if event.sender != self._user_id:
                    logger.warning(
                        "Ignoring verification request from non-owner sender %s",
                        event.sender,
                    )
                    return

                logger.info(
                    "Received SAS verification start from device %s (tx: %s)",
                    event.from_device,
                    event.transaction_id,
                )
                self._latest_verification_result = None
                self._pending_verification_start = event
                if self._is_verifying:
                    await self._accept_verification(event.transaction_id)
                else:
                    logger.info(
                        "Verification start saved. Waiting for /verify API call to proceed..."
                    )

            elif isinstance(event, KeyVerificationKey):
                sas = self._client.key_verifications.get(event.transaction_id)
                if not sas:
                    return

                # Send out queued to-device messages immediately (sas.share_key())
                # so Tchap receives our public key to compute and display the emojis
                if self._client.outgoing_to_device_messages:
                    logger.info(
                        "Sending queued to-device messages (sharing SAS pubkey with device %s)...",
                        sas.other_olm_device.id,
                    )
                    await self._client.send_to_device_messages()

                emojis = sas.get_emoji()
                logger.info(
                    "🔐 SAS Key Verification for bot %s with device %s! Emojis: %s",
                    self._user_id,
                    sas.other_olm_device.id,
                    emojis,
                )

                # Store result with timestamp for instant retrieval
                self._latest_verification_result = (
                    event.transaction_id,
                    emojis,
                    sas.other_olm_device.id,
                    time.time(),
                )

                # Resolve waiting future if present
                if (
                    self._current_verification_future
                    and not self._current_verification_future.done()
                ):
                    self._current_verification_future.set_result(
                        (event.transaction_id, emojis, sas.other_olm_device.id)
                    )

                # Give Tchap client time to process key and display emojis before sending MAC
                await asyncio.sleep(0.5)
                confirm_resp = await self._client.confirm_short_auth_string(event.transaction_id)
                if isinstance(confirm_resp, ToDeviceError):
                    logger.error("confirm_short_auth_string failed: %s", confirm_resp)

            elif isinstance(event, KeyVerificationMac):
                sas = self._client.key_verifications.get(event.transaction_id)
                if not sas:
                    return

                logger.info(
                    "✅ SAS key verification successful! Device %s is now verified for bot %s.",
                    sas.other_olm_device.id,
                    self._user_id,
                )
                self._client.verify_device(sas.other_olm_device)

                # Conforming to MSC2241: Send m.key.verification.done so Tchap Web marks verification completed
                logger.info(
                    "Sending m.key.verification.done to device %s (tx: %s)...",
                    sas.other_olm_device.id,
                    event.transaction_id,
                )
                done_msg = ToDeviceMessage(
                    type="m.key.verification.done",
                    recipient=sas.other_olm_device.user_id,
                    recipient_device=sas.other_olm_device.id,
                    content={
                        "transaction_id": event.transaction_id,
                    },
                )
                resp = await self._client.to_device(done_msg)
                if isinstance(resp, ToDeviceError):
                    logger.error("Failed to send m.key.verification.done: %s", resp)
                else:
                    logger.info(
                        "Successfully sent m.key.verification.done to %s", sas.other_olm_device.id
                    )

                if self._on_verified:
                    try:
                        await self._on_verified()
                    except Exception as exc:
                        logger.error("Error executing on_verified hook: %s", exc)

            elif isinstance(event, KeyVerificationCancel):
                logger.warning(
                    "Verification cancelled by %s (code: %s, reason: %s)",
                    event.sender,
                    event.code,
                    event.reason,
                )
                self._pending_verification_request = None
                self._pending_verification_start = None
                if (
                    self._current_verification_future
                    and not self._current_verification_future.done()
                ):
                    self._current_verification_future.set_exception(
                        MatrixClientError(
                            f"Verification was cancelled: {event.reason} (code: {event.code})"
                        )
                    )
        except Exception as exc:
            logger.exception("Unexpected error in to-device verification handler: %s", exc)
        finally:
            if self._client.outgoing_to_device_messages:
                try:
                    await self._client.send_to_device_messages()
                except Exception as exc:
                    logger.warning("Error flushing outgoing to-device messages: %s", exc)
            await self._notify_store_changed()

    async def _sync_loop(self) -> None:
        """Background continuous sync task."""
        logger.info("Starting background Matrix sync loop for %s", self._user_id)
        try:
            while True:
                try:
                    sync_resp = await self._client.sync(timeout=30000)
                    if isinstance(sync_resp, SyncError):
                        logger.warning(
                            "Matrix sync error: %s (status: %s)",
                            sync_resp.message,
                            sync_resp.status_code,
                        )
                        await asyncio.sleep(5)
                    else:
                        if self._client.should_upload_keys:
                            await self._client.keys_upload()
                        if self._client.should_query_keys:
                            await self._client.keys_query()
                        if self._client.should_claim_keys:
                            await self._client.keys_claim(
                                cast(Any, self._client.get_users_for_key_claiming())
                            )
                        await self._client.send_to_device_messages()
                        await self._notify_store_changed()
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "Transient error in Matrix sync loop for %s: %s, retrying in 5s...",
                        self._user_id,
                        exc,
                    )
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Matrix sync loop cancelled for %s.", self._user_id)

    async def is_room_encrypted(self, room_id: str) -> bool:
        """Check whether the target room has encryption enabled."""
        room = self._client.rooms.get(room_id)
        if room is None:
            # Attempt to join room first if unknown
            await self.join_room(room_id)
            room = self._client.rooms.get(room_id)

        if room is None:
            logger.warning("Room %s not found in client state, assuming unencrypted", room_id)
            return False

        return bool(room.encrypted)

    async def join_room(self, room_id: str) -> None:
        """Join a room by its ID or alias."""
        logger.info("Attempting to join room: %s", room_id)
        resp = await self._client.join(room_id)
        if isinstance(resp, JoinError):
            raise RoomNotFoundError(f"Cannot join room {room_id}: {resp.message}")
        logger.info("Successfully joined room: %s", room_id)
        await self._notify_store_changed()

    async def send_message(
        self,
        room_id: str,
        formatted_body: str,
        plain_body: str,
    ) -> str:
        """Send a message to a Matrix room, automatically handling encryption if enabled."""
        # Ensure the room is known and joined
        if room_id not in self._client.rooms:
            try:
                await self.join_room(room_id)
            except RoomNotFoundError as exc:
                raise RoomNotFoundError(
                    f"Bot is not in room {room_id} and could not join: {exc.message}"
                ) from exc

        content: dict[str, Any] = {
            "msgtype": "m.text",
            "body": plain_body,
            "format": "org.matrix.custom.html",
            "formatted_body": formatted_body,
        }

        # ignore_unverified_devices ensures notifications are sent even if room participants have new devices
        resp: RoomSendResponse | RoomSendError = await self._client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content,
            ignore_unverified_devices=True,
        )

        if isinstance(resp, RoomSendError):
            raise MessageSendError(f"Failed to send message to room {room_id}: {resp.message}")

        await self._notify_store_changed()
        return str(resp.event_id)

    async def check_health(self) -> dict[str, Any]:
        """Return connectivity and client operational health."""
        logged_in = bool(self._client.logged_in)
        sync_running = bool(self._sync_task and not self._sync_task.done())

        return {
            "status": "healthy" if (logged_in or self._access_token) else "degraded",
            "user_id": self._user_id,
            "device_id": self._device_id,
            "homeserver": self._homeserver,
            "logged_in": logged_in,
            "sync_loop_running": sync_running,
            "rooms_count": len(self._client.rooms),
            "store_path": str(self._store_path),
        }

    async def request_verification(
        self,
        target_device_id: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> tuple[str, list[tuple[str, str]], str | None]:
        """Request or await interactive SAS key verification, returning (tx_id, emojis, target_device_id)."""
        if not self._is_started:
            await self.start()

        # Check if we already received emojis in the last 15 seconds
        if self._latest_verification_result:
            tx_id, emojis, other_dev, timestamp = self._latest_verification_result
            if time.time() - timestamp < 15.0 and (
                target_device_id is None or target_device_id == other_dev
            ):
                logger.info("Returning freshly computed emojis for transaction %s", tx_id)
                return tx_id, emojis, other_dev

        loop = asyncio.get_running_loop()
        verification_future: asyncio.Future[tuple[str, list[tuple[str, str]], str | None]] = (
            loop.create_future()
        )
        self._current_verification_future = verification_future
        self._is_verifying = True

        try:
            # 1. If we already received a KeyVerificationStart from Tchap while waiting:
            if self._pending_verification_start:
                start_event = self._pending_verification_start
                self._pending_verification_start = None
                logger.info(
                    "Processing pending SAS verification start for tx %s from device %s...",
                    start_event.transaction_id,
                    start_event.from_device,
                )
                await self._accept_verification(start_event.transaction_id)

            # 2. If we received an m.key.verification.request from Tchap while waiting:
            elif self._pending_verification_request:
                req = self._pending_verification_request
                if time.time() - req["timestamp"] < 90.0:
                    logger.info(
                        "Answering pending verification request from device %s (tx: %s)...",
                        req["from_device"],
                        req["transaction_id"],
                    )
                    await self._send_verification_ready(
                        req["sender"], req["from_device"], req["transaction_id"]
                    )
                self._pending_verification_request = None

            # 3. If target_device_id was explicitly specified and nothing pending, initiate proactively:
            elif target_device_id is not None:
                try:
                    self._client.users_for_key_query.add(self._user_id)
                    await self._client.keys_query()
                    target_olm_device = self._client.device_store[self._user_id].get(
                        target_device_id
                    )
                    if target_olm_device:
                        logger.info(
                            "Initiating SAS verification from bot %s to device %s",
                            self._user_id,
                            target_device_id,
                        )
                        start_msg = self._client.create_key_verification(target_olm_device)
                        await self._client.to_device(start_msg)
                except Exception as exc:
                    logger.warning(
                        "Could not proactively initiate verification with device %s: %s",
                        target_device_id,
                        exc,
                    )
            else:
                logger.info(
                    "No pending verification request yet. Waiting for verification request from Tchap for bot %s...",
                    self._user_id,
                )

            logger.info(
                "Waiting for SAS verification emojis on bot %s (timeout: %.1fs)...",
                self._user_id,
                timeout_seconds,
            )

            tx_id, emojis, matched_dev = await asyncio.wait_for(
                verification_future, timeout=timeout_seconds
            )
            return tx_id, emojis, matched_dev or target_device_id
        except TimeoutError as err:
            raise VerificationTimeoutError(
                f"Timed out waiting for SAS verification emojis after {timeout_seconds:.0f}s. "
                "Please make sure you click 'Vérifier l'appareil' on Tchap before or right after calling /verify."
            ) from err
        finally:
            self._is_verifying = False
            self._current_verification_future = None

    async def close(self) -> None:
        """Gracefully close sync task and underlying HTTP sessions."""
        logger.info("Closing Matrix client connection...")
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        await self._client.close()
        self._is_started = False
        logger.info("Matrix client closed successfully.")
