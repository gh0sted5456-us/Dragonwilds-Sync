from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build(path: Path, *, malicious: bool = False, save_mode: str = "raw") -> None:
    created = "2026-08-20T02:30:00+00:00"
    fingerprint = "browser-draft"
    draft = {
        "name": "Web Builder Test World",
        "description": "Created in the browser builder.",
        "community_rules": "Be kind.",
        "tags": ["family-friendly", "rune schema", "pak"],
        "audience": "kids",
        "platform_compatibility": {"steam": True, "epicgames": True, "nintendo": True, "xbox": True},
        "runtimeIntent": {"ue4ss": True, "runeschema": True},
        "release_channel": "experimental",
        "placard_background": "3",
        "dedicated": {"game_port": 7788},
        "mods": [{"name": "Example Mod", "tags": ["RuneSchema"]}],
    }
    if malicious:
        draft["server_key"] = "browser-must-never-own-this"
    profile = {"profileId": "browser-profile-hint", "profileName": "Web Builder Test World"}
    worlds = {"worlds": [{"profileWorldKey": "web-test-world", "name": "Web Builder Test World"}]}
    payloads = [
        ("profile-metadata", "profile/profile.json", _canonical(profile), "application/json", True),
        ("world-list", "worlds/worlds.json", _canonical(worlds), "application/json", True),
        ("server-profile-draft", "worlds/drafts/web-test-world/server-profile.json", _canonical(draft), "application/json", True),
    ]
    if save_mode == "raw":
        payloads.append(("world-save-file", "worlds/saves/web-test-world/TestWorld.sav", b"SAVE-WEBSITE-DRAFT", "application/octet-stream", True))
    elif save_mode in {"zip", "unsafe-zip"}:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as save_archive:
            save_archive.writestr("Nested/TestWorld.sav" if save_mode == "zip" else "../escaped.sav", b"SAVE-WEBSITE-DRAFT-ZIP")
        payloads.append(("world-save-archive", "worlds/saves/web-test-world/world-save.zip", buffer.getvalue(), "application/zip", True))
    records = [
        {"role": role, "path": member, "mediaType": media, "sha256": _sha(blob), "size": len(blob), "required": required}
        for role, member, blob, media, required in payloads
    ]
    digest = _sha(_canonical(records))
    export_key = _sha(f"{fingerprint}|{created}|{digest}".encode("utf-8"))
    manifest = {
        "format": "dragonwilds-sync-launcher",
        "version": 3,
        "packageType": "profile",
        "packageId": "browser-package-test",
        "createdAtUtc": created,
        "producer": {"application": "Dragonwilds Sync Web Builder", "version": "web-v1", "fingerprint": fingerprint},
        "profile": {"profileId": "browser-profile-hint", "profileName": "Web Builder Test World"},
        "layout": {"profileRoot": "profile/", "worldsRoot": "worlds/", "itemsRoot": "items/"},
        "payloads": records,
        "security": {"digestAlgorithm": "sha256", "payloadIndexSha256": digest, "exportKey": export_key, "trustMode": "website-draft"},
        "metadata": {"worldsIncluded": True, "worldSaveIncluded": True, "websiteDraft": True},
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        for _role, member, blob, _media, _required in payloads:
            archive.writestr(member, blob)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dws-web-draft-") as tmp:
        os.environ["DRAGONWILDS_SYNC_APPDATA"] = tmp
        from website_draft_import import inspect_website_draft, import_website_draft
        from profile_store import SERVER_PROFILES_DIR, load_server_profile

        package = Path(tmp) / "website-world.rsdwl"
        _build(package)
        inspected = inspect_website_draft(package)
        assert inspected["ok"] is True
        assert inspected["kind"] == "website-draft"
        assert inspected["signature_verified"] is False
        assert inspected["save"]["included"] is True
        assert inspected["save"]["file_count"] == 1

        result = import_website_draft(package)
        assert result["ok"] is True
        assert result["created_new_world"] is True
        assert result["fresh_local_authority"] is True
        assert result["server_started"] is False
        assert result["profile_id"] != "browser-profile-hint"
        assert result["save"]["included"] is True
        assert (SERVER_PROFILES_DIR / result["profile_id"] / "savegame" / "TestWorld.sav").is_file()

        profile = load_server_profile(result["profile_id"])
        assert profile["sync_config"]["server_key"]
        assert profile["sync_config"]["share_access_key"]
        assert profile["auto_ue4ss"] is True
        assert profile["auto_runeschema"] is True
        assert profile["release_channel"] == "experimental"
        assert profile["dedicated_config"]["port"] == 7788
        assert profile["dedicated_config"]["port_auto"] is False
        assert {"Family Friendly", "RuneSchema", "PAKs"}.issubset(set(profile["tags"]))
        assert profile["platform_compatibility"]["epic"] is True
        assert profile["platform_compatibility"]["nintendo"] is True
        assert profile["platform_compatibility"]["xbox"] is True
        assert profile["website_draft_import"]["trust_mode"] == "website-draft"

        no_save = Path(tmp) / "website-world-no-save.rsdwl"
        _build(no_save, save_mode="none")
        no_save_result = import_website_draft(no_save)
        assert no_save_result["save"]["included"] is False
        assert no_save_result["server_started"] is False

        zipped = Path(tmp) / "website-world-zipped-save.rsdwl"
        _build(zipped, save_mode="zip")
        zipped_result = import_website_draft(zipped)
        assert zipped_result["save"]["included"] is True
        assert (SERVER_PROFILES_DIR / zipped_result["profile_id"] / "savegame" / "Nested" / "TestWorld.sav").is_file()

        unsafe_zip = Path(tmp) / "website-world-unsafe-save.rsdwl"
        _build(unsafe_zip, save_mode="unsafe-zip")
        try:
            import_website_draft(unsafe_zip)
        except ValueError as exc:
            assert "unsafe" in str(exc).casefold() or "traversal" in str(exc).casefold()
        else:
            raise AssertionError("Website draft ZIP traversal must be rejected")

        bad = Path(tmp) / "website-world-malicious.rsdwl"
        _build(bad, malicious=True)
        try:
            inspect_website_draft(bad)
        except ValueError as exc:
            assert "prohibited" in str(exc).casefold()
        else:
            raise AssertionError("Website draft containing server_key must be rejected")

    print("website draft RSDWL regression passed")


if __name__ == "__main__":
    main()
