from __future__ import annotations

import json
import tempfile
from pathlib import Path

import shared_mod_repository as repository


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        repository.REPOSITORY_ROOT = root / "repository"
        repository.PAYLOAD_ROOT = repository.REPOSITORY_ROOT / "payloads"
        repository.INDEX_PATH = repository.REPOSITORY_ROOT / "index.json"
        repository.LOCAL_PROFILES_DIR = root / "local"
        repository.SERVER_PROFILES_DIR = root / "dedicated"

        for profile_id, text in (("world-a", "first"), ("world-b", "older")):
            profile = repository.LOCAL_PROFILES_DIR / profile_id
            write_json(profile / "profile.json", {
                "name": profile_id,
                "unit_overrides": {"runeschema_mod::SharedSchema": {
                    "source": {"provider": "nexus", "mod_id": 42, "version": "1.0"}
                }},
            })
            payload = profile / "snapshot" / "mods" / "ue4ss_mods" / "RuneSchema" / "mods" / "SharedSchema"
            payload.mkdir(parents=True)
            (payload / "schema.json").write_text(text, encoding="utf-8")

        scanned = repository.refresh_repository()
        assert len(scanned["entries"]) == 1
        assert len(scanned["entries"][0]["profiles"]) == 2

        source = repository.LOCAL_PROFILES_DIR / "world-a" / "snapshot" / "mods" / "ue4ss_mods" / "RuneSchema" / "mods" / "SharedSchema"
        (source / "new-schema.json").write_text("new", encoding="utf-8")
        result = repository.publish_from_profile("local", "world-a", "runeschema_mod::SharedSchema", propagate=True)
        target = repository.LOCAL_PROFILES_DIR / "world-b" / "snapshot" / "mods" / "ue4ss_mods" / "RuneSchema" / "mods" / "SharedSchema"
        assert (target / "schema.json").read_text(encoding="utf-8") == "first"
        assert (target / "new-schema.json").read_text(encoding="utf-8") == "new"
        assert len(result["deployed"]) == 1

    project = Path(__file__).resolve().parents[1]
    renderer = (project / "renderer" / "app.js").read_text(encoding="utf-8")
    profile_bundle = (project / "backend" / "profile_bundle.py").read_text(encoding="utf-8")
    service = (project / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
    maintenance = (project / "backend" / "world_maintenance.py").read_text(encoding="utf-8")
    assert "const pageSize=40" in renderer
    assert '"items/manifest.json"' in profile_bundle and '"itemsRoot": "items/"' in profile_bundle
    assert "application.custom_items.write_to_mod" in service and '"icon-manifest.json"' in service
    assert "origin_label" in maintenance and "config-origin-group" in renderer

    print("V2.0.0 shared mod repository tests passed")


if __name__ == "__main__":
    main()
