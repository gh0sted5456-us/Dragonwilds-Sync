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
ELECTRON_MAIN_V2 = ROOT / "electron" / "main-v2.cjs"
ELECTRON_PRELOAD_V2 = ROOT / "electron" / "preload-v2.cjs"


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
    assert 'Testing packaged headless CLI output and exit code' in text
    assert 'Dragonwilds Sync Headless-$packageVersion.exe' in text
    assert '$probeInput' in text and '$probeOutput' in text
    assert 'Testing packaged Ed25519 generation' in text
    assert 'application.cryptography.status' in text and 'invalid_signature_rejected' in text
    assert "build-service\\packaged-probe-appdata" in text, "packaged service probes must use build-local disposable AppData"
    assert "$env:DRAGONWILDS_SYNC_APPDATA = $probeAppData" in text, "packaged service probes must not use real user AppData"
    assert "GetEnvironmentVariable('DRAGONWILDS_SYNC_APPDATA', 'Process')" in text, "build must preserve any caller-provided AppData override"
    assert "Remove-Item Env:DRAGONWILDS_SYNC_APPDATA" in text, "build must restore an originally unset AppData override"
    assert "$env:DRAGONWILDS_SYNC_APPDATA = $previousProbeAppData" in text, "build must restore an existing AppData override"
    assert 'finally {' in text and 'Remove-Item -LiteralPath $probeAppData -Recurse -Force -ErrorAction SilentlyContinue' in text

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
    assert "console=True" in spec, "JSON-RPC service must retain stdin/stdout in the packaged build"
    assert "upx=False" in spec, "service build should avoid UPX variability"
    requirements = (ROOT / "backend" / "requirements-build.txt").read_text(encoding="utf-8")
    assert "pyinstaller==6.22.0" in requirements.casefold()
    assert "cryptography>=46,<47" in requirements.casefold()
    assert "$expectedPyInstaller = '6.22.0'" in text
    assert "pip', 'install', '--upgrade'" in text
    assert "windowsHide: true" in ELECTRON_MAIN_V2.read_text(encoding="utf-8")

    process_utils = PROCESS_UTILS.read_text(encoding="utf-8")
    assert "def popen_game_server(" in process_utils
    assert "CREATE_NEW_CONSOLE" in process_utils, "UE4SS requires a valid Win32 console allocation"
    assert "CREATE_NO_WINDOW" in process_utils, "background helpers should remain windowless"
    server_engine = (ROOT / "backend" / "server_engine.py").read_text(encoding="utf-8")
    phase4_startup = (ROOT / "backend" / "phase4_runtime_startup.py").read_text(encoding="utf-8")
    assert "popen_game_server(" in server_engine
    assert "popen_game_server(" in phase4_startup

    main_v2 = ELECTRON_MAIN_V2.read_text(encoding="utf-8")
    renderer_v2 = (ROOT / "renderer" / "app-v2.js").read_text(encoding="utf-8")
    trash_v2 = (ROOT / "renderer" / "release-v2-trash.js").read_text(encoding="utf-8")
    assert "skipTaskbar: false" in main_v2, "detached application windows must be real taskbar windows"
    assert "openNative(shellNode.innerHTML" in trash_v2, "Trash must open in a native application window"
    assert "Return to Application" in renderer_v2

    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    build_bat = BUILD_BAT.read_text(encoding="utf-8")
    assert "backend\\dragonwilds_service.py" in build_bat
    assert "scripts\\build_windows.ps1" in build_bat
    assert "pause" in build_bat.lower()
    assert f"Dragonwilds Sync {package['version']}" in build_bat and "Portable Windows Build" in build_bat
    assert "Alpha 3.2" not in build_bat

    process_utils = PROCESS_UTILS.read_text(encoding="utf-8")
    assert "CREATE_NO_WINDOW" in process_utils
    assert "STARTF_USESHOWWINDOW" in process_utils
    electron_main = ELECTRON_MAIN_V2.read_text(encoding="utf-8")
    assert "windowsHide: true" in electron_main
    assert "beginVisualApplicationExit();" in electron_main, "application close must hide the launcher before verified backend cleanup"
    electron_preload_v2 = ELECTRON_PRELOAD_V2.read_text(encoding="utf-8")
    assert "preload: path.join(__dirname, 'preload-v2.cjs')" in electron_main
    assert "sandbox: true" in electron_main
    assert "require('./preload" not in electron_preload_v2 and 'require("./preload' not in electron_preload_v2
    assert "exposeInMainWorld('dragonwilds'" in electron_preload_v2
    assert "exposeInMainWorld('dragonwildsV3'" in electron_preload_v2

    # Process spawning remains centralized. The only intentional exception is
    # WorkerSupervisor, whose job is specifically to launch the same packaged
    # backend in authenticated --runtime-worker mode. It is a process-management
    # boundary below AuthoritativeRuntimeManager, not a lifecycle-policy bypass.
    direct_spawn_owners = {"worker_supervisor.py"}
    for candidate in (ROOT / "backend").glob("*.py"):
        if candidate.name.startswith("test_") or candidate.name == "process_utils.py":
            continue
        live_text = candidate.read_text(encoding="utf-8")
        for direct_call in ("subprocess.Popen(", "subprocess.run(", "subprocess.check_output("):
            if direct_call in live_text:
                assert candidate.name in direct_spawn_owners, f"visible subprocess bypass in {candidate.name}: {direct_call}"

    worker_supervisor = (ROOT / "backend" / "worker_supervisor.py").read_text(encoding="utf-8")
    assert "subprocess.Popen(self._worker_command(" in worker_supervisor, "WorkerSupervisor must own runtime-worker process creation"
    assert '"--runtime-worker"' in worker_supervisor, "worker spawn must use the same packaged application worker mode"
    assert "DWSYNC_DISABLE_RUNTIME_WORKERS" not in worker_supervisor, "rollback policy belongs above WorkerSupervisor"

    assert package["version"] == "3.0.5"
    assert package["devDependencies"]["luaparse"] == "0.3.1"
    assert "scripts/check_ue4ss_lua.cjs" in package["scripts"]["check:renderer"]
    assert package["devDependencies"]["electron"] != "latest"
    assert package["devDependencies"]["electron-builder"] != "latest"
    assert package["devDependencies"]["monaco-editor"] == "0.52.2"
    assert package["devDependencies"]["@electron/asar"] == "4.2.1"
    assert package["scripts"]["prepare:monaco"] == "node scripts/prepare_monaco.cjs"
    assert package["scripts"]["package:raw"] == "node scripts/package_raw_source.cjs"
    assert package["scripts"]["test:preload"] == "electron scripts/check_preload_bridge_electron.cjs"
    monaco_prepare = (ROOT / "scripts" / "prepare_monaco.cjs").read_text(encoding="utf-8")
    assert "expectedVersion = '0.52.2'" in monaco_prepare
    assert "base', 'worker', 'workerMain.js" in monaco_prepare
    assert "AMD-compatible runtime" in monaco_prepare
    assert "--include=dev" in text
    assert "Packaged Monaco Editor runtime is present" in text
    assert "Verifying packaged Monaco + launcher resources" in text
    assert "@('run', 'test:preload')" in text
    assert "DragonwildsSyncPlayerTracker" not in text
    assert "PersistentDirectConnectProfile-v0.4.0.zip" not in text
    assert "singleplayer-banner.webp" in text
    assert "singleplayer-icon.webp" in text
    assert "backend\\local_world.py" in text
    assert "electron/discord_rpc.cjs" in package["scripts"]["check:renderer"]
    assert "electron/app_updater.cjs" in package["scripts"]["check:renderer"]
    assert "electron/rsdw_webview_preload.cjs" in package["scripts"]["check:renderer"]
    assert "electron/preload-v2.cjs" in package["scripts"]["check:renderer"]
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
    assert "resources\\RSDWTools-baseline.zip" not in text
    resource_bundle = next(x for x in extra if x.get("from") == "resources")
    assert "!RSDWTools-baseline.zip" in resource_bundle.get("filter", [])
    assert "!renderer/assets/help/**/*" in package["build"]["files"]
    systems = (ROOT / "backend" / "server_systems.py").read_text(encoding="utf-8")
    assert 'RSDW_DEVKIT_RELEASES_URL = "https://github.com/RSDWArchive/RSDWDevKit/releases"' in systems
    assert 'APP_DATA_DIR / "runtime_downloads" / "rsdw_devkit"' in systems
    assert "download_runtime_zip(" in systems
    client_runtime = systems[systems.index("def ensure_client_base_runtimes"):systems.index("def install_ue4ss_zip")]
    assert "ensure_rsdwtools_baseline" not in client_runtime
    assert "DRAGONWILDS_SYNC_PYTHON" in text
    assert "win-unpacked.tmp" in text
    assert "Clear-ReleaseDirectory" in text
    assert "Removing previous release artifacts (locked running portables are preserved)" in text
    assert "Preserving locked release artifact" in text
    assert "Release contains portable EXE artifacts only" in text

    # Ubuntu is an additional release-candidate path; Windows portable remains
    # the production baseline and keeps all of the assertions above.
    assert package["scripts"]["build:linux"] == "bash scripts/build_linux.sh"
    assert package["build"]["linux"]["target"] == ["AppImage"]
    assert package["build"]["linux"]["artifactName"] == "${productName}-Ubuntu-${version}.${ext}"
    assert package["build"]["linux"]["extraResources"][0]["from"] == "dist-service/DragonwildsSync.Service"
    linux_script = ROOT / "scripts" / "build_linux.sh"
    assert linux_script.is_file()
    linux_text = linux_script.read_text(encoding="utf-8")
    assert "Ubuntu is the supported baseline" in linux_text
    assert "backend/DragonwildsSync.Service.spec" in linux_text
    assert "npm run verify" in linux_text
    assert "xvfb-run -a npm run test:preload" in linux_text
    assert linux_text.index("node node_modules/electron/install.js") < linux_text.index("chown root:root node_modules/electron/dist/chrome-sandbox")
    assert "chown root:root node_modules/electron/dist/chrome-sandbox" in linux_text
    assert "chmod 4755 node_modules/electron/dist/chrome-sandbox" in linux_text
    assert "--no-sandbox" not in linux_text, "Linux preload verification must not weaken Chromium sandboxing"
    assert "electron-builder --linux AppImage" in linux_text
    assert 'HEADLESS_ARCHIVE="release/${HEADLESS_NAME}.tar.gz"' in linux_text
    assert 'tar -C release -czf "$HEADLESS_ARCHIVE" "$HEADLESS_NAME"' in linux_text
    linux_package_test = (ROOT / "scripts" / "test_packaged_linux.sh").read_text(encoding="utf-8")
    assert "archive preserves executable permissions" in linux_package_test
    release_workflow = (ROOT / ".github" / "workflows" / "release-candidate.yml").read_text(encoding="utf-8")
    assert "Dragonwilds-Sync-Headless-Ubuntu-*.tar.gz" in release_workflow
    assert "Linux headless archive did not preserve executable permissions" in release_workflow
    assert "process.platform === 'win32' ? 'DragonwildsSync.Service.exe' : 'DragonwildsSync.Service'" in electron_main
    assert (ROOT / "docs" / "CAPABILITIES.md").is_file()
    print("build contract tests passed")


if __name__ == "__main__":
    main()
