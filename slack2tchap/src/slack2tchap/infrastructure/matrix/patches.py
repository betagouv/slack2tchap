"""Runtime compatibility monkey patches for matrix-nio.

Addresses regressions introduced in matrix-nio >= 0.26.0 (migration to vodozemac):

1. Issue #570: SAS verification commitment hash was computed using .hexdigest() instead
   of unpadded base64. Matrix specification (Section 11.12.2.2.1) and standard clients
   (Element, Tchap Web / matrix-rust-sdk) strictly require 43-character unpadded base64.
2. SAS Emoji Generation: In vodozemac, `EstablishedSas.bytes().emoji_indices` returns
   an array of 7 integers (each 0..63) representing the emoji indices. matrix-nio mistakenly
   treated this as raw 48-bit bytes and re-sliced them into 6-bit chunks, yielding corrupted
   emojis that did not match the other client.
3. SAS MAC Calculation: For "hkdf-hmac-sha256", Matrix specification and matrix-rust-sdk
   use the libolm-compatible invalid-base64 encoding (`calculate_mac_invalid_base64`).
   matrix-nio called the new standard `calculate_mac`, causing modern clients to reject
   the MAC with `m.key_mismatch`.
"""

from hashlib import sha256
from typing import Any

from nio.api import Api
from nio.crypto.sas import Sas, SasState
from nio.event_builders import ToDeviceMessage
from nio.exceptions import LocalProtocolError
from unpaddedbase64 import encode_base64

_patched = False


def apply_matrix_nio_patches() -> None:
    """Apply runtime patches to matrix-nio to conform with Matrix SAS specification."""
    global _patched
    if _patched:
        return

    orig_from_key_verification_start = Sas.from_key_verification_start

    # Patch 1: Commitment hash in unpadded base64
    def patched_from_key_verification_start(
        _cls: type[Sas],
        own_user: str,
        own_device: str,
        own_fp_key: str,
        other_olm_device: Any,
        event: Any,
    ) -> Sas:
        obj = orig_from_key_verification_start(
            own_user,
            own_device,
            own_fp_key,
            other_olm_device,
            event,
        )
        string_content = Api.to_canonical_json(event.source["content"])
        obj.commitment = encode_base64(
            sha256(obj.pubkey.encode() + string_content.encode()).digest()
        )
        return obj

    def patched_check_commitment(self: Sas, key: str) -> bool:
        assert self.commitment
        digest = sha256(
            key.encode() + Api.to_canonical_json(self.start_verification().content).encode()
        ).digest()
        b64_commitment = encode_base64(digest)
        hex_commitment = digest.hex()
        return self.commitment in (b64_commitment, hex_commitment)

    # Patch 2: Correct emoji generation from vodozemac emoji_indices
    def patched_generate_emoji(self: Sas, extra_info: str) -> list[tuple[str, str]]:
        assert self.established_sas
        generated_bytes = self.established_sas.bytes(extra_info).emoji_indices
        return [self.emoji[i] for i in generated_bytes]

    # Patch 3: MAC calculation and verification conforming to Matrix spec for hkdf-hmac-sha256
    def patched_get_mac(self: Sas) -> ToDeviceMessage:
        if not self.sas_accepted:
            raise LocalProtocolError("SAS string wasn't yet accepted")

        if self.state == SasState.canceled:
            raise LocalProtocolError("SAS verification was canceled, can't generate MAC.")

        key_id = f"ed25519:{self.own_device}"

        assert self.established_sas
        assert self.chosen_mac_method

        if self.chosen_mac_method == Sas._mac_normal:
            calculate_mac = self.established_sas.calculate_mac_invalid_base64
        else:
            calculate_mac = self.established_sas.calculate_mac

        info = (
            "MATRIX_KEY_VERIFICATION_MAC"
            f"{self.own_user}{self.own_device}"
            f"{self.other_olm_device.user_id}{self.other_olm_device.id}{self.transaction_id}"
        )

        mac = {key_id: calculate_mac(self.own_fp_key, info + key_id)}

        content = {
            "mac": mac,
            "keys": calculate_mac(key_id, info + "KEY_IDS"),
            "transaction_id": self.transaction_id,
        }

        return ToDeviceMessage(
            "m.key.verification.mac",
            self.other_olm_device.user_id,
            self.other_olm_device.id,
            content,
        )

    def patched_receive_mac_event(self: Sas, event: Any) -> None:
        if self.verified:
            return

        if not self._event_ok(event):
            return

        if self.state != SasState.key_received:
            self.state = SasState.canceled
            (
                self.cancel_code,
                self.cancel_reason,
            ) = Sas._unexpected_message_error
            return

        info = (
            f"MATRIX_KEY_VERIFICATION_MAC{self.other_olm_device.user_id}{self.other_olm_device.id}"
            f"{self.own_user}{self.own_device}{self.transaction_id}"
        )

        key_ids = ",".join(sorted(event.mac.keys()))

        assert self.established_sas
        assert self.chosen_mac_method

        def verify_mac_match(val: str, expected_input: str, expected_info: str) -> bool:
            assert self.established_sas
            return val in (
                self.established_sas.calculate_mac_invalid_base64(expected_input, expected_info),
                self.established_sas.calculate_mac(expected_input, expected_info),
            )

        if not verify_mac_match(event.keys, key_ids, info + "KEY_IDS"):
            self.state = SasState.canceled
            self.cancel_code, self.cancel_reason = self._key_mismatch_error
            return

        for key_id, key_mac in event.mac.items():
            try:
                key_type, device_id = key_id.split(":", 2)
            except ValueError:
                self.state = SasState.canceled
                (
                    self.cancel_code,
                    self.cancel_reason,
                ) = self._invalid_message_error
                return

            if key_type != "ed25519":
                self.state = SasState.canceled
                self.cancel_code, self.cancel_reason = self._key_mismatch_error
                return

            if device_id != self.other_olm_device.id:
                continue

            other_fp_key = self.other_olm_device.ed25519

            if not verify_mac_match(key_mac, other_fp_key, info + key_id):
                self.state = SasState.canceled
                self.cancel_code, self.cancel_reason = self._key_mismatch_error
                return

            self.verified_devices.append(device_id)

        if not self.verified_devices:
            self.state = SasState.canceled
            self.cancel_code, self.cancel_reason = self._key_mismatch_error

        self.state = SasState.mac_received

    Sas.from_key_verification_start = classmethod(patched_from_key_verification_start)  # type: ignore[assignment]
    Sas._check_commitment = patched_check_commitment  # type: ignore[assignment]
    Sas._generate_emoji = patched_generate_emoji  # type: ignore[assignment]
    Sas.get_mac = patched_get_mac  # type: ignore[assignment]
    Sas.receive_mac_event = patched_receive_mac_event  # type: ignore[assignment]
    _patched = True
