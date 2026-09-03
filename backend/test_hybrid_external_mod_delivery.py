from __future__ import annotations

import hashlib
import tempfile
import zipfile
from pathlib import Path

import external_mod_hosting as external


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeSync:
    @staticmethod
    def target_for_entry(root: Path, entry: dict) -> Path:
        return Path(root) / Path(*Path(str(entry["path"])).parts)

    @staticmethod
    def entry_allowed_for_platform(entry: dict, platform: str) -> bool:
        return True


def test_url_contracts() -> None:
    url, provider = external.normalize_external_url("https://www.dropbox.com/s/example/file.zip?dl=0", "auto")
    assert provider == "dropbox" and "dl=1" in url
    url, provider = external.normalize_external_url("https://drive.google.com/file/d/abc123/view?usp=sharing", "auto")
    assert provider == "google_drive" and "drive.usercontent.google.com" in url and "id=abc123" in url
    url, provider = external.normalize_external_url("https://1drv.ms/u/s!abc", "auto")
    assert provider == "onedrive" and "api.onedrive.com/v1.0/shares/u!" in url
    for bad in ("http://example.com/mod.zip", "https://127.0.0.1/mod.zip", "https://192.168.1.10/mod.zip"):
        try:
            external.normalize_external_url(bad, "direct_https")
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe URL accepted: {bad}")


def test_overlay_policy() -> None:
    assert external._allowed_overlay_entry({"path": "Content/Paks/~mods/Huge_P.pak"})
    assert external._allowed_overlay_entry({"path": "Binaries/Win64/ue4ss/Mods/FarmersQoL/Scripts/main.lua"})
    assert not external._allowed_overlay_entry({"path": "Binaries/Win64/ue4ss/Mods/DragonLink/dlls/main.dll"})
    assert not external._allowed_overlay_entry({"path": "Binaries/Win64/version.dll"})


def test_verified_overlay_archive() -> None:
    files = {
        "Content/Paks/~mods/Huge_P.pak": b"pak-bytes",
        "Content/Paks/~mods/Huge_P.utoc": b"utoc-bytes",
        "Content/Paks/~mods/Huge_P.ucas": b"ucas-bytes",
    }
    manifest = {"files": [
        {"path": path, "size": len(data), "sha256": digest(data), "kind": "file"}
        for path, data in files.items()
    ]}
    package = {
        "schema": external.PACKAGE_SCHEMA,
        "id": "pak_mod::Huge",
        "paths": list(files),
        "archive": {"sha256": "0" * 64, "size": 1},
    }
    with tempfile.TemporaryDirectory(prefix="dws-hybrid-test-") as td:
        root = Path(td)
        archive = root / "Huge.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, data in files.items():
                zf.writestr(path, data)
        staging = root / "stage"
        verified = external._verify_overlay_archive(FakeSync, package, manifest, archive, staging)
        assert {entry["path"] for entry, _ in verified} == set(files)

        extra = root / "extra.zip"
        with zipfile.ZipFile(extra, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, data in files.items():
                zf.writestr(path, data)
            zf.writestr("Content/Paks/~mods/Unexpected.dll", b"nope")
        try:
            external._verify_overlay_archive(FakeSync, package, manifest, extra, root / "stage-extra")
        except ValueError:
            pass
        else:
            raise AssertionError("extra package member was accepted")

        traversal = root / "traversal.zip"
        with zipfile.ZipFile(traversal, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("../escape.txt", b"nope")
        try:
            external._verify_overlay_archive(FakeSync, package, manifest, traversal, root / "stage-traversal")
        except ValueError:
            pass
        else:
            raise AssertionError("path traversal was accepted")


def test_one_mod_one_transport_metadata() -> None:
    class Unit:
        key = "pak_mod::Huge"
        name = "Huge"
        group = "pak_mod"
        classification = "player_required"

        def content_summary(self):
            return (3, 30, "fingerprint")

        def iter_files(self):
            return iter([
                ("Content/Paks/~mods/Huge.pak", Path("Huge.pak")),
                ("Content/Paks/~mods/Huge.ucas", Path("Huge.ucas")),
                ("Content/Paks/~mods/Huge.utoc", Path("Huge.utoc")),
            ])

    profile = {"unit_overrides": {"pak_mod::Huge": {"external_delivery": {
        "delivery": "external", "provider": "direct_https", "url": "https://cdn.example/Huge.zip",
        "fallback_to_server": True, "archive_sha256": "a" * 64, "archive_size": 999,
        "archive_name": "Huge.zip", "archive_mode": "overlay_archive",
        "archive_path": "prepared", "content_fingerprint": "fingerprint", "link_status": "ready",
    }}}}
    manifest = {"files": [
        {"path": "Content/Paks/~mods/Huge.pak", "size": 10, "sha256": "1" * 64, "kind": "file"},
        {"path": "Content/Paks/~mods/Huge.ucas", "size": 10, "sha256": "2" * 64, "kind": "file"},
        {"path": "Content/Paks/~mods/Huge.utoc", "size": 10, "sha256": "3" * 64, "kind": "file"},
    ]}

    class ServerSystems:
        @staticmethod
        def client_distribution_allowed_unit(unit):
            return True

    package = external._package_for_unit(ServerSystems, profile, Unit(), manifest)
    assert package and package["mode"] == "overlay_archive"
    assert set(package["paths"]) == {row["path"] for row in manifest["files"]}
    assert package["fallback"] == "server"


def test_platform_gate() -> None:
    manifest = {"files": [{"path": "Content/Paks/~mods/A.pak", "platforms": ["windows"]}]}
    package = {"paths": ["Content/Paks/~mods/A.pak"]}

    class PlatformSync:
        @staticmethod
        def entry_allowed_for_platform(entry, platform):
            return platform == "windows"

    assert external._package_allowed_for_platform(PlatformSync, manifest, package, "windows")
    assert not external._package_allowed_for_platform(PlatformSync, manifest, package, "linux")


def main() -> None:
    test_url_contracts()
    test_overlay_policy()
    test_verified_overlay_archive()
    test_one_mod_one_transport_metadata()
    test_platform_gate()
    print("verified hybrid Server/External mod delivery contracts: PASS")


if __name__ == "__main__":
    main()
