const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const requireText = (source, text, label) => {
  if (!source.includes(text)) throw new Error(`Phase 3 contract failed: ${label}`);
};

const preload = read('electron/preload.cjs');
const phase3 = read('renderer/release-phase3.js');
const index = read('renderer/index.html');

requireText(preload, 'const invokeCache = new Map()', 'preload must keep an in-memory read cache');
requireText(preload, 'const invokeInFlight = new Map()', 'preload must deduplicate matching in-flight reads');
requireText(preload, "'characters.list': { ttl: 5000", 'Character Tools must use a hot read policy');
requireText(preload, "'singleplayer.inventory'", 'local mod inventory must use coordinated cached reads');
requireText(preload, "'server.world.inventory'", 'dedicated mod inventory must use coordinated cached reads');
requireText(preload, "'server.world.save.status'", 'save status must use coordinated cached reads');
requireText(preload, "p.force === true || p.refresh === true || p.rescan === true || p.verify === true", 'explicit verify/refresh/rescan must bypass stale cache');
requireText(preload, 'invalidateAfterMutation', 'writes must invalidate related read caches');
requireText(preload, 'prewarmRequests', 'renderer must be able to warm known local state in the background');
requireText(preload, 'onRequestActivity', 'renderer must receive real request activity instead of fake spinner timers');
requireText(preload, 'requestStats', 'backend request timings must be inspectable');

requireText(phase3, 'criticalRequests(state)', 'Phase 3 must define critical local-state warmup');
requireText(phase3, "{ method: 'characters.list', params: {} }", 'Character Tools must warm after bootstrap');
requireText(phase3, "{ method: 'singleplayer.inventory'", 'local mods must warm after bootstrap');
requireText(phase3, "{ method: 'server.world.inventory'", 'server mods must warm after bootstrap');
requireText(phase3, "{ method: 'server.world.save.status'", 'World save state must warm after bootstrap');
requireText(phase3, "{ method: 'server.world.config.list'", 'World configuration must warm after bootstrap');
requireText(phase3, "{ method: 'server.backups.list'", 'Save Manager/maintenance backup data must warm after bootstrap');
requireText(phase3, 'requested_to_first_paint', 'major surfaces must record requested-to-first-paint timing');
requireText(phase3, 'phase3-load-pill', 'slow foreground work must use a localized loading indicator');
requireText(phase3, 'window.__DWSYNC_PERF__', 'performance evidence must be available for diagnostics');

if (phase3.includes("world.directory.refresh")) {
  throw new Error('Phase 3 contract failed: public/network World discovery must not be part of local warmup.');
}
if (phase3.includes('setInterval(')) {
  throw new Error('Phase 3 contract failed: responsiveness warmup must not add a polling loop.');
}

requireText(index, 'release-phase3.css', 'Phase 3 localized loading CSS must be loaded');
requireText(index, 'release-phase3.js', 'Phase 3 responsiveness layer must be loaded');

console.log('Phase 3 responsiveness / backend loading contract: OK');
