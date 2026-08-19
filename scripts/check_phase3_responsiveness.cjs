const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const requireText = (source, text, label) => {
  if (!source.includes(text)) throw new Error(`Phase 3 contract failed: ${label}`);
};

const preload = read('electron/preload.cjs');
const phase3 = read('renderer/release-phase3.js');
const backend = read('backend/phase3_responsiveness.py');
const index = read('renderer/index.html');

requireText(preload, 'const invokeCache = new Map()', 'preload must keep an in-memory read cache');
requireText(preload, 'const invokeInFlight = new Map()', 'preload must deduplicate matching in-flight reads');
requireText(preload, 'let cacheGeneration = 0', 'mutations must invalidate older in-flight cache generations');
requireText(preload, 'READ_TIMEOUT_MS = 15000', 'foreground/local backend reads must have a bounded timeout');
requireText(preload, "'characters.list': { ttl:", 'Character Tools must use a hot read policy');
requireText(preload, "'singleplayer.inventory'", 'local mod inventory must use coordinated cached reads');
requireText(preload, "'server.world.inventory'", 'dedicated mod inventory must use coordinated cached reads');
requireText(preload, "'singleplayer.mod.files'", 'Mod Explorer file lists must use coordinated cached reads');
requireText(preload, "'singleplayer.profile.get'", 'World profile detail reads must use coordinated cached reads');
requireText(preload, "'world.save.editor.read'", 'Save Editor reads must use coordinated cached reads');
requireText(preload, "'server.world.save.status'", 'save status must use coordinated cached reads');
requireText(preload, "p.force === true || p.refresh === true || p.rescan === true || p.verify === true", 'explicit verify/refresh/rescan must bypass stale cache');
requireText(preload, 'invalidateAfterMutation', 'writes must invalidate related read caches');
requireText(preload, 'generation === cacheGeneration', 'pre-mutation reads must not repopulate cache afterward');
requireText(preload, 'prewarmRequests', 'renderer must be able to warm known local state in the background');
requireText(preload, 'onRequestActivity', 'renderer must receive real request activity instead of fake spinner timers');
requireText(preload, 'requestStats', 'backend request timings must be inspectable');

requireText(phase3, 'criticalRequests(state)', 'Phase 3 must define a lightweight startup warmup');
requireText(phase3, "{ method: 'characters.list', params: {} }", 'Character Tools must warm on explicit user intent');
requireText(phase3, "{ method: 'singleplayer.profile.get'", 'World profile details must warm on relevant intent');
requireText(phase3, "{ method: 'singleplayer.inventory'", 'local mods must warm from cache on Mods intent');
requireText(phase3, "{ method: 'server.world.inventory'", 'server mods must warm from cache on Mods intent');
requireText(phase3, "{ method: 'server.world.save.status'", 'World save state must warm on relevant World intent');
requireText(phase3, "{ method: 'world.save.editor.read'", 'Save Editor must warm on user intent');
requireText(phase3, "{ method: 'server.world.config.list'", 'World configuration must warm on configuration intent');
requireText(phase3, "{ method: 'server.backups.list'", 'Save Manager/maintenance backup data must warm on maintenance intent');
requireText(phase3, 'requested_to_first_paint', 'major surfaces must record requested-to-first-paint timing');
requireText(phase3, 'phase3-load-pill', 'slow foreground work must use a localized loading indicator');
requireText(phase3, 'window.__DWSYNC_PERF__', 'performance evidence must be available for diagnostics');

const criticalStart = phase3.indexOf('function criticalRequests');
const criticalEnd = phase3.indexOf('async function prewarmCritical', criticalStart);
const critical = phase3.slice(criticalStart, criticalEnd);
for (const forbidden of ['application.rsdw.status', 'application.map.status', 'characters.list', 'singleplayer.inventory', 'server.world.inventory', 'server.backups.list']) {
  if (critical.includes(forbidden)) throw new Error(`Phase 3 contract failed: startup warmup must not include ${forbidden}`);
}

requireText(backend, 'DragonwildsSync.CharacterIndex.v1', 'backend must persist a lightweight Character Index');
requireText(backend, '_cached_local_world_projection', 'unchanged local World projection must reuse known profile state');
requireText(backend, '_local_world_signature', 'World projection reuse must be invalidated by cheap file metadata');
requireText(backend, '_profile_without_volatile', 'unchanged profile persistence must avoid timestamp-only rewrites');
requireText(backend, 'legacy-profile-v1', 'legacy local profile migration must be marked once-only');
if (backend.includes('_characters.rsdw_cache.status()')) {
  throw new Error('Phase 3 contract failed: Character hot path must not recursively validate the full RSDW cache.');
}

if (phase3.includes("world.directory.refresh")) {
  throw new Error('Phase 3 contract failed: public/network World discovery must not be part of local warmup.');
}
if (phase3.includes('setInterval(')) {
  throw new Error('Phase 3 contract failed: responsiveness warmup must not add a polling loop.');
}

requireText(index, 'release-phase3.css', 'Phase 3 localized loading CSS must be loaded');
requireText(index, 'release-phase3.js', 'Phase 3 responsiveness layer must be loaded');

console.log('Phase 3 responsiveness / backend loading contract: OK');
