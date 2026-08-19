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
const shell = read('backend/shell_persistence_stabilization.py');
const monaco = read('renderer/release-monaco-prewarm.js');
const app = read('renderer/app.js');
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
requireText(phase3, "{ method: 'characters.list', params: {} }", 'Characters must warm immediately after shell bootstrap');
requireText(phase3, "{ method: 'singleplayer.profile.get'", 'active local World profile must warm from persisted state');
requireText(phase3, "{ method: 'singleplayer.inventory'", 'active local mod inventory must warm from cache');
requireText(phase3, "{ method: 'server.world.inventory'", 'active server mod inventory must warm from cache');
requireText(phase3, "{ method: 'server.world.save.status'", 'active server save state must warm with the shell');
requireText(phase3, 'setTimeout(() => prewarmCritical(true), 0)', 'local workspace warmup must start immediately after initial state paint');
requireText(phase3, 'window.__DWSYNC_SHELL_READY__', 'shell readiness must be observable for diagnostics');
requireText(phase3, "{ method: 'world.save.editor.read'", 'Save Editor must still warm only on user intent');
requireText(phase3, "{ method: 'server.world.config.list'", 'World configuration must warm on configuration intent');
requireText(phase3, "{ method: 'server.backups.list'", 'Save Manager/maintenance backup data must remain intent-driven');
requireText(phase3, 'requested_to_first_paint', 'major surfaces must record requested-to-first-paint timing');
requireText(phase3, 'phase3-load-pill', 'slow foreground work must use a localized loading indicator');
requireText(phase3, 'window.__DWSYNC_PERF__', 'performance evidence must be available for diagnostics');

const criticalStart = phase3.indexOf('function criticalRequests');
const criticalEnd = phase3.indexOf('async function prewarmCritical', criticalStart);
const critical = phase3.slice(criticalStart, criticalEnd);
for (const required of ['characters.list', 'singleplayer.inventory', 'server.world.inventory']) {
  if (!critical.includes(required)) throw new Error(`Phase 3 contract failed: shell warmup must include persisted/local ${required}`);
}
for (const forbidden of [
  'world.browser.refresh', 'world.directory.refresh', 'application.recommendations.refresh',
  'application.rsdw.refresh', 'application.map.refresh', 'server.backups.list', 'rescan: true',
]) {
  if (critical.includes(forbidden)) throw new Error(`Phase 3 contract failed: shell warmup must not include heavyweight ${forbidden}`);
}

requireText(backend, 'DragonwildsSync.CharacterIndex.v1', 'backend must persist a lightweight Character Index');
requireText(backend, '_cached_local_world_projection', 'unchanged local World projection must reuse known profile state');
requireText(backend, '_local_world_signature', 'World projection reuse must be invalidated by cheap file metadata');
requireText(backend, '_profile_without_volatile', 'unchanged profile persistence must avoid timestamp-only rewrites');
requireText(backend, 'legacy-profile-v1', 'legacy local profile migration must be marked once-only');
if (backend.includes('_characters.rsdw_cache.status()')) {
  throw new Error('Phase 3 contract failed: Character hot path must not recursively validate the full RSDW cache.');
}

requireText(shell, 'DragonwildsSync.ModFileIndex.v1', 'local Mod Explorer must have a persistent file-tree index');
requireText(shell, 'settings-manifest', 'settings.json must recover cached mod inventory without a scan');
requireText(shell, 'mods["inventory"]', 'settings.json must persist the known user-mod inventory');
requireText(shell, 'is_user_manageable_mod', 'persisted mod inventory must obey the authoritative hidden-infrastructure taxonomy');
requireText(shell, '_invalidate_mod_indexes', 'narrow local file mutations must invalidate only affected Mod Explorer indexes');
requireText(shell, '_bind_legacy_aliases', 'packaged/source late imports must share the indexed local Mod Explorer provider');
requireText(shell, '_server_manifest_rows', 'Dedicated Mod Explorer must project its durable managed config manifest first');
requireText(shell, '_refresh_server_manifest_background', 'stale dedicated config evidence must refresh in deduplicated background work');
requireText(shell, '_bind_server_config_alias', 'packaged/source late imports must share the dedicated manifest-first provider');

if (phase3.includes('setInterval(')) {
  throw new Error('Phase 3 contract failed: responsiveness warmup must not add a polling loop.');
}

requireText(monaco, "script.src = 'vendor/monaco/vs/loader.js'", 'bundled Monaco loader must be prewarmed');
requireText(monaco, "amdRequire(['vs/editor/editor.main']", 'Monaco editor core must preload before first editor intent');
requireText(monaco, 'window.__DWSYNC_MONACO_STATUS__', 'Monaco readiness/failure must be observable');
requireText(monaco, 'warm().catch(() => {})', 'Monaco must begin warming during the backend bootstrap window');
requireText(app, 'monaco.editor.create', 'the application must still mount the real Monaco editor');
requireText(app, "state.data = await api.invoke('bootstrap')", 'app.js must retain an asynchronous backend bootstrap window');
requireText(index, 'release-monaco-prewarm.js', 'Monaco prewarm layer must be loaded');
requireText(index, 'release-phase3.css', 'Phase 3 localized loading CSS must be loaded');
requireText(index, 'release-phase3.js', 'Phase 3 responsiveness layer must be loaded');
const appIndex = index.indexOf('app.js');
const monacoIndex = index.indexOf('release-monaco-prewarm.js');
const performanceIndex = index.indexOf('release-performance.js');
if (!(appIndex >= 0 && monacoIndex > appIndex && performanceIndex > monacoIndex)) {
  throw new Error('Phase 3 contract failed: Monaco must warm after app bootstrap starts and before release enhancement work.');
}

console.log('Phase 3 shell-first responsiveness / persistence / Monaco contract: OK');
