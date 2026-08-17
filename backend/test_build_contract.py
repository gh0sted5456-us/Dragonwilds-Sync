import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PS1 = ROOT / "scripts" / "build_windows.ps1"
PACKAGE = ROOT / "package.json"
SPEC = ROOT / "backend" / "DragonwildsSync.Service.spec"
BUILD_BAT = ROOT / "build.bat"
PROCESS_UTILS = ROOT / "backend" / "process_utils.py"
ELECTRON_MAIN = ROOT / "electron" / "main.cjs"


def main():
    text = PS1.read_text(encoding="utf-8")
    allowed_scopes = {"global", "local", "script", "private", "env", "using"}
    offenders = []
    for match in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*):", text):
        name = match.group(1).lower()
        if name not in allowed_scopes:
            line = text.count("\n", 0, match.start()) + 1
            offenders.append((line, match.group(0)))
    assert not offenders, f"unsafe PowerShell variable-colon interpolation: {offenders}"
    assert "$previousErrorActionPreference = $ErrorActionPreference" in text
    assert "$ErrorActionPreference = 'Continue'" in text
    assert "$ErrorActionPreference = $previousErrorActionPreference" in text
    assert 'if ($rc -ne 0)' in text
    assert 'Testing packaged service JSON-RPC stdio' in text
    assert '$probeInput' in text and '$probeOutput' in text
    assert 'Testing packaged Ed25519 generation' in text
    assert 'application.cryptography.status' in text and 'invalid_signature_rejected' in text

    required = [
        "backend\\server_systems.py", "backend\\health_model.py", "backend\\integrations.py",
        "backend\\network_health.py", "backend\\process_utils.py", "backend\\security_policy.py",
        "backend\\security_scanner.py", "backend\\server_layout.py", "backend\\client_layout.py",
        "backend\\character_profiles.py", "backend\\local_world.py", "backend\\network_benchmark.py",
        "backend\\guided_setup.py", "backend\\player_tracker.py", "backend\\server_scheduler.py",
        "backend\\world_save_distribution.py", "backend\\rsdwl_packages.py", "backend\\world_sharing.py",
        "backend\\profile_bundle.py", "resources\\recommended-mods.json", "backend\\requirements-build.txt",
        "backend\\DragonwildsSync.Service.spec", "backend\\crypto_runtime.py",
    ]
    for value in required:
        assert value in text, f"build script missing required contract: {value}"

    spec = SPEC.read_text(encoding="utf-8")
    assert "backend = Path(SPECPATH).resolve()" in spec
    assert "Path(SPECPATH).resolve().parent" not in spec
    assert "backend / 'dragonwilds_service.py'" in spec
    assert "collect_submodules('cryptography')" in spec
    assert "collect_dynamic_libs('cryptography')" in spec
    assert "renderer_assets = backend.parent / 'renderer' / 'assets'" in spec
    assert "renderer/assets/platforms" in spec, "packaged WebHost must contain platform/community SVGs"
    assert "console=True" in spec
    assert "upx=False" in spec
    requirements = (ROOT / "backend" / "requirements-build.txt").read_text(encoding="utf-8")
    assert "pyinstaller==6.22.0" in requirements.casefold()
    assert "cryptography>=46,<47" in requirements.casefold()
    assert "$expectedPyInstaller = '6.22.0'" in text
    assert "pip', 'install', '--upgrade'" in text
    assert "windowsHide: true" in ELECTRON_MAIN.read_text(encoding="utf-8")

    build_bat = BUILD_BAT.read_text(encoding="utf-8")
    assert "backend\\dragonwilds_service.py" in build_bat
    assert "scripts\\build_windows.ps1" in build_bat
    assert "pause" in build_bat.lower()
    assert "Dragonwilds Sync 2.0.0" in build_bat and "Portable Windows Build" in build_bat
    assert "Alpha 3.2" not in build_bat

    process_utils = PROCESS_UTILS.read_text(encoding="utf-8")
    assert "CREATE_NO_WINDOW" in process_utils
    assert "STARTF_USESHOWWINDOW" in process_utils
    electron_main = ELECTRON_MAIN.read_text(encoding="utf-8")
    assert "windowsHide: true" in electron_main
    for candidate in (ROOT / "backend").glob("*.py"):
        if candidate.name.startswith("test_") or candidate.name == "process_utils.py":
            continue
        live_text = candidate.read_text(encoding="utf-8")
        for direct_call in ("subprocess.Popen(", "subprocess.run(", "subprocess.check_output("):
            assert direct_call not in live_text, f"visible subprocess bypass in {candidate.name}: {direct_call}"

    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    assert package["version"] == "2.0.0"
    assert package["devDependencies"]["luaparse"] == "0.3.1"
    assert "scripts/check_ue4ss_lua.cjs" in package["scripts"]["check:renderer"]
    assert package["devDependencies"]["electron"] != "latest"
    assert package["devDependencies"]["electron-builder"] != "latest"
    assert package["devDependencies"]["monaco-editor"] == "0.52.2"
    assert package["devDependencies"]["@electron/asar"] == "4.2.1"
    assert package["scripts"]["prepare:monaco"] == "node scripts/prepare_monaco.cjs"
    assert package["scripts"]["package:raw"] == "node scripts/package_raw_source.cjs"
    monaco_prepare = (ROOT / "scripts" / "prepare_monaco.cjs").read_text(encoding="utf-8")
    assert "expectedVersion = '0.52.2'" in monaco_prepare
    assert "base', 'worker', 'workerMain.js" in monaco_prepare
    assert "AMD-compatible runtime" in monaco_prepare
    assert "--include=dev" in text
    assert "Packaged Monaco Editor runtime is present" in text
    assert "Verifying packaged Monaco + launcher resources" in text
    assert "DragonwildsSyncPlayerTracker" not in text
    assert "PersistentDirectConnectProfile-v0.4.0.zip" not in text
    assert "singleplayer-banner.png" in text
    assert "singleplayer-icon.png" in text
    assert "backend\\local_world.py" in text
    assert "electron/discord_rpc.cjs" in package["scripts"]["check:renderer"]
    assert "electron/app_updater.cjs" in package["scripts"]["check:renderer"]
    assert "electron/rsdw_webview_preload.cjs" in package["scripts"]["check:renderer"]
    assert "renderer/release-meta.js" in package["scripts"]["check:renderer"]
    assert package["build"]["win"]["target"] == ["portable"]
    assert "nsis" not in package["build"]
    assert package["build"]["portable"]["artifactName"] == "${productName}-Portable-${version}.${ext}"
    extra = package["build"].get("extraResources", [])
    assert any(x.get("from") == "resources" for x in extra)
    assert "RuneSchema-core-latest.zip" in text
    assert "$bundledRuneSchema = Join-Path $ProjectRoot 'resources\\RuneSchema-core-latest.zip'" in text
    raw_packager = (ROOT / "scripts" / "package_raw_source.cjs").read_text(encoding="utf-8")
    assert "DragonwildsSync_V2_Raw_Source" in raw_packager
    assert "RAW_SOURCE_CONTENTS.md" in raw_packager
    assert "node_modules" in raw_packager and "Codex Outputs" in raw_packager
    assert "Staging reproducible raw-source folder" not in text
    assert "Portable package still contains the removed RSDWTools UE4SS mod" in text
    assert "DRAGONWILDS_SYNC_PYTHON" in text
    assert "win-unpacked.tmp" in text
    assert "Clear-ReleaseDirectory" in text
    assert "Removing the previous release directory so only this build remains" in text
    assert "Release contains portable EXE artifacts only" in text

    assert "build:linux" not in package["scripts"]
    assert "linux" not in package["build"]
    assert not (ROOT / "build-linux.sh").exists()
    assert not (ROOT / "scripts" / "build_linux.sh").exists()
    assert not (ROOT / ".github" / "workflows" / "linux-build.yml").exists()
    assert not (ROOT / "docs" / "LINUX_BUILD.md").exists()
    assert (ROOT / "docs" / "CAPABILITIES.md").is_file()
    print("build contract tests passed")


if __name__ == "__main__":
    main()
