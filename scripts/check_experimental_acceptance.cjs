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
const serverSystems = read('backend/server_systems.py');
const serverEngine = read('backend/server_engine.py');
const syncEngine = read('backend/sync_engine.py');

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

// Runtime/process ownership remains centralized and full application exit must
// ask that backend to shut down before Electron quits.
requireText(service, 'RUNTIME = AuthoritativeRuntimeManager', 'authoritative runtime controller');
requireText(main, "serviceInvoke('application.shutdown'", 'full application shutdown');
for (const phase of ['Starting', 'Stopping', 'Restarting', 'Updating', 'Start Failed', 'Stop Failed', 'Update Failed']) {
  requireText(runtimeManager, `"${phase}"`, `runtime lifecycle phase ${phase}`);
}
requireText(runtimeManager, 'A server lifecycle operation is already active', 'conflicting command lock');
requireText(runtimeManager, 'exited unexpectedly', 'unexpected process exit reconciliation');
requireText(runtimeManager, 'broadcast_verified', 'broadcast lifecycle verification');

// Steam build/version checks are independent for the retail client and the
// dedicated server. SteamCMD is a dedicated-server updater only. The client
// row may tell the user to update through Steam, but it must never route into
// server.install.update or install_dedicated_server.
requireText(runtimeVersions, 'CLIENT_STEAM_APP_ID = "1374490"', 'retail Steam App ID');
requireText(runtimeVersions, 'SERVER_STEAM_APP_ID = "4019830"', 'dedicated Steam App ID');
requireText(runtimeVersions, 'def client_runtime_status', 'client Steam version check');
requireText(runtimeVersions, 'def server_runtime_stack', 'server Steam version check');
requireText(service, '"game"] = {', 'unified client update state');
requireText(service, '"server"] = {', 'unified server update state');
requireText(service, '"action": "Open Steam to update safely"', 'client update action');
requireText(service, 'RUNTIME.update(profile_id, lambda: _legacy_handle("server.install.update"', 'server-only SteamCMD lifecycle');
requireText(legacyService, 'install_dedicated_server(install_dir, steamcmd_dir)', 'managed dedicated SteamCMD install/update');

// Desktop and authenticated WebGUI must command the same backend runtime
// operations rather than maintaining parallel process state.
for (const method of ['server.runtime.start', 'server.runtime.stop', 'server.runtime.restart', 'server.runtime.update', 'server.runtime.update_restart']) {
  requireText(service, method, `service RPC ${method}`);
}
requireText(directoryHost, '"start": "start", "stop": "stop", "restart": "restart", "update": "update", "update_restart": "update"', 'WebGUI lifecycle permissions');
requireText(legacyService, 'handle("server.runtime.restart"', 'remote restart routes to runtime manager');
requireText(legacyService, '"server.runtime.update_restart" if action == "update_restart" else "server.runtime.update"', 'remote update routes to runtime manager');

// Central update state must include retail game, dedicated server, launcher and
// managed/core runtime information and feed the common notification system.
for (const token of ['updates["game"]', 'updates["server"]', 'updates["core_mod"]', 'updates["launcher"]']) {
  requireText(service, token, `central update state ${token}`);
}
requireText(service, '_record_notification(', 'shared notification sink');

// CL evidence must be normalized numerically and exposed from the same runtime
// version stack rather than hard-coded in the UI.
requireText(runtimeVersions, 'def normalize_cl_version', 'CL normalization');
requireText(runtimeVersions, 'def cl_version_status', 'CL comparison');
requireText(runtimeVersions, 'reported_number = int(', 'numeric CL comparison');
requireText(runtimeVersions, 'current_expected_cl', 'dynamic expected CL status');
requireText(app, 'reported_cl', 'desktop CL visibility');

// Dedicated scanning/profile activation/publication and host-to-client transfer
// must continue to operate on real files, not UI-only inventory state.
requireText(serverSystems, 'def scan_mod_units', 'dedicated mod scanner');
requireText(serverEngine, 'restore_profile_mods', 'physical server profile swap');
requireText(serverEngine, 'scan_mod_units', 'live dedicated rescan');
requireText(syncEngine, '.partial', 'client partial download');
requireText(syncEngine, 'sha256', 'client transfer hash verification');

console.log('Experimental acceptance contract: OK');
