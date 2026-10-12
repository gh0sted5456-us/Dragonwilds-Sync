from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    with TemporaryDirectory(prefix="dws-trust-") as temporary:
        os.environ["DRAGONWILDS_SYNC_APPDATA"] = temporary
        for name in ("profile_store", "trusted_devices"):
            sys.modules.pop(name, None)
        import trusted_devices as trust

        pairing = trust.create_pairing(broadcaster_ref="broadcaster-1", world_id="world-1",
                                       world_name="Test World", requested_role="operator",
                                       base_url="https://world.example")
        assert pairing["pairingUrl"].startswith("https://world.example/admin/pair?")
        assert pairing["fallbackCode"] not in Path(temporary, "security", "trusted-devices.json").read_text(encoding="utf-8")

        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        submitted = trust.submit_pairing(pairing["pairingId"], challenge=pairing["challenge"],
            public_key_b64=base64.b64encode(public).decode("ascii"), credential_id="credential-1",
            display_name="Luke's Phone", device_class="phone", platform="Android", browser_or_app="Dragonwilds Sync")
        approved = trust.approve_pairing(submitted["requestId"], approved=True, role="operator")
        device_id = approved["device"]["deviceId"]
        challenge = trust.begin_auth(device_id)
        signature = private.sign(challenge["challenge"].encode("utf-8"))
        session = trust.complete_auth(device_id, challenge["challengeId"], base64.b64encode(signature).decode("ascii"))
        assert trust.validate_session(session["token"], permission="sync")
        assert trust.validate_session(session["token"], permission="security") is None
        assert trust.validate_session(session["token"], permission="sync", sensitive_action="world_delete") is None
        state = trust.list_security_state(world_id="world-1")
        assert len(state["devices"]) == 1 and state["devices"][0]["displayName"] == "Luke's Phone"
        trust.update_device(device_id, status="revoked")
        assert trust.validate_session(session["token"], permission="sync") is None
    print("trusted-device pairing/session contracts: PASS")


if __name__ == "__main__":
    main()
