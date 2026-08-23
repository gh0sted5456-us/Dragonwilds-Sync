'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { buildQuickShortcutArgs, modeForWorldKind, normalizeProfileId } = require('../electron/quick_shortcut.cjs');

assert.strictEqual(buildQuickShortcutArgs({ profileId: 'private-a', mode: 'player', autoStart: true }), '--quick --profile=private-a --mode=player --auto-start');
assert.strictEqual(buildQuickShortcutArgs({ profileId: 'server-a', mode: 'server', autoStart: true }), '--quick --profile=server-a --mode=server --auto-start');
assert.strictEqual(modeForWorldKind('private'), 'player');
assert.strictEqual(modeForWorldKind('server'), 'server');
assert.throws(() => normalizeProfileId('world-a --mode=server'), /unsupported characters/);

const root = path.resolve(__dirname, '..');
const renderer = fs.readFileSync(path.join(root, 'renderer', 'release-v3-phase2.js'), 'utf8');
const retainedMain = fs.readFileSync(path.join(root, 'electron', 'main-v2.cjs'), 'utf8');
assert(renderer.includes("fallbackKind === 'private' ? 'coop' : 'player'"));
assert(renderer.includes("api.invoke('quick.status'"));
assert(retainedMain.includes("createQuickWindow(q.worldId,q.worldKind,q.autoStart)"), 'legacy --quick-launch shortcuts must remain supported');
console.log('profile desktop shortcut contracts passed');
