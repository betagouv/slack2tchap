"""Unit tests for MatrixClientManager crypto-store fingerprinting and real-time persistence."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from fakes import FakeMatrixAccountRepository
from slack2tchap.domain.models import MatrixAccount
from slack2tchap.infrastructure.matrix.manager import (
    MatrixClientManager,
    compute_store_fingerprint,
    create_crypto_store_archive,
    extract_crypto_store_archive,
)


def test_crypto_store_archive_and_extract() -> None:
    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dest_dir:
        src_path = Path(src_dir)
        dest_path = Path(dest_dir)

        # Create dummy store files
        (src_path / "matrix-store.db").write_text("dummy sqlite content")
        (src_path / "matrix-store.db-wal").write_text("wal data")

        archive = create_crypto_store_archive(src_path)
        assert len(archive) > 0

        extract_crypto_store_archive(archive, dest_path)
        assert (dest_path / "matrix-store.db").exists()
        assert (dest_path / "matrix-store.db").read_text() == "dummy sqlite content"
        assert (dest_path / "matrix-store.db-wal").read_text() == "wal data"


def test_compute_store_fingerprint() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)
        assert compute_store_fingerprint(path) == ()

        file_1 = path / "store.db"
        file_1.write_text("initial")

        fp1 = compute_store_fingerprint(path)
        assert len(fp1) == 1
        assert fp1[0][0] == "store.db"

        # Same content -> same fingerprint
        fp2 = compute_store_fingerprint(path)
        assert fp1 == fp2

        # Modified content -> different fingerprint
        file_1.write_text("modified content")
        fp3 = compute_store_fingerprint(path)
        assert fp1 != fp3


@pytest.mark.asyncio
async def test_persist_if_modified_only_saves_on_actual_change(
    fake_matrix_account_repository: FakeMatrixAccountRepository,
) -> None:
    with tempfile.TemporaryDirectory() as base_temp:
        from slack2tchap.infrastructure.security.cipher import AesGcmSecretCipher

        cipher = AesGcmSecretCipher("32_bytes_super_secret_test_key_for_cipher!")
        manager = MatrixClientManager(
            cipher=cipher,
            homeserver="https://matrix.agent.tchap.gouv.fr",
            account_repo=fake_matrix_account_repository,
            base_temp_dir=Path(base_temp),
        )

        account_id = uuid4()
        account = MatrixAccount(
            id=account_id,
            name="Test Bot",
            matrix_user_id="@test:agent.tchap.gouv.fr",
            user_id=uuid4(),
        )
        await fake_matrix_account_repository.save(account)

        store_dir = Path(base_temp) / str(account_id)
        store_dir.mkdir(parents=True, exist_ok=True)
        db_file = store_dir / "store.db"
        db_file.write_text("state 1")

        # 1. First persist_if_modified: should detect changes and save blob to repository
        saved_1 = await manager.persist_if_modified(account_id)
        assert saved_1 is True
        saved_acc = await fake_matrix_account_repository.get_by_id(account_id)
        assert saved_acc is not None
        assert saved_acc.crypto_store_blob is not None
        initial_blob = saved_acc.crypto_store_blob

        # 2. Second persist_if_modified without disk changes: should NOT save (fingerprint match)
        saved_2 = await manager.persist_if_modified(account_id)
        assert saved_2 is False

        # 3. Simulate Matrix client modifying SQLite store
        import asyncio

        await asyncio.sleep(0.01)
        db_file.write_text("state 2 with new room keys")

        # 4. Third persist_if_modified: should detect change and save updated blob
        saved_3 = await manager.persist_if_modified(account_id)
        assert saved_3 is True
        updated_acc = await fake_matrix_account_repository.get_by_id(account_id)
        assert updated_acc is not None
        assert updated_acc.crypto_store_blob != initial_blob

        await manager.shutdown()


@pytest.mark.asyncio
async def test_remove_client(
    fake_matrix_account_repository: FakeMatrixAccountRepository,
) -> None:
    with tempfile.TemporaryDirectory() as base_temp:
        from unittest.mock import AsyncMock

        from slack2tchap.infrastructure.security.cipher import AesGcmSecretCipher

        cipher = AesGcmSecretCipher("32_bytes_super_secret_test_key_for_cipher!")
        manager = MatrixClientManager(
            cipher=cipher,
            homeserver="https://matrix.agent.tchap.gouv.fr",
            account_repo=fake_matrix_account_repository,
            base_temp_dir=Path(base_temp),
        )

        account_id = uuid4()
        fake_client = AsyncMock()
        manager._clients[account_id] = fake_client  # type: ignore[assignment]
        manager._store_fingerprints[account_id] = (("store.db", 1, 1),)

        await manager.remove_client(account_id)

        assert account_id not in manager._clients
        assert account_id not in manager._store_fingerprints
        fake_client.close.assert_awaited_once()
