from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import local_world
import server_engine
import sync_engine
from client_layout import resolve_client_layout
from server_systems import ModUnit


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def by_key(rows: list[dict]) -> dict[str, dict]:
    return {str(row["key"]): row for row in rows}


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        original_local_profile_dir = local_world.LOCAL_PROFILE_DIR
        original_private_profiles_dir = local_world.PRIVATE_PROFILES_DIR
        local_world.LOCAL_PROFILE_DIR = root / "profiles" / "singleplayer"
        local_world.PRIVATE_PROFILES_DIR = root / "profiles"
        local_world.save_profile(local_world.default_singleplayer_profile())
        install = root / "client"
        game = install / "RSDragonwilds"
        (game / "Content" / "Paks").mkdir(parents=True)
        layout = resolve_client_layout(install)
        alpha = layout.ue4ss_mods_dir / "Alpha"
        beta = layout.ue4ss_mods_dir / "Beta"
        alpha.mkdir(parents=True); beta.mkdir(parents=True)
        (alpha / "main.lua").write_text("return 'alpha-v1'\n", encoding="utf-8")
        (beta / "main.lua").write_text("return 'beta-v1'\n", encoding="utf-8")

        before = by_key(local_world.scan_inventory(str(install), live=True))
        alpha_before = before["ue4ss_mod::Alpha"]["content_hash"]
        beta_before = before["ue4ss_mod::Beta"]["content_hash"]
        assert len(alpha_before) == 64 and len(beta_before) == 64
        assert ModUnit(name="Alpha", group="ue4ss_mod", source_dir=alpha).public()["content_hash"] == alpha_before

        profile_file = local_world._profile_file(local_world.SINGLEPLAYER_ID)
        profile_before = profile_file.read_bytes()
        character = root / "SaveCharacters" / "hero.sav"
        character.parent.mkdir(parents=True)
        character.write_bytes(b"character-sentinel")
        character_before = file_sha(character)

        original_client_worlds = sync_engine.CLIENT_WORLDS_DIR
        sync_engine.CLIENT_WORLDS_DIR = root / "client-worlds"
        try:
            snapshot = sync_engine.client_world_dir("singleplayer")
            cached_alpha = snapshot / "mods" / "UE4SS" / "Alpha"
            cached_beta = snapshot / "mods" / "UE4SS" / "Beta"
            cached_alpha.mkdir(parents=True); cached_beta.mkdir(parents=True)
            (cached_alpha / "main.lua").write_text("return 'alpha-v1'\n", encoding="utf-8")
            (cached_beta / "main.lua").write_text("return 'beta-v1'\n", encoding="utf-8")
            world_sentinel = snapshot / "configs" / "game" / "GameUserSettings.ini"
            world_sentinel.parent.mkdir(parents=True)
            world_sentinel.write_bytes(b"world-settings-sentinel")
            beta_snapshot_before = file_sha(cached_beta / "main.lua")
            beta_mtime_before = (cached_beta / "main.lua").stat().st_mtime_ns
            world_before = file_sha(world_sentinel)

            result = local_world.save_mod_file(str(install), "ue4ss_mod::Alpha", "main.lua", "return 'alpha-v2'\n", live=True)
            assert result["hash_changed"] is True
            assert result["previous_content_hash"] == alpha_before
            sync_result = sync_engine.snapshot_client_mod_unit("singleplayer", install, "ue4ss_mod::Alpha")
            assert sync_result["copied"] >= 1

            after = by_key(local_world.scan_inventory(str(install), live=True))
            assert after["ue4ss_mod::Alpha"]["content_hash"] == result["content_hash"]
            assert after["ue4ss_mod::Alpha"]["content_hash"] != alpha_before
            assert after["ue4ss_mod::Beta"]["content_hash"] == beta_before
            assert file_sha(cached_beta / "main.lua") == beta_snapshot_before
            assert (cached_beta / "main.lua").stat().st_mtime_ns == beta_mtime_before
            assert file_sha(world_sentinel) == world_before
            assert file_sha(character) == character_before
            assert profile_file.read_bytes() == profile_before
            assert (cached_alpha / "main.lua").read_text(encoding="utf-8") == "return 'alpha-v2'\n"

            legacy_rune = layout.runeschema_root / "Gamma"
            legacy_rune.mkdir(parents=True)
            (legacy_rune / "recipe.json").write_text('{"value": 1}\n', encoding="utf-8")
            rune_result = sync_engine.snapshot_client_mod_unit("singleplayer", install, "runeschema_mod::Gamma")
            assert rune_result["copied"] == 1
            assert (snapshot / "mods" / "RuneSchema" / "Gamma" / "recipe.json").is_file()
        finally:
            sync_engine.CLIENT_WORLDS_DIR = original_client_worlds

        server_profile_root = root / "server-profile"
        original_profile_dir = server_engine._profile_mods_dir
        server_engine._profile_mods_dir = lambda _profile_id: server_profile_root / "mods"
        try:
            server_snapshot_beta = server_profile_root / "mods" / "UE4SS" / "Beta" / "main.lua"
            server_snapshot_beta.parent.mkdir(parents=True)
            server_snapshot_beta.write_bytes(b"server-beta-sentinel")
            server_beta_before = file_sha(server_snapshot_beta)
            server_engine.snapshot_profile_mod_unit("world-a", game, "ue4ss_mod::Alpha")
            assert file_sha(server_snapshot_beta) == server_beta_before
            assert (server_profile_root / "mods" / "UE4SS" / "Alpha" / "main.lua").read_text(encoding="utf-8") == "return 'alpha-v2'\n"
        finally:
            server_engine._profile_mods_dir = original_profile_dir
            local_world.LOCAL_PROFILE_DIR = original_local_profile_dir
            local_world.PRIVATE_PROFILES_DIR = original_private_profiles_dir

    print("per-mod content hash and real-time isolation tests passed")


if __name__ == "__main__":
    main()
