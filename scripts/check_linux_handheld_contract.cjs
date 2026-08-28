const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const app = read('renderer/app-v2.js');
const css = read('renderer/release-final-cleanup.css');
const baseCss = read('renderer/styles.css');
const main = read('electron/main-v2.cjs');
const preload = read('electron/preload-v2.cjs');
const runtime = read('backend/runtime_platforms.py');
const systems = read('backend/server_systems.py');
const archivePolicy = read('backend/runtime_archive_policy.py');

const requireText = (source, text, message) => {
  if (!source.includes(text)) throw new Error(message);
};

requireText(app, "id=\"server-native-ue4ss-source\"", 'Native Linux UE4SS source control is missing.');
requireText(app, "id=\"server-native-runeschema-source\"", 'Native Linux RuneSchema source control is missing.');
requireText(app, 'linux_server_mode:', 'Linux server mode is not persisted.');
requireText(app, "id=\"save-window-preferences\"", 'Window preference controls are missing.');
requireText(app, "id=\"window-custom-width\"", 'Custom persistent window width is missing.');
requireText(app, "id=\"window-use-current-size\"", 'Current window size capture is missing.');
const renderSettingsStart = app.indexOf('function renderSettings()');
const windowPreferencesDeclaration = app.indexOf('const windowPrefs = a.window_preferences || {};', renderSettingsStart);
const applicationSettingsStart = app.indexOf("} else if (tab === 'application') {");
const windowSettingsStart = app.indexOf("Window &amp; Handheld");
const computerProfileStart = app.indexOf("computer-profile-section");
if (!(renderSettingsStart < windowPreferencesDeclaration && windowPreferencesDeclaration < applicationSettingsStart)) {
  throw new Error('Window preferences are not declared in the shared Settings render scope.');
}
if (!(applicationSettingsStart < windowSettingsStart && windowSettingsStart < computerProfileStart)) {
  throw new Error('Window & Handheld controls are not on the primary Application settings page.');
}
requireText(app, 'document.body.dataset.handheldMode', 'Handheld state is not applied to the renderer shell.');
requireText(css, 'body[data-handheld-mode="1"] .sidebar .appy-nav', 'Handheld title-card styling is missing.');
requireText(preload, 'windowPreferences:', 'The window preference preload bridge is missing.');
requireText(main, "dragonwilds:window-preferences", 'The Electron window preference handler is missing.');
requireText(main, "saveRememberedWindowBounds(win)", 'Applied remember-mode window bounds are not persisted immediately.');
requireText(runtime, 'def dedicated_runtime_contract', 'The dedicated runtime scope contract is missing.');
requireText(runtime, '"distribution": "never"', 'Native server material is not marked non-distributable.');
requireText(systems, '"runtime_scope": "client_required"', 'Published Win64 baseline entries lack their client scope.');
requireText(systems, 'dedicated_runtime_contract', 'Sync manifests do not expose the host/client runtime boundary.');
requireText(archivePolicy, 'inspect_runtime_archive', 'Runtime ZIP entries are not inventoried.');
requireText(archivePolicy, 'validate_client_targets', 'Runtime client selectors are not policy validated.');
requireText(app, 'data-runtime-client-files', 'Runtime build rows do not expose client file selectors.');
requireText(app, 'function gameModeBadgesMarkup', 'Shared world mode badge renderer is missing.');
requireText(app, "hardmode: 'hard'", 'Hard mode metadata aliases are not normalized.');
requireText(app, 'gameModeBadgesMarkup(world,server)', 'World mode badges are not shared by placards and horizontal rows.');
requireText(baseCss, '.world-mode-pill.mode-normal', 'Normal mode badge styling is missing.');
requireText(baseCss, '.world-mode-pill.mode-hard', 'Hard mode badge styling is missing.');
requireText(baseCss, '.world-mode-pill.mode-creative', 'Creative mode badge styling is missing.');
requireText(baseCss, '.world-mode-pill.mode-pvp', 'PVP badge styling is missing.');

console.log('[OK] Linux server/client runtime separation and handheld window contracts');
