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
const preload = read('electron/preload.cjs');
const bootstrap = read('electron/bootstrap.cjs');
const main = read('electron/main.cjs');
const service = read('backend/dragonwilds_service.py');
const legacyService = read('backend/dragonwilds_service_legacy.py');
const runtimeManager = read('backend/runtime_manager.py');
const runtimeVersions = read('backend/runtime_versions.py');
const directoryHost = read('backend/directory_host.py');
const directoryWeb = read('backend/directory_web_legacy.py');
const serverSystems = read('backend/server_systems.py');
const serverEngine = read('backend/server_engine.py');
const syncEngine = read('backend/sync_engine.py');
const dragonCore = read('backend/dragon_core.py');
const steamcmdTest = read('backend/test_steamcmd_server_update.py');
const remoteLifecycleTest = read('backend/test_release1_4_web_directory_remote.py');
const runtimeManagerTest = read('backend/test_runtime_manager.py');

// Supplied placards must be a first-class World-card surface rather than a
// fallback texture. The renderer owns four selectable assets and the release
// cascade suppresses an unrelated card banner whenever a placard is present.
requireText(app, "const PLACARD_BACKGROUNDS = ['1','2','3','4'];", 'placard asset contract');
requireText(app, 'world-placard-backdrop', 'placard card renderer');
requireText(css, '.world-card:has(> .world-placard-backdrop) > .world-card-banner', 'placard banner suppression');
requireText(css, 'opacity:.78 !important', 'placard full-card visibility');
requireText(css, '.recommended-mod-card', 'compact Recommended Mods');

// Application-owned dialogs stay inside the renderer. Genuine website content
// keeps the dedicated browser-window bridge.
forbidText(preload, 'openManagedDialog:', 'in-app dialog contract');
forbidText(preload, 'managedDialogContent:', 'in-app dialog contract');
requireText(preload, 'openInAppBrowser:', 'external website browser contract');

// Minimal Mode keeps the authoritative server scheduler/runtime but skips work
// that exists only to maintain the full desktop/client experience.
requireText(bootstrap, "process.argv.includes('--minimal-mode')", 'Minimal Mode detection');
for (const name of ['maybeBenchmark', 'backgroundTick', 'rsdwModuleTick']) {
  requireText(bootstrap, `'${name}'`, `Minimal Mode ${name} suppression`);
}
forbidText(bootstrap, "'schedulerTick'", 'Minimal Mode must not suppress server scheduler');
requireText(main, 'createMinimalWindow(worldId)', 'Minimal Mode selected-world launch');
requireText(app, 'Minimal Mode · Dedicated World', 'Minimal Mode dedicated surface');
requireText(app, 'Update &amp; Restart', 'Minimal Mode update/restart control');

// Runtime/process ownership remains centralized and full application exit must
// ask that backend to shut down before Electron quits.
requireText(service, 'RUNTIME = AuthoritativeRuntimeManager', 'authoritative runtime controller');
requireText(main, "serviceInvoke('application.shutdown'", 'full application shutdown');
for (const phase of ['Starting', 'Stopping', 'Restarting', 'Updating', 'Start Failed', 'Stop Failed', 'Restart Failed', 'Update Failed']) {
  requireText(runtimeManager, `"${phase}"`, `runtime lifecycle phase ${phase}`);
}
requireText(runtimeManager, 'A server lifecycle operation is already active', 'conflicting command lock');
requireText(runtimeManager, 'exited unexpectedly', 'unexpected process exit reconciliation');
requireText(runtimeManager, 'broadcast_verified', 'broadcast lifecycle verification');
requireText(runtimeManager, 'component: str = "Dedicated Server"', 'generic managed update lifecycle');
requireText(runtimeManager, 'web_management_stopped', 'verified WebGUI shutdown');
requireText(runtimeManager, 'The Sync advertisement remained active during launcher shutdown.', 'verified broadcast shutdown');

// Start/Restart/Update+Restart must prepare while offline, verify the real game
// process, and only then expose Sync. The old ServerEngine.start_world helper is
// deliberately not the authoritative manager path because it publishes first.
requireText(runtimeManager, 'def _start_verified', 'process-before-broadcast helper');
requireOrder(runtimeManager, [
  'prepared = self.engine.scan_mods(profile_id)',
  'started = self.engine.start_dedicated(profile_id)',
  'after_process = self._actual()',
  'published = self.engine.publish(profile_id)',
], 'process-before-broadcast ordering');
forbidText(runtimeManager, 'self.engine.start_world(', 'authoritative lifecycle must not use publish-first start_world');
requireText(runtimeManager, 'self.engine.stop_world()', 'failed post-launch cleanup');
requireText(runtimeManager, 'Sync became available before dedicated-process verification completed.', 'early advertisement guard');

// Authenticated WebGUI state is projected from the same manager, including
// transitional/busy/error/broadcast state. It must not fall back to a separate
// remembered lifecycle model while actions are routed through the manager.
requireText(runtimeManager, 'def _install_directory_state_bridge', 'WebGUI authoritative state bridge');
requireText(runtimeManager, 'host.set_remote_admin_callbacks = bridged_set_remote_admin_callbacks', 'WebGUI callback bridge installation');
requireText(runtimeManager, '"busy": bool(lifecycle.get("busy"))', 'WebGUI busy lifecycle state');
requireText(runtimeManager, '"last_error": lifecycle.get("last_error") or ""', 'WebGUI lifecycle error state');
requireText(runtimeManagerTest, 'test_webgui_state_bridge_uses_authoritative_lifecycle', 'WebGUI lifecycle projection regression');
requireText(runtimeManagerTest, 'updating["runtime"]["state"] == "Updating"', 'WebGUI Updating state regression');
requireText(runtimeManagerTest, 'updating["runtime"]["broadcast"]["serving"] is False', 'WebGUI update broadcast withdrawal regression');

// Steam build/version checks are independent for the retail client and the
// dedicated server. SteamCMD is a dedicated-server updater only. The client
// row may tell the user to update through Steam, but it must never route into
// server.install.update or install_dedicated_server.
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

// Desktop and authenticated WebGUI must command the same backend runtime
// operations rather than maintaining parallel process state.
for (const method of ['server.runtime.start', 'server.runtime.stop', 'server.runtime.restart', 'server.runtime.update', 'server.runtime.update_restart']) {
  requireText(service, method, `service RPC ${method}`);
}
requireText(directoryHost, '"start": "start", "stop": "stop", "restart": "restart", "update": "update", "update_restart": "update"', 'WebGUI lifecycle permissions');
requireText(legacyService, 'handle("server.runtime.restart"', 'remote restart routes to runtime manager');
requireText(legacyService, '"server.runtime.update_restart" if action == "update_restart" else "server.runtime.update"', 'remote update routes to runtime manager');
for (const action of ['"start"', '"stop"', '"restart"', '"update"', '"update_restart"']) {
  requireText(remoteLifecycleTest, action, `authenticated WebGUI action ${action}`);
}

// Central update state must include retail game, dedicated server, launcher,
// UE4SS, and launcher-managed DragonCore evidence and feed one notification
// system. DragonCore server updates use the generic runtime queue, not SteamCMD.
for (const token of ['updates["game"]', 'updates["server"]', 'updates["core_mod"]', 'updates["launcher"]']) {
  requireText(service, token, `central update state ${token}`);
}
requireText(service, 'dragoncore_client', 'central DragonCore client update state');
requireText(service, 'dragoncore_server', 'central DragonCore server update state');
requireText(service, 'if method == "application.core_mod.update"', 'DragonCore update RPC');
requireText(service, 'component="DragonCore"', 'DragonCore uses authoritative update queue');
requireText(service, 'Close RuneScape: Dragonwilds before updating', 'safe client DragonCore update gate');
requireText(dragonCore, 'def managed_status', 'DragonCore managed version status');
requireText(dragonCore, 'sha256', 'DragonCore content fingerprint');
requireText(service, '_record_notification(', 'shared notification sink');
requireText(legacyService, '"update_status": dict(((state.get("application") or {}).get("update_status") or {}))', 'WebGUI shared update status payload');
requireText(directoryWeb, 'Object.values(maintenance.update_status||{})', 'WebGUI shared update status rendering');

// CL evidence must be normalized numerically and exposed from the same runtime
// version stack rather than hard-coded in the UI. Desktop and WebGUI both show
// the reported value plus semantic Current/Outdated/Unknown state.
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

// Dedicated scanning/profile activation/publication and host-to-client transfer
// must continue to operate on real files, not UI-only inventory state.
requireText(serverSystems, 'def scan_mod_units', 'dedicated mod scanner');
requireText(serverEngine, 'restore_profile_mods', 'physical server profile swap');
requireText(serverEngine, 'scan_mod_units', 'live dedicated rescan');
requireText(syncEngine, '.partial', 'client partial download');
requireText(syncEngine, 'sha256', 'client transfer hash verification');

console.log('Experimental acceptance contract: OK');
