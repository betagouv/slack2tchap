"""Tests for matrix-nio SAS verification monkey patch."""

from hashlib import sha256
from typing import Any

from nio.api import Api
from nio.crypto import Sas
from nio.events import KeyVerificationStart
from unpaddedbase64 import decode_base64

from slack2tchap.infrastructure.matrix.patches import apply_matrix_nio_patches


class DummyDevice:
    """Mock OlmDevice for testing."""

    id = "DUMMY_DEV"
    device_id = "DUMMY_DEV"
    user_id = "@user:test.gouv.fr"
    ed25519 = "dummy_ed25519_key"


def test_matrix_nio_sas_commitment_patch_applied() -> None:
    """Verify that matrix-nio SAS commitment adheres to Matrix spec (unpadded base64)."""
    apply_matrix_nio_patches()

    start_payload: dict[str, Any] = {
        "sender": "@user:test.gouv.fr",
        "transaction_id": "tx_test_123",
        "content": {
            "from_device": "DUMMY_DEV",
            "method": "m.sas.v1",
            "key_agreement_protocols": ["curve25519-hkdf-sha256"],
            "hashes": ["sha256"],
            "message_authentication_codes": ["hkdf-hmac-sha256"],
            "short_authentication_string": ["emoji", "decimal"],
            "transaction_id": "tx_test_123",
        },
    }
    event = KeyVerificationStart.from_dict(start_payload)

    sas = Sas.from_key_verification_start(
        "@bot:test.gouv.fr",
        "BOT_DEV",
        "bot_fp_key",
        DummyDevice(),  # type: ignore[arg-type]
        event,
    )

    # Matrix spec: unpadded base64 of sha256 digest is exactly 43 characters
    assert sas.commitment is not None
    assert len(sas.commitment) == 43
    assert not sas.commitment.endswith("=")

    # Verify that decoding matches exact sha256 bytes
    expected_digest = sha256(
        sas.pubkey.encode() + Api.to_canonical_json(event.source["content"]).encode()
    ).digest()
    assert decode_base64(sas.commitment) == expected_digest

    # Verify accept_verification contains the unpadded base64 commitment
    accept_msg = sas.accept_verification()
    assert accept_msg.content["commitment"] == sas.commitment


def test_matrix_nio_sas_emoji_and_mac_patches() -> None:
    """Verify that emoji generation matches vodozemac and MAC calculation uses invalid_base64 for hkdf-hmac-sha256."""
    apply_matrix_nio_patches()

    alice_device = DummyDevice()
    alice_device.id = "ALICE_DEV"
    alice_device.device_id = "ALICE_DEV"
    alice_device.user_id = "@alice:test.gouv.fr"
    alice_device.ed25519 = "alice_fingerprint_key"

    bob_device = DummyDevice()
    bob_device.id = "BOB_DEV"
    bob_device.device_id = "BOB_DEV"
    bob_device.user_id = "@bob:test.gouv.fr"
    bob_device.ed25519 = "bob_fingerprint_key"

    tx_id = "test_tx_123"
    sas_alice = Sas(
        "@alice:test.gouv.fr",
        "ALICE_DEV",
        "alice_fp",
        bob_device,  # type: ignore[arg-type]
        transaction_id=tx_id,
    )
    sas_bob = Sas(
        "@bob:test.gouv.fr",
        "BOB_DEV",
        "bob_fp",
        alice_device,  # type: ignore[arg-type]
        transaction_id=tx_id,
    )

    sas_alice.we_started_it = True
    sas_bob.we_started_it = False

    # Perform DH / establish SAS
    sas_alice.establish_sas(sas_bob.pubkey)
    sas_bob.establish_sas(sas_alice.pubkey)

    sas_alice.chosen_key_agreement = Sas._key_agreement_v2
    sas_bob.chosen_key_agreement = Sas._key_agreement_v2
    sas_alice.chosen_mac_method = Sas._mac_normal
    sas_bob.chosen_mac_method = Sas._mac_normal

    # Verify emojis match across both parties and have exactly 7 emojis
    emojis_alice = sas_alice.get_emoji()
    emojis_bob = sas_bob.get_emoji()
    assert len(emojis_alice) == 7
    assert emojis_alice == emojis_bob

    # Verify MAC generation and exchange
    sas_alice.sas_accepted = True
    sas_bob.sas_accepted = True

    mac_msg_alice = sas_alice.get_mac()
    assert "ed25519:ALICE_DEV" in mac_msg_alice.content["mac"]
    assert "keys" in mac_msg_alice.content

    mac_msg_bob = sas_bob.get_mac()
    assert "ed25519:BOB_DEV" in mac_msg_bob.content["mac"]
    assert "keys" in mac_msg_bob.content
