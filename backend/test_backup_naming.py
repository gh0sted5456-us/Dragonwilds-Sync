from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import backup_naming
import world_operations


def test_backup_template_is_sanitized_and_tokenized():
    name = backup_naming.render_backup_name(
        "{world}-{date}-{time}-{kind}", suffix=".zip",
        world="Effing: Desync / Main", kind="manual", now=1_700_000_000)
    assert name.endswith(".zip")
    assert ":" not in name and "/" not in name and "\\" not in name
    assert "Effing_ Desync _ Main" in name


def test_unknown_backup_token_is_rejected():
    try:
        backup_naming.normalize_template("{world}-{shell}")
    except ValueError as exc:
        assert "{shell}" in str(exc)
    else:
        raise AssertionError("unknown template token was accepted")


def test_local_world_archive_uses_selected_template():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        saves = root / "SaveGames"; saves.mkdir(); (saves / "World.sav").write_bytes(b"save")
        archives = root / "archives"
        with patch.object(world_operations, "CLIENT_SAVEGAMES", saves), patch.object(world_operations, "ARCHIVE_ROOT", archives):
            result = world_operations.archive_private("Test World", name_template="{world}-{kind}-{date}")
        archive = Path(result["archive_path"])
        assert archive.is_file()
        assert archive.name.startswith("Test World-singleplayer-")
