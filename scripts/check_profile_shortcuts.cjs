'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { buildHeadlessShortcutArgs, buildQuickShortcutArgs, modeForWorldKind, normalizeProfileId } = require('../electron/quick_shortcut.cjs');
const { resolveGuiShortcutTarget, resolveHeadlessShortcutTarget } = require('../electron/shortcut_targets.cjs');

assert.strictEqual(buildQuickShortcutArgs({ profileId: 'private-a', mode: 'player', autoStart: true }), '--quick --profile=private-a --mode=player --auto-start');
assert.strictEqual(buildQuickShortcutArgs({ profileId: 'server-a', mode: 'server', autoStart: true }), '--quick --profile=server-a --mode=server --auto-start');
assert.strictEqual(buildHeadlessShortcutArgs({ profileId: 'server-a', mode: 'server' }), '--headless run --profile=server-a --mode=server');
assert.strictEqual(modeForWorldKind('private'), 'player');
assert.strictEqual(modeForWorldKind('server'), 'server');
assert.throws(() => normalizeProfileId('world-a --mode=server'), /unsupported characters/);

const shortcutFixture = fs.mkdtempSync(path.join(os.tmpdir(), 'dws-shortcuts-'));
try {
  const gui = path.join(shortcutFixture, 'Dragonwilds Sync and Launcher-Portable-3.0.5.exe');
  const headless = path.join(shortcutFixture, 'Dragonwilds Sync Headless-3.0.5.exe');
  fs.writeFileSync(gui, 'gui'); fs.writeFileSync(headless, 'headless');
  assert.strictEqual(resolveGuiShortcutTarget(gui), path.resolve(gui));
  assert.strictEqual(resolveHeadlessShortcutTarget({ executablePath: gui, version: '3.0.5' }), path.resolve(headless));
  assert.throws(() => resolveHeadlessShortcutTarget({ executablePath: path.join(shortcutFixture, 'missing', 'app.exe') }), /Headless EXE|ENOENT/);
} finally { fs.rmSync(shortcutFixture, { recursive: true, force: true }); }

const root = path.resolve(__dirname, '..');
const renderer = fs.readFileSync(path.join(root, 'renderer', 'release-v3-phase2.js'), 'utf8');
const retainedMain = fs.readFileSync(path.join(root, 'electron', 'main-v2.cjs'), 'utf8');
assert(renderer.includes("fallbackKind === 'private' ? 'coop' : 'player'"));
assert(renderer.includes("api.invoke('quick.status'"));
assert(retainedMain.includes("createQuickWindow(q.worldId,q.worldKind,q.autoStart)"), 'legacy --quick-launch shortcuts must remain supported');
assert(retainedMain.includes('promoteToFullApplication(event.sender)'), 'Open Full must promote the existing Quick process');
assert(renderer.includes("quickState?.profile_kind==='linked'"), 'Connected Quick must explain its verified Sync pipeline');
assert(renderer.includes("without contacting a remote Sync host"), 'Local Quick must remain independent from remote Sync');
assert(renderer.includes('Headless Start') && renderer.includes("runtime:behavior==='headless'?'headless':'gui'"), 'Server shortcut picker must route headless shortcuts to the standalone executable');
console.log('profile desktop shortcut contracts passed');
