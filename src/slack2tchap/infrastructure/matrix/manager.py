"""Multi-tenant stateless Matrix client manager with PostgreSQL crypto-store persistence."""

import asyncio
import io
import logging
import tarfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slack2tchap.domain.exceptions import AuthenticationError, MatrixAccountNotFoundError
from slack2tchap.domain.models import MatrixAccount
from slack2tchap.domain.ports import (
    MatrixAccountRepositoryPort,
    MatrixClientManagerPort,
    MatrixMessengerPort,
    SecretCipherPort,
)
from slack2tchap.infrastructure.matrix.adapter import MatrixNioAdapter
from slack2tchap.infrastructure.repositories.matrix_account_repository import (
    SqlAlchemyMatrixAccountRepository,
)

logger = logging.getLogger(__name__)


def create_crypto_store_archive(store_dir: Path) -> bytes:
    """Create a compressed tar.gz in-memory archive of the matrix-nio SQLite store directory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for file_path in store_dir.glob("*"):
            if file_path.is_file():
                tar.add(str(file_path), arcname=file_path.name)
    return buf.getvalue()


def extract_crypto_store_archive(archive_bytes: bytes, target_dir: Path) -> None:
    """Extract in-memory tar.gz archive into the target temporary store directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(archive_bytes)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(path=str(target_dir), filter="data")


def compute_store_fingerprint(store_dir: Path) -> tuple[tuple[str, int, int], ...]:
    """Return sorted tuple of (filename, mtime_ns, size_bytes) for all files in store_dir."""
    if not store_dir.exists():
        return ()
    items: list[tuple[str, int, int]] = []
    for p in sorted(store_dir.glob("*")):
        if p.is_file():
            stat = p.stat()
            items.append((p.name, stat.st_mtime_ns, stat.st_size))
    return tuple(items)


class MatrixClientManager(MatrixClientManagerPort):
    """Manages dynamic Matrix bot sessions, restoring & persisting E2EE state in PostgreSQL."""

    def __init__(
        self,
        cipher: SecretCipherPort,
        homeserver: str,
        account_repo: MatrixAccountRepositoryPort | None = None,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        base_temp_dir: Path = Path("/tmp/matrix_stores"),
        auto_join: bool = True,
    ) -> None:
        self._account_repo = account_repo
        self._session_maker = session_maker
        self._cipher = cipher
        self._homeserver = homeserver
        self._base_temp_dir = base_temp_dir
        self._auto_join = auto_join

        self._clients: dict[UUID, MatrixNioAdapter] = {}
        self._lock = asyncio.Lock()
        self._store_fingerprints: dict[UUID, tuple[tuple[str, int, int], ...]] = {}
        self._persist_locks: dict[UUID, asyncio.Lock] = {}
        self._watcher_task: asyncio.Task[None] | None = None

    @asynccontextmanager
    async def _get_repo(self) -> AsyncGenerator[MatrixAccountRepositoryPort, None]:
        if self._account_repo is not None:
            yield self._account_repo
        elif self._session_maker is not None:
            async with self._session_maker() as session:
                yield SqlAlchemyMatrixAccountRepository(session)
                await session.commit()
        else:
            raise RuntimeError(
                "Neither account_repo nor session_maker configured in MatrixClientManager"
            )

    def _get_account_store_dir(self, account_id: UUID) -> Path:
        return self._base_temp_dir / str(account_id)

    def _resolve_homeserver_url(self, matrix_user_id: str) -> str:
        """Resolve actual homeserver URL based on user ID domain and configured homeserver."""
        if ":" in matrix_user_id:
            domain = matrix_user_id.split(":", 1)[1].strip()
            clean_hs = self._homeserver.strip().rstrip("/")
            if not clean_hs or "www.tchap.gouv.fr" in clean_hs:
                return f"https://matrix.{domain}"
            if domain.endswith(".tchap.gouv.fr") and not clean_hs.endswith(domain):
                return f"https://matrix.{domain}"
        return self._homeserver

    def _start_watcher_if_needed(self) -> None:
        """Start periodic background watcher if not already running."""
        if self._watcher_task is None or self._watcher_task.done():
            self._watcher_task = asyncio.create_task(
                self._store_watcher_loop(), name="matrix-store-watcher"
            )

    async def _store_watcher_loop(self) -> None:
        """Periodic background task ensuring any modification to SQLite stores is persisted."""
        while True:
            try:
                await asyncio.sleep(10)
                for account_id in list(self._clients.keys()):
                    try:
                        await self.persist_if_modified(account_id)
                    except Exception as exc:
                        logger.warning(
                            "Error in periodic crypto store persistence check for %s: %s",
                            account_id,
                            exc,
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unexpected error in store watcher loop: %s", exc)
                await asyncio.sleep(5)

    async def get_or_create_client(self, account_id: UUID) -> MatrixMessengerPort:
        """Retrieve active Matrix client or initialize one restoring its E2EE crypto-store from DB."""
        async with self._lock:
            if account_id in self._clients:
                return self._clients[account_id]

            async with self._get_repo() as repo:
                account = await repo.get_by_id(account_id)
            if account is None or not account.is_active:
                raise MatrixAccountNotFoundError(
                    f"Matrix account {account_id} not found or is inactive."
                )

            client = await self._initialize_client(account)
            self._clients[account_id] = client
            self._start_watcher_if_needed()
            return client

    async def get_client(self, account_id: UUID) -> MatrixMessengerPort:
        """Alias for get_or_create_client."""
        return await self.get_or_create_client(account_id)

    async def remove_client(self, account_id: UUID) -> None:
        """Close and remove an active Matrix client session."""
        async with self._lock:
            client = self._clients.pop(account_id, None)
            self._store_fingerprints.pop(account_id, None)
            self._persist_locks.pop(account_id, None)
            if client is not None:
                try:
                    await client.close()
                except Exception as exc:
                    logger.error("Error closing Matrix client %s: %s", account_id, exc)

    async def start_all_clients(self) -> None:
        """Start Matrix clients for all configured and active accounts at startup."""
        async with self._get_repo() as repo:
            accounts = await repo.list_all_active()

        logger.info("Auto-starting %d active Matrix bot account(s)...", len(accounts))
        for account in accounts:
            try:
                await self.get_or_create_client(account.id)
            except Exception as exc:
                logger.error(
                    "Failed to auto-start Matrix client for bot %s: %s",
                    account.matrix_user_id,
                    exc,
                )

    async def _initialize_client(self, account: MatrixAccount) -> MatrixNioAdapter:
        """Initialize a single Matrix client, restoring its persisted state if available."""
        store_dir = self._get_account_store_dir(account.id)

        # Restore persisted SQLite crypto-store blob from PostgreSQL if present
        if account.crypto_store_blob:
            logger.info(
                "Restoring persisted E2EE crypto-store from DB for bot %s (size: %d bytes)",
                account.matrix_user_id,
                len(account.crypto_store_blob),
            )
            extract_crypto_store_archive(account.crypto_store_blob, store_dir)
        else:
            logger.info(
                "First initialization of bot %s: creating new store in %s",
                account.matrix_user_id,
                store_dir,
            )
            store_dir.mkdir(parents=True, exist_ok=True)

        # Decrypt password or access token
        raw_password: str | None = None
        raw_token: str | None = None

        if account.encrypted_password and account.encryption_nonce:
            raw_password = self._cipher.decrypt(
                account.encrypted_password, account.encryption_nonce
            )
        elif account.encrypted_access_token and account.encryption_nonce:
            raw_token = self._cipher.decrypt(
                account.encrypted_access_token, account.encryption_nonce
            )

        if not raw_password and not raw_token:
            raise AuthenticationError(
                f"No credentials configured for Matrix account {account.matrix_user_id}"
            )

        homeserver_url = self._resolve_homeserver_url(account.matrix_user_id)
        adapter = MatrixNioAdapter(
            homeserver=homeserver_url,
            user_id=account.matrix_user_id,
            device_id=account.device_id,
            store_path=store_dir,
            store_passphrase="stateless_session_passphrase",
            password=raw_password,
            access_token=raw_token,
            auto_join=self._auto_join,
            on_verified=lambda: self.persist_account_crypto_store(account.id),
            on_store_changed=lambda: self._handle_store_changed(account.id),
        )

        await adapter.start()

        # Immediately persist the newly generated or uploaded crypto keys to PostgreSQL
        await self.persist_account_crypto_store(account.id)

        return adapter

    async def _handle_store_changed(self, account_id: UUID) -> None:
        """Handle store change notification by persisting if modified."""
        await self.persist_if_modified(account_id)

    async def _do_persist_account_crypto_store(self, account_id: UUID) -> None:
        """Internal worker persisting crypto store directory as tar.gz into PostgreSQL."""
        store_dir = self._get_account_store_dir(account_id)
        if not store_dir.exists():
            return

        blob = create_crypto_store_archive(store_dir)
        if blob:
            logger.info(
                "Persisting E2EE crypto-store blob to PostgreSQL for account %s (%d bytes)",
                account_id,
                len(blob),
            )
            async with self._get_repo() as repo:
                await repo.save_crypto_store(account_id, blob)

    async def persist_account_crypto_store(self, account_id: UUID) -> None:
        """Dump SQLite crypto store files into tar.gz and persist in PostgreSQL."""
        lock = self._persist_locks.setdefault(account_id, asyncio.Lock())
        async with lock:
            await self._do_persist_account_crypto_store(account_id)
            store_dir = self._get_account_store_dir(account_id)
            self._store_fingerprints[account_id] = compute_store_fingerprint(store_dir)

    async def persist_if_modified(self, account_id: UUID) -> bool:
        """Check if SQLite store was modified since last save; if so, persist to PostgreSQL."""
        lock = self._persist_locks.setdefault(account_id, asyncio.Lock())
        async with lock:
            store_dir = self._get_account_store_dir(account_id)
            current_fp = compute_store_fingerprint(store_dir)
            if not current_fp:
                return False

            last_fp = self._store_fingerprints.get(account_id)
            if last_fp == current_fp:
                return False

            logger.info(
                "Crypto store modified on disk for bot %s; persisting updated snapshot to PostgreSQL...",
                account_id,
            )
            await self._do_persist_account_crypto_store(account_id)
            self._store_fingerprints[account_id] = current_fp
            return True

    async def persist_all_stores(self) -> None:
        """Persist crypto stores of all currently active clients to DB."""
        for account_id in list(self._clients.keys()):
            try:
                await self.persist_account_crypto_store(account_id)
            except Exception as exc:
                logger.error("Failed to persist crypto store for account %s: %s", account_id, exc)

    async def shutdown(self) -> None:
        """Persist all crypto stores to PostgreSQL and close all Matrix sessions."""
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

        logger.info(
            "Persisting all active Matrix E2EE crypto stores to PostgreSQL before shutdown..."
        )
        await self.persist_all_stores()

        logger.info("Closing all active Matrix bot clients (%d)...", len(self._clients))
        for account_id, client in self._clients.items():
            try:
                await client.close()
            except Exception as exc:
                logger.error("Error closing Matrix client %s: %s", account_id, exc)

        self._clients.clear()
        logger.info("All Matrix bot clients closed.")
