import tempfile
import unittest
from pathlib import Path

from profile_importer import build_import_plan, import_into_profile


class ProfileImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = self.root / "profile"
        self.server = self.root / "server"
        self.game = self.server / "RSDragonwilds"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, content=b"content"):
        target = self.game / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def populate_server(self):
        self.write("Binaries/Win64/ue4ss/UE4SS.dll", b"loader")
        self.write("Binaries/Win64/dwmapi.dll", b"shim")
        self.write("Binaries/Win64/ue4ss/Mods/CoolMod/scripts/main.lua", b"ue4ss")
        self.write("Binaries/Win64/ue4ss/Mods/RuneSchema/core.dll", b"rune-core")
        self.write("Binaries/Win64/ue4ss/Mods/RuneSchema/mods/Items/assets.json", b"rune-mod")
        self.write("Content/Paks/~mods/BetterBuilding.pak", b"pak")
        self.write("Content/Paks/~mods/BetterBuilding.pak.sig", b"sig")
        self.write("Saved/Config/WindowsServer/Game.ini", b"config")
        self.write("Binaries/Win64/RSDragonwildsServer.exe", b"steam-owned")

    def test_server_import_classifies_verifies_and_cleans_only_imported_files(self):
        self.populate_server()
        plan = build_import_plan(self.profile, self.server)
        self.assertEqual(plan["source_kind"], "server")
        self.assertEqual(plan["file_count"], 8)
        receipt = import_into_profile(self.profile, self.server)
        staged = self.profile / "staged"
        self.assertEqual((staged / "loaders/ue4ss/Binaries/Win64/ue4ss/UE4SS.dll").read_bytes(), b"loader")
        self.assertEqual((staged / "mods/ue4ss/CoolMod/scripts/main.lua").read_bytes(), b"ue4ss")
        self.assertEqual((staged / "mods/runeschema/Items/assets.json").read_bytes(), b"rune-mod")
        self.assertEqual((staged / "mods/paks/BetterBuilding/BetterBuilding.pak").read_bytes(), b"pak")
        self.assertEqual((staged / "mods/paks/BetterBuilding/BetterBuilding.pak.sig").read_bytes(), b"sig")
        self.assertFalse((self.game / "Saved/Config/WindowsServer/Game.ini").exists())
        self.assertTrue((self.game / "Binaries/Win64/RSDragonwildsServer.exe").is_file())
        self.assertEqual(receipt["cleaned"], 8)
        self.assertTrue((Path(receipt["recovery"]) / "receipt.json").is_file())

    def test_conflict_requires_approval_and_preserves_source(self):
        (self.game / "Binaries/Win64").mkdir(parents=True)
        self.write("Saved/Config/WindowsServer/Game.ini", b"config")
        source = self.write("Content/Paks/~mods/Test.pak", b"new")
        destination = self.profile / "staged/mods/paks/Test/Test.pak"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"old")
        plan = build_import_plan(self.profile, self.server)
        self.assertEqual(plan["conflicts"], 1)
        with self.assertRaisesRegex(ValueError, "replacement approval"):
            import_into_profile(self.profile, self.server)
        self.assertEqual(source.read_bytes(), b"new")
        self.assertEqual(destination.read_bytes(), b"old")
        receipt = import_into_profile(self.profile, self.server, replace_conflicts=True)
        self.assertEqual(destination.read_bytes(), b"new")
        self.assertFalse(source.exists())
        self.assertTrue(any((Path(receipt["recovery"]) / "replaced").rglob("*")))

    def test_layered_profile_import(self):
        source = self.root / "old-profile/staged"
        mod = source / "mods/ue4ss/Example/scripts/main.lua"
        mod.parent.mkdir(parents=True)
        mod.write_bytes(b"profile-mod")
        receipt = import_into_profile(self.profile, source.parent, cleanup_source=False)
        self.assertEqual(receipt["source_kind"], "profile")
        self.assertTrue(mod.is_file())
        self.assertEqual((self.profile / "staged/mods/ue4ss/Example/scripts/main.lua").read_bytes(), b"profile-mod")


if __name__ == "__main__":
    unittest.main()
