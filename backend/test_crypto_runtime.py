from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

import crypto_runtime
import operator_identity


def main() -> None:
    health = crypto_runtime.cryptography_self_test()
    assert health["healthy"] is True
    assert health["sign_verify"] is True
    assert health["serialization_reload"] is True
    assert health["invalid_signature_rejected"] is True

    original_path = operator_identity.IDENTITY_PATH
    with tempfile.TemporaryDirectory() as temporary:
        operator_identity.IDENTITY_PATH = Path(temporary) / "operator_identity.json"
        first = operator_identity.operator_identity()
        stored = json.loads(operator_identity.IDENTITY_PATH.read_text(encoding="utf-8"))
        assert "private_key" not in stored
        assert stored["private_key_protected"]["protection"] in {"windows-dpapi-current-user", "owner-only-file"}
        assert base64.b64decode(stored["public_key"], validate=True)
        signed = operator_identity.sign_world_identity({"world_id": "crypto-test", "world_name": "Signed World"})
        verified = operator_identity.verify_world_identity(signed)
        assert verified["verified"] is True
        signed["payload"]["world_name"] = "Tampered"
        assert operator_identity.verify_world_identity(signed)["verified"] is False
        second = operator_identity.operator_identity()
        assert second["fingerprint"] == first["fingerprint"]
    operator_identity.IDENTITY_PATH = original_path
    print("cryptography runtime tests passed")


if __name__ == "__main__":
    main()
