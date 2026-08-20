const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`${label}: missing ${JSON.stringify(needle)}`);
};
const forbidText = (text, needle, label) => {
  if (text.includes(needle)) throw new Error(`${label}: forbidden ${JSON.stringify(needle)}`);
};
const requireOrder = (text, needles, label) => {
  let cursor = -1;
  for (const needle of needles) {
    const next = text.indexOf(needle, cursor + 1);
    if (next < 0) throw new Error(`${label}: missing ${JSON.stringify(needle)}`);
    if (next <= cursor) throw new Error(`${label}: ${JSON.stringify(needle)} is out of order`);
    cursor = next;
  }
};

const app = read('renderer/app.js');
const css = read('renderer/release-overrides.css');
const responsiveCss = read('renderer/release-responsiveness.css');
const phase4Renderer = read('renderer/release-v3-phase4.js');
const preload = read('electron/preload.cjs');
const bootstrap = read('electron/bootstrap.cjs');
const main = read('electron/main.cjs');
const service = read('backend/dragonwilds_service.py');
const legacyService = read('backend/dragonwilds_service_legacy.py');
const runtimeManager = read('backend/runtime_manager.py');
const runtimeVersions = read('backend/runtime_versions.py');
const managedUpdates = read('backend/managed_updates.py');
const directoryHost = read('backend/directory_host.py');
const directoryWeb = read('backend/directory_web_legacy.py');
const serverSystems = read('backend/server_systems.py');
const serverEngine = read('backend/server_engine.py');
const syncEngine = read('backend/sync_engine.py');
const steamcmdTest = read('backend/test_steamcmd_server_update.py');
const postVerifyTest = read('backend/test_dedicated_post_verify.py');
const orphanWatchdogTest = read('backend/test_orphan_watchdog.py');
const unifiedUpdateTest = read('backend/test_unified_update_status.py');
const remoteLifecycleTest = read('backend/test_release1_4_web_directory_remote.py');
const runtimeManagerTest = read('backend/test_runtime_manager.py');

// Supplied placards must be a first-class World-card surface rather than a fallback texture.
requireText(app, "const PLACARD_BACKGROUNDS = ['1','2','3','4'];", 'placard asset contract');
requireText(app, 'class="world-card app-world-placard has-placard', 'CSS-layer placard card renderer');
requireText(app, '--world-placard:url(', 'placard artwork variable');
requireText(responsiveCss, '.world-card.has-placard::before', 'full-card placard background layer');
requireText(responsiveCss, '.world-card.has-placard>.world-card-banner', 'placard banner suppression');
requireText(app, 'world-card-inner', 'website-parity flip card structure');
requireText(app, 'world-card-face world-card-back', 'website-parity details face');
requireText(responsiveCss, '.app-world-placard.flipped .world-card-inner', 'website-parity flip motion');
requireText(phase4Renderer, "card.classList.contains('app-world-placard')", 'single website-parity placard model');
requireText(phase4Renderer, "card.classList.toggle('flipped'", 'Phase 4 uses the shared website flip state');
requireText(app, 'function renderUnsafe()', 'renderer recovery boundary');
requireText(app, 'renderer-recovery-root', 'visible renderer recovery surface');
requireText(css, 'opacity:.78 !important', 'placard full-card visibility');
requireText(css, '.recommended-mod-card', 'compact Recommended Mods');

// Application-owned dialogs stay in renderer; genuine websites keep the browser bridge.
forbidText(preload, 'openManagedDialog:', 'in-app dialog contract');
forbidText(preload, 'managedDialogContent:', 'in-app dialog contract');
requireText(preload, 'openInAppBrowser:', 'external website browser contract');

// Minimal Mode retains server lifecycle/scheduler but suppresses desktop/client background work.
requireText(bootstrap, "process.argv.includes('--minimal-mode')", 'Minimal Mode detection');
for (const name of ['maybeBenchmark', 'backgroundTick', 'rsdwModuleTick']) requireText(bootstrap, `'${name}'`, `Minimal Mode ${name} suppression`);
forbidText(bootstrap, "'schedulerTick'", 'Minimal Mode must not suppress server scheduler');
requireText(main, 'createMinimalWindow(worldId)', 'Minimal Mode selected-world launch');
requireText(app, 'Minimal Mode · Dedicated World', 'Minimal Mode dedicated surface');
requireText(app, 'Update &amp; Restart', 'Minimal Mode update/restart control');

// Phase 1: one runtime authority and verified shutdown.
requireText(service, 'RUNTIME = AuthoritativeRuntimeManager', 'authoritative runtime controller');
requireText(main, "serviceInvoke('application.shutdown'", 'full application shutdown');
for (const phase of ['Starting', 'Stopping', 'Restarting', 'Updating', 'Start Failed', 'Stop Failed', 'Restart Failed', 'Update Failed']) requireText(runtimeManager, `"${phase}"`, `runtime lifecycle phase ${phase}`);
requireText(runtimeManager, 'A server lifecycle operation is already active', 'conflicting command lock');
requireText(runtimeManager, 'exited unexpectedly', 'unexpected process exit reconciliation');
requireText(runtimeManager, 'broadcast_verified', 'broadcast lifecycle verification');
requireText(runtimeManager, 'component: str = "Dedicated Server"', 'generic managed update lifecycle');
requireText(runtimeManager, 'web_management_stopped', 'verified WebGUI shutdown');
requireText(runtimeManager, 'The Sync advertisement remained active during launcher shutdown.', 'verified broadcast shutdown');

// Process before broadcast: prepare, launch, verify/guard, watchdog, then publish.
requireText(runtimeManager, 'def _start_verified', 'process-before-broadcast helper');
requireOrder(runtimeManager, [
  'prepared = self.engine.scan_mods(profile_id)',
  'started = self.engine.start_dedicated(profile_id)',
  'after_process = self._actual()',
  'watchdog = self._arm_watchdog(server_pid)',
  'published = self.engine.publish(profile_id)',
], 'process-before-broadcast ordering');
forbidText(runtimeManager, 'self.engine.start_world(', 'authoritative lifecycle must not use publish-first start_world');
requireText(runtimeManager, 'self.engine.stop_world()', 'failed post-launch cleanup');
requireText(runtimeManager, 'Sync became available before dedicated-process verification completed.', 'early advertisement guard');

// Catastrophic backend exit must not orphan the real dedicated process tree.
requireText(runtimeManager, 'def _launch_orphan_watchdog', 'orphan watchdog launcher');
requireText(runtimeManager, 'taskkill.exe /PID $serverPid /T /F', 'Windows orphan process-tree termination');
requireText(runtimeManager, 'kill -KILL "$target"', 'POSIX orphan process termination');
requireText(runtimeManager, 'self.engine.__class__.__module__ == "server_engine"', 'watchdog production-engine boundary');
requireText(orphanWatchdogTest, 'catastrophic dedicated-server orphan watchdog contract passed', 'orphan watchdog regression');

// Authenticated WebGUI state is projected from the same manager.
requireText(runtimeManager, 'def _install_directory_state_bridge', 'WebGUI authoritative state bridge');
requireText(runtimeManager, 'host.set_remote_admin_callbacks = bridged_set_remote_admin_callbacks', 'WebGUI callback bridge installation');
requireText(runtimeManager, '"busy": bool(lifecycle.get("busy"))', 'WebGUI busy lifecycle state');
requireText(runtimeManager, '"last_error": lifecycle.get("last_error") or ""', 'WebGUI lifecycle error state');
requireText(runtimeManagerTest, 'test_webgui_state_bridge_uses_authoritative_lifecycle', 'WebGUI lifecycle projection regression');
requireText(runtimeManagerTest, 'updating["runtime"]["state"] == "Updating"', 'WebGUI Updating state regression');
requireText(runtimeManagerTest, 'updating["runtime"]["broadcast"]["serving"] is False', 'WebGUI update broadcast withdrawal regression');

// Phase 2: retail and dedicated Steam apps are independent; SteamCMD is dedicated-only.
requireText(runtimeVersions, 'CLIENT_STEAM_APP_ID = "1374490"', 'retail Steam App ID');
requireText(runtimeVersions, 'SERVER_STEAM_APP_ID = "4019830"', 'dedicated Steam App ID');
requireText(runtimeVersions, 'def client_runtime_status', 'client Steam version check');
requireText(runtimeVersions, 'def server_runtime_stack', 'server Steam version check');
requireText(service, 'updates["game"] = {', 'unified client update state');
requireText(service, 'updates["server"] = {', 'unified server update state');
requireText(service, '"action": "Open Steam to update safely"', 'client update action');
requireText(service, 'RUNTIME.update(profile_id, lambda: _legacy_handle("server.install.update"', 'server-only SteamCMD lifecycle');
requireText(legacyService, 'install_dedicated_server(install_dir, steamcmd_dir)', 'managed dedicated SteamCMD install/update');
requireText(serverSystems, '"+app_update", DEDICATED_STEAM_APP_ID, "validate"', 'SteamCMD dedicated update command');
requireText(serverSystems, '"output": (result.stdout or "")[-4000:]', 'SteamCMD success output');
requireText(steamcmdTest, 'CLIENT_STEAM_APP_ID not in command', 'SteamCMD never targets retail client');
requireText(steamcmdTest, 'test_failed_steamcmd_update_surfaces_output', 'failed SteamCMD regression');

// A zero SteamCMD exit code is insufficient: appmanifest + executable must be re-read before restart.
requireText(runtimeManager, 'def _verify_dedicated_install', 'post-SteamCMD verification helper');
requireText(runtimeManager, 'detect_installed_steam_build(install_dir, SERVER_STEAM_APP_ID, steamcmd_dir)', 'post-SteamCMD appmanifest read');
requireText(runtimeManager, 'steam_public_build(SERVER_STEAM_APP_ID, cache_seconds=0.0)', 'fresh dedicated public build verification');
requireText(runtimeManager, 'steam_appmanifest_post_validate', 'verified installed-build source');
requireText(runtimeManager, 'last_steamcmd_output', 'managed SteamCMD output persistence');
requireText(postVerifyTest, 'test_build_mismatch_blocks_restart_contract', 'Steam build mismatch regression');

// Desktop and authenticated WebGUI command the same runtime operations.
for (const method of ['server.runtime.start', 'server.runtime.stop', 'server.runtime.restart', 'server.runtime.update', 'server.runtime.update_restart']) requireText(service, method, `service RPC ${method}`);
requireText(directoryHost, '"start": "start", "stop": "stop", "restart": "restart", "update": "update", "update_restart": "update"', 'WebGUI lifecycle permissions');
requireText(legacyService, 'handle("server.runtime.restart"', 'remote restart routes to runtime manager');
requireText(legacyService, '"server.runtime.update_restart" if action == "update_restart" else "server.runtime.update"', 'remote update routes to runtime manager');
for (const action of ['"start"', '"stop"', '"restart"', '"update"', '"update_restart"']) requireText(remoteLifecycleTest, action, `authenticated WebGUI action ${action}`);

// Central update state includes launcher, retail game, server, UE4SS and RuneSchema.
for (const token of ['updates["game"]', 'updates["server"]', 'updates["core_mod"]', 'updates["runeschema"]', 'updates["launcher"]']) requireText(service, token, `central update state ${token}`);
requireText(managedUpdates, 'def runeschema_status', 'RuneSchema managed update evidence');
requireText(managedUpdates, 'managed-release-asset-name', 'RuneSchema version basis');
requireText(service, 'if method == "application.core_mod.update"', 'managed core update RPC');
requireText(service, 'component not in {"ue4ss", "runeschema"}', 'managed core component allowlist');
requireText(service, '_legacy_handle("server.install.ue4ss_update"', 'UE4SS server managed update');
requireText(service, '_legacy_handle("server.install.runeschema_update"', 'RuneSchema server managed update');
requireText(service, 'RUNTIME.update(profile_id, installer, restart=restart, component=label)', 'core server update lifecycle serialization');
requireText(service, 'without SteamCMD', 'core update notification distinguishes managed runtime path');
requireText(service, 'Close RuneScape: Dragonwilds before updating a managed client core runtime.', 'safe client core update gate');
requireText(managedUpdates, 'def install_client_core', 'client UE4SS/RuneSchema managed update');
requireText(unifiedUpdateTest, 'RuneSchema Core Update', 'RuneSchema notification regression');
requireText(service, '_record_notification(', 'shared notification sink');
requireText(legacyService, '"update_status": dict(((state.get("application") or {}).get("update_status") or {}))', 'WebGUI shared update status payload');
requireText(directoryWeb, 'Object.values(maintenance.update_status||{})', 'WebGUI shared update status rendering');

// CL evidence remains dynamic and visible across desktop/Minimal/WebGUI.
requireText(runtimeVersions, 'def normalize_cl_version', 'CL normalization');
requireText(runtimeVersions, 'def cl_version_status', 'CL comparison');
requireText(runtimeVersions, 'reported_number = int(', 'numeric CL comparison');
requireText(runtimeVersions, 'current_expected_cl', 'dynamic expected CL status');
requireText(app, 'reported_cl', 'desktop CL visibility');
requireText(app, 'CL status', 'Minimal Mode CL visibility');
requireText(directoryWeb, 'function clBadge(w)', 'WebGUI Worlds CL badge');
requireText(directoryWeb, 'Reported CL', 'WebGUI management CL detail');
requireText(directoryWeb, 'Expected CL', 'WebGUI management expected CL');
requireText(directoryWeb, 'CL status', 'WebGUI management CL status');

// Dedicated profile/sync workflow remains real-file based.
requireText(serverSystems, 'def scan_mod_units', 'dedicated mod scanner');
requireText(serverEngine, 'restore_profile_mods', 'physical server profile swap');
requireText(serverEngine, 'scan_mod_units', 'live dedicated rescan');
requireText(syncEngine, '.partial', 'client partial download');
requireText(syncEngine, 'sha256', 'client transfer hash verification');

console.log('Experimental acceptance contract: OK');
