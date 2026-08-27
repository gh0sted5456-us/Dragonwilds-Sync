from __future__ import annotations

import tempfile
from pathlib import Path

import local_world
import sync_engine


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        local_root = root / "profiles" / "world" / "local"
        connected_root = root / "profiles" / "world" / "connected"
        local_root.mkdir(parents=True)

        old_local = (local_world.WORLD_PROFILE_ROOT, local_world.LOCAL_PROFILE_DIR,
                     local_world.LOCAL_PROFILE_FILE, local_world.PRIVATE_PROFILES_DIR,
                     local_world.CONNECTED_PROFILES_DIR)
        old_sync = (sync_engine.CLIENT_WORLDS_DIR, sync_engine.LEGACY_CLIENT_WORLDS_DIR)
        try:
            local_world.WORLD_PROFILE_ROOT = local_root
            local_world.LOCAL_PROFILE_DIR = local_root / local_world.SINGLEPLAYER_ID
            local_world.LOCAL_PROFILE_FILE = local_world.LOCAL_PROFILE_DIR / "profile.json"
            local_world.PRIVATE_PROFILES_DIR = local_root
            local_world.CONNECTED_PROFILES_DIR = connected_root
            sync_engine.CLIENT_WORLDS_DIR = connected_root
            sync_engine.LEGACY_CLIENT_WORLDS_DIR = local_root

            misplaced = local_root / "connected-old-id" / "snapshot"
            misplaced.mkdir(parents=True)
            (misplaced / sync_engine.SNAPSHOT_MARKER).write_text("ready\n", encoding="utf-8")
            (misplaced / "payload.bin").write_bytes(b"connected-cache")

            private = local_world.default_singleplayer_profile("private-real", "Real Private World")
            local_world.save_profile(private, "private-real")
            profiles = local_world.list_profiles()
            ids = {str(profile.get("id") or "") for profile in profiles}
            assert "connected-old-id" not in ids
            assert "private-real" in ids
            assert not (local_root / "connected-old-id").exists()

            migrated = sync_engine.client_world_dir("connected-old-id")
            assert migrated == connected_root / "connected-old-id" / "snapshot"
            assert (migrated / "payload.bin").read_bytes() == b"connected-cache"

            # A same-named real private profile is an ownership boundary; its
            # snapshot must never be moved or deleted by connected migration.
            private_snapshot = local_root / "private-real" / "snapshot"
            private_snapshot.mkdir(parents=True)
            (private_snapshot / "private.bin").write_bytes(b"private")
            target = sync_engine.client_world_dir("private-real")
            assert not target.exists()
            assert (private_snapshot / "private.bin").read_bytes() == b"private"
        finally:
            (local_world.WORLD_PROFILE_ROOT, local_world.LOCAL_PROFILE_DIR,
             local_world.LOCAL_PROFILE_FILE, local_world.PRIVATE_PROFILES_DIR,
             local_world.CONNECTED_PROFILES_DIR) = old_local
            sync_engine.CLIENT_WORLDS_DIR, sync_engine.LEGACY_CLIENT_WORLDS_DIR = old_sync

    print("connected snapshot namespace and stable profile enumeration: PASS")


if __name__ == "__main__":
    main()
