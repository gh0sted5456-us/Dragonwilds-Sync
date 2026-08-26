from __future__ import annotations

import json
import zipfile
from pathlib import Path

import dragonwilds_service_v2_wrapper as service
import runeschema_tools


EXPECTED_SCHEMA_TYPES = {
    "utility", "assets", "blueprints", "buildings", "courses", "enums",
    "journal", "raw", "recipes", "spawns", "strings",
}


def main() -> None:
    archive_path = Path(__file__).parent.parent / "resources" / "RuneSchema-experimental-latest.zip"
    with zipfile.ZipFile(archive_path) as archive:
        raw = archive.read("RuneSchema/config/config.json").decode("utf-8")

    detected = runeschema_tools.detect_variant({}, raw)
    assert detected["variant"] == "experimental"
    assert detected["version"] == "0.6.3 Experimental"

    parsed = service._parse_runeschema_settings(raw)
    assert set(parsed["tooling"]["schemaTypes"]) == EXPECTED_SCHEMA_TYPES
    parsed["tooling"]["schemaTypes"]["buildings"] = False
    parsed["tooling"]["schemaTypes"]["spawns"] = False

    serialized = json.loads(service._serialize_runeschema_settings(parsed))
    assert set(serialized["tooling"]["schemaTypes"]) == EXPECTED_SCHEMA_TYPES
    assert serialized["tooling"]["schemaTypes"]["buildings"] is False
    assert serialized["tooling"]["schemaTypes"]["spawns"] is False
    assert serialized["identityOverrides"] == parsed["identityOverrides"]
    assert serialized["spawnSafety"] == parsed["spawnSafety"]
    print("RuneSchema 0.6.3 Experimental Console function/config round-trip passed")


if __name__ == "__main__":
    main()
