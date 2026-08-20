from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dws-profile-cache-") as temp:
        os.environ["DRAGONWILDS_SYNC_APPDATA"] = str(Path(temp) / "appdata")
        import profile_store

        state = profile_store.default_state()
        state["application"]["cache_probe"] = "saved"
        profile_store.save_state(state)

        # Callers receive isolated copies; a renderer/RPC mutation cannot poison
        # the backend's process cache before an explicit save.
        first = profile_store.load_state()
        first["application"]["cache_probe"] = "caller-mutated"
        assert profile_store.load_state()["application"]["cache_probe"] == "saved"

        # An out-of-process/legacy writer remains authoritative. File metadata
        # invalidates the memory entry and the next read observes disk.
        raw = json.loads(profile_store.V2_SETTINGS_PATH.read_text(encoding="utf-8"))
        raw["application"]["cache_probe"] = "external-writer"
        raw["application"]["cache_probe_padding"] = "signature-change"
        profile_store.V2_SETTINGS_PATH.write_text(json.dumps(raw), encoding="utf-8")
        assert profile_store.load_state()["application"]["cache_probe"] == "external-writer"

        profile_id = profile_store.create_server_profile("Cache Authority")
        profile = profile_store.load_server_profile(profile_id)
        profile["name"] = "unsaved caller mutation"
        assert profile_store.load_server_profile(profile_id)["name"] == "Cache Authority"

        profile_path = profile_store.SERVER_PROFILES_DIR / profile_id / "profile.json"
        raw_profile = json.loads(profile_path.read_text(encoding="utf-8"))
        raw_profile["name"] = "External Profile Writer"
        raw_profile["cache_probe_padding"] = "signature-change"
        profile_path.write_text(json.dumps(raw_profile), encoding="utf-8")
        assert profile_store.load_server_profile(profile_id)["name"] == "External Profile Writer"

        profile_store.delete_server_profile(profile_id)
        assert profile_store.load_server_profile(profile_id) == {}

    print("profile/system state memory cache authority + invalidation: PASS")


if __name__ == "__main__":
    main()
