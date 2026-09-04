'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const phase5 = read('renderer/release-phase5.js');
const bridge = read('renderer/release-phase5-frame-bridge.js');
const frameActions = read('renderer/release-phase5-frame-actions.js');
const css = read('renderer/release-phase5.css');
const embeddedCss = read('renderer/release-phase5-embedded.css');
const html = read('renderer/index.html');

const requireText = (source, token, label = token) => {
  if (!source.includes(token)) throw new Error(`Phase 5 contract missing: ${label}`);
};
const rejectText = (source, token, label = token) => {
  if (source.includes(token)) throw new Error(`Phase 5 contract forbids: ${label}`);
};

requireText(html, 'release-phase5.css', 'Phase 5 stylesheet load');
requireText(html, 'release-phase5-embedded.css', 'embedded workspace guard stylesheet');
requireText(html, 'release-phase5-frame-bridge.js', 'same-renderer embedded bridge bootstrap');
requireText(html, 'release-phase5.js', 'Phase 5 renderer load');
requireText(html, 'release-phase5-frame-actions.js', 'embedded Explorer forwarding load');
if (html.indexOf('release-phase5-frame-bridge.js') > html.indexOf('app.js')) {
  throw new Error('Phase 5 embedded bridge must initialize before app.js.');
}
if (html.indexOf('release-phase5-frame-actions.js') < html.indexOf('release-phase5.js')) {
  throw new Error('Phase 5 embedded action forwarding must load after the parent window API layer.');
}
requireText(bridge, "query.get('phase5Internal') !== '1'", 'embedded-only bridge guard');
requireText(bridge, 'window.parent?.dragonwilds', 'reuse parent preload/backend bridge');
rejectText(bridge, 'openDetachedWindow', 'BrowserWindow creation from embedded bridge');
requireText(frameActions, "query.get('phase5Internal') !== '1'", 'embedded action guard');
requireText(frameActions, 'window.parent?.__DWSYNC_INTERNAL_WINDOWS__?.openExplorer', 'forward embedded actions to parent Explorer');
if (frameActions.includes("target.id === 'phase2-view-mods'")) fail('embedded View Mods must use its native profile Mods tab instead of being hijacked by Explorer');
requireText(frameActions, "target.dataset.action === 'open'", 'embedded Mod Manager Explore forwarding');
rejectText(frameActions, 'openDetachedWindow', 'BrowserWindow creation from embedded actions');

requireText(phase5, 'DRAGONWILDS SYNC EXPLORER', 'Explorer title');
requireText(phase5, 'assets/application-icon.webp', 'application icon in internal windows/Explorer');
for (const category of ['UE4SS', 'RuneSchema', 'Pak']) requireText(phase5, category, `logical ${category} category`);
for (const hidden of ['dragonconnect', 'persistentdirectconnectip', 'rsdwtools', 'rsdwdevkit', 'mods.txt']) {
  requireText(phase5, hidden, `hidden infrastructure guard ${hidden}`);
}
requireText(phase5, 'user_manageable === false', 'central user-manageable presentation guard');
requireText(phase5, "text(unit.visibility) !== 'user-mod'", 'user-mod visibility guard');

for (const id of ['detach-profile', 'detach-worlds', 'detach-settings', 'detach-private-world', 'detach-server-world']) {
  requireText(phase5, id, `internal Open in Window interception for ${id}`);
  requireText(embeddedCss, `#${id}`, `nested ${id} suppression inside internal route workspace`);
}
requireText(embeddedCss, '#modal-root', 'embedded editor/modal layer remains usable');
requireText(embeddedCss, '#internal-taskbar', 'embedded editor minimize/restore path remains usable');
if (phase5.includes("target.id === 'phase2-view-mods'")) fail('View Mods must use its native profile Mods tab instead of being hijacked by Explorer');
requireText(phase5, "target.dataset.action === 'open'", 'Mod Manager Open/Edit → same Explorer interception');
requireText(phase5, 'window.__DWSYNC_INTERNAL_WINDOWS__', 'internal window registry/API');
requireText(phase5, 'desktop-window phase5-window', 'existing MDI desktop-window contract');
requireText(phase5, 'phase5Internal=1', 'internal embedded route mode');
requireText(phase5, '<iframe class="phase5-route-frame"', 'app-owned route frame');
requireText(phase5, "win.classList.add('minimized')", 'minimize');
requireText(phase5, "win.classList.add('maximized')", 'maximize');
requireText(phase5, 'closeWindow(win)', 'close');
requireText(phase5, 'focusWindow(win)', 'focus / z-order');
requireText(phase5, 'internal-task-button', 'in-app taskbar');
requireText(phase5, 'localStorage.setItem(geometryKey', 'window geometry retention');
requireText(phase5, "header.addEventListener('pointerdown'", 'drag geometry');
requireText(phase5, 'ResizeObserver', 'resize geometry retention');
rejectText(phase5, 'location.reload', 'renderer/app reload during window geometry changes');
rejectText(phase5, 'openDetachedWindow', 'new application-owned BrowserWindow creation');
rejectText(phase5, 'openManagedDialog', 'new native managed-dialog BrowserWindow creation');

for (const rpc of [
  'singleplayer.inventory', 'server.world.inventory',
  'singleplayer.mod.files', 'server.world.config.list',
  'singleplayer.mod.file.open', 'server.world.config.open',
  'singleplayer.mod.file.save', 'server.world.config.save',
]) requireText(phase5, rpc, `Explorer lazy existing-provider use: ${rpc}`);
requireText(phase5, 'rescan: refresh', 'explicit Explorer Refresh bypasses cached inventory');
requireText(phase5, 'Files load only when you open a mod.', 'lazy mod-file discovery');
requireText(phase5, 'Binary and oversized payloads', 'binary/view-only policy');
requireText(phase5, 'JSON.parse(content)', 'JSON save validation');

requireText(css, '.phase5-window', 'internal window styles');
requireText(css, '.phase5-route-frame', 'internal route frame styles');
requireText(css, 'body.phase5-embedded', 'embedded workspace shell styles');
requireText(css, '.phase5-explorer', 'Explorer layout styles');
requireText(css, '.phase5-explorer-sidebar', 'Explorer logical root/sidebar');
requireText(css, '.phase5-editor-textarea', 'Explorer text editor surface');

// Phase 5 owns only app-managed window/Explorer presentation. External browser
// links intentionally remain with the existing data-open-external implementation.
if (/data-open-external/.test(phase5) || /data-open-external/.test(frameActions)) {
  throw new Error('Phase 5 must not intercept genuine external browser links.');
}

console.log('Phase 5 internal windows / Dragonwilds Sync Explorer contract: OK');
