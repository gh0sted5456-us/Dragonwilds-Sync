import tempfile
import zipfile
from pathlib import Path

from world_operations import import_worldsave_archive


def main():
    with tempfile.TemporaryDirectory() as root_value:
        root = Path(root_value)
        archive = root / "world.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("WorldOne.sav", b"save-data")
            zf.writestr("Players/player.sav", b"player-data")
        result = import_worldsave_archive(archive, root / "imported")
        assert result["file_count"] == 2
        assert (root / "imported" / "WorldOne.sav").read_bytes() == b"save-data"
        assert (root / "imported" / "Players" / "player.sav").read_bytes() == b"player-data"

        unsafe = root / "unsafe.zip"
        with zipfile.ZipFile(unsafe, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("../outside.sav", b"blocked")
        try:
            import_worldsave_archive(unsafe, root / "unsafe-import")
        except ValueError as exc:
            assert "Unsafe World save archive path" in str(exc)
        else:
            raise AssertionError("Traversal archive was accepted")
        assert not (root / "outside.sav").exists()
    print("World-save archive import safety contracts passed")


if __name__ == "__main__":
    main()
