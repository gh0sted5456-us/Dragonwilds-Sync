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

// Runtime/process ownership remains centralized and full application exit must
// ask that backend to shut down before Electron quits.
requireText(service, 'RUNTIME = AuthoritativeRuntimeManager', 'authoritative runtime controller');
requireText(main, "serviceInvoke('application.shutdown'", 'full application shutdown');

// Dedicated scanning/profile activation/publication and host-to-client transfer
// must continue to operate on real files, not UI-only inventory state.
requireText(serverSystems, 'def scan_mod_units', 'dedicated mod scanner');
requireText(serverEngine, 'restore_profile_mods', 'physical server profile swap');
requireText(serverEngine, 'scan_mod_units', 'live dedicated rescan');
requireText(syncEngine, '.partial', 'client partial download');
requireText(syncEngine, 'sha256', 'client transfer hash verification');

console.log('Experimental acceptance contract: OK');
