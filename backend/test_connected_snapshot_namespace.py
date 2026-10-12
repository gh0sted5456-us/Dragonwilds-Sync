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

            # Merging a legacy cache into an existing destination must remove
            # only snapshot/. Unknown sibling files may belong to the user.
            merge_root = local_root / "connected-merge-id"
            merge_snapshot = merge_root / "snapshot"
            merge_snapshot.mkdir(parents=True)
            (merge_snapshot / "migrated.bin").write_bytes(b"migrated")
            unknown_file = merge_root / "unknown-user-file.txt"
            unknown_file.write_text("preserve me", encoding="utf-8")
            merge_destination = connected_root / "connected-merge-id" / "snapshot"
            merge_destination.mkdir(parents=True)
            (merge_destination / "existing.bin").write_bytes(b"existing")

            local_world.list_profiles()
            assert (merge_destination / "migrated.bin").read_bytes() == b"migrated"
            assert (merge_destination / "existing.bin").read_bytes() == b"existing"
            assert not merge_snapshot.exists()
            assert unknown_file.read_text(encoding="utf-8") == "preserve me"

            # Deleting a connected profile follows the same ownership rule for
            # the old misplaced cache path.
            delete_root = local_root / "connected-delete-id"
            delete_snapshot = delete_root / "snapshot"
            delete_snapshot.mkdir(parents=True)
            (delete_snapshot / "cache.bin").write_bytes(b"cache")
            delete_unknown = delete_root / "notes.txt"
            delete_unknown.write_text("keep", encoding="utf-8")
            active_cache = connected_root / "connected-delete-id" / "snapshot"
            active_cache.mkdir(parents=True)
            (active_cache / "active.bin").write_bytes(b"active")

            sync_engine.delete_client_world_profile("connected-delete-id")
            assert not (connected_root / "connected-delete-id").exists()
            assert not delete_snapshot.exists()
            assert delete_unknown.read_text(encoding="utf-8") == "keep"

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
