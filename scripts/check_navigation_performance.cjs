'use strict';

const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const fail = (message) => { console.error(`navigation performance contract: FAIL · ${message}`); process.exit(1); };
const must = (condition, message) => { if (!condition) fail(message); };

const index = read('renderer/index.html');
const performanceJs = read('renderer/release-performance.js');
const navigationJs = read('renderer/release-navigation.js');
const lifecycleJs = read('renderer/dom-lifecycle.js');
const performanceCss = read('renderer/release-performance.css');
const preload = read('electron/preload-v2.cjs');
const phase3 = read('renderer/release-phase3.js');
const serviceCompat = read('backend/dragonwilds_service_compat.py');
const appV2 = read('renderer/app-v2.js');

const appPos = index.indexOf('app.js?');
const perfPos = index.indexOf('release-performance.js?');
const navigationPos = index.indexOf('release-navigation.js?');
must(appPos >= 0 && perfPos > appPos && navigationPos > perfPos,
  'performance coordinator must load after app.js but before historical release enhancers');
must(index.includes('release-performance.css?'), 'performance CSS must be packaged by the renderer entrypoint');

must(lifecycleJs.includes('const callbacks = new Set()') && lifecycleJs.includes('observer = new MutationObserver'),
  'document-wide renderer updates must share one lifecycle observer');
must(performanceJs.includes("document.addEventListener('wheel'") && performanceJs.includes("document.addEventListener('scroll'"),
  'scroll/navigation interaction must take priority over presentation enhancement work');
must(!performanceJs.includes('window.MutationObserver ='),
  'performance diagnostics must not replace the browser MutationObserver implementation');
must(performanceCss.includes('content-visibility: auto'), 'long off-screen UI rows must use Chromium content visibility');
must(performanceCss.includes('overscroll-behavior: contain'), 'main scroll surface must use bounded overscroll behavior');
must(appV2.includes('function renderPersistentShell(page)') && appV2.includes("root.dataset.persistentShell='1'"),
  'full-mode navigation must mount one persistent titlebar/sidebar shell');
must(appV2.includes('else shellUpdate=renderPersistentShell(page);') && appV2.includes('main.__dwsPageMarkup=page;') && appV2.includes('main.innerHTML=page;'),
  'ordinary renders must update the main workspace without rebuilding the navigation rail');
must(appV2.includes('if(!shellUpdate.changed)'), 'unchanged snapshots must not repaint the workspace');
must(appV2.includes('const persistentShellBindings=new WeakMap()') && appV2.includes('bindPersistentOnce('),
  'persistent shell controls must retain exactly one event binding across content renders');

// Menu names/visibility must settle before paint. Decorative release enhancements
// may stay coordinated/idle, but navigation itself must not pop into place later.
must(navigationJs.includes('function applyNavigationCritical') && navigationJs.includes('function applyPresentationEnhancements'),
  'navigation-critical cleanup must be separated from decorative presentation work');
must(navigationJs.includes("const appRoot = document.getElementById('app')"),
  'navigation-critical cleanup must target the app root');
must(navigationJs.includes('window.DragonwildsDOMLifecycle.register((records)'),
  'navigation cleanup must subscribe to the shared lifecycle');
must(navigationJs.includes('function matchingNodes') && navigationJs.includes('for (const node of record.addedNodes'),
  'navigation cleanup must inspect only newly inserted subtrees instead of rescanning the app root');
must(navigationJs.includes('window.DragonwildsDOMLifecycle.register(scheduleEnhancements)'),
  'noncritical navigation enhancements must use the shared lifecycle');

for (const token of ['Profiles &amp; Data', 'Profile Runtime Staging', 'id="machine-paths-card"', "data-application-settings-tab=\"runtimes\""]) {
  must(appV2.includes(token), `coherent profile data controls must retain ${token}`);
}
must(!appV2.includes('update-client-ue4ss') && !appV2.includes('update-client-runeschema'),
  'machine-wide runtime update controls must stay retired in favor of profile staging');
must(!appV2.includes('Client &amp; Singleplayer Runtime'),
  'legacy duplicate client runtime settings must remain consolidated into Runtime & Data');

for (const method of ['singleplayer.inventory', 'server.world.inventory']) {
  const match = preload.match(new RegExp(`'${method.replaceAll('.', '\\.')}'\\s*:\\s*\\{\\s*ttl:\\s*(\\d+),\\s*stale:\\s*(\\d+)`));
  must(match, `${method} must have an explicit preload cache policy`);
  must(Number(match[1]) >= 30000, `${method} hot-cache TTL is too short for free tab navigation`);
  must(Number(match[2]) >= 300000, `${method} stale-while-revalidate window is too short`);
}
must(preload.includes('const MAX_PREWARM_CONCURRENCY = 2'), 'background module prewarm must be concurrency bounded');
must(preload.includes('const workers = Array.from') && !preload.includes('Promise.allSettled([...unique.values()]'),
  'prewarm must use the bounded worker queue rather than unbounded fan-out');

const criticalStart = phase3.indexOf('function criticalRequests');
const criticalEnd = phase3.indexOf('async function prewarmCritical', criticalStart);
const critical = phase3.slice(criticalStart, criticalEnd);
// Shell-first readiness intentionally warms cheap persisted/local workspaces so
// Characters and Mods do not pay a first-click cold start. Expensive/networked
// surfaces and any authoritative deep scan remain outside this startup slice.
for (const required of ['characters.list', 'singleplayer.inventory', 'server.world.inventory']) {
  must(critical.includes(required), `shell-first warmup must include local cached ${required}`);
}
for (const forbidden of [
  'application.rsdw.status', 'application.rsdw.refresh', 'application.map.status',
  'application.map.refresh', 'world.browser.refresh', 'world.directory.refresh',
  'application.recommendations.refresh', 'server.backups.list', 'rescan: true',
]) {
  must(!critical.includes(forbidden), `startup shell warmup must not include heavyweight ${forbidden}`);
}
must(phase3.includes("tab === 'mods'") && phase3.includes('rescan: false'), 'Mods tabs must warm the cached inventory first');
must(phase3.includes('scheduleInventoryVerification') && phase3.includes('rescan: true'),
  'Found Mods must receive an idle authoritative filesystem rescan after cached paint');

must(serviceCompat.includes('def _inventory_cache(profile: dict)') && serviceCompat.includes('def _cache_local_inventory') && serviceCompat.includes('def _cache_server_inventory'),
  'Found Mods must retain the persistent profile metadata cache');
must(serviceCompat.includes('bool(params.get("rescan"))') && serviceCompat.includes('not cached["updated_at"]'),
  'inventory RPC must use cache normally and reserve deep scan for explicit/first-run refresh');

console.log('Fast shell navigation / Found Mods cache contract: PASS');
