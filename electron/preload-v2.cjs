const { contextBridge, ipcRenderer, webUtils } = require('electron');

// Keep the Quick presentation bridge in this self-contained preload. Sandboxed
// Electron preload scripts can use Electron's built-in modules, but they cannot
// require another project-local preload file.
contextBridge.exposeInMainWorld('dragonwildsV3', {
  createQuickShortcut: (data) => ipcRenderer.invoke('dragonwilds:create-v3-quick-shortcut', data || {}),
  quickContext: () => ({
    enabled: process.env.DWS_V3_QUICK === '1',
    profileId: String(process.env.DWS_V3_QUICK_PROFILE || ''),
    mode: ['player', 'coop', 'server'].includes(String(process.env.DWS_V3_QUICK_MODE || '')) ? String(process.env.DWS_V3_QUICK_MODE) : 'player',
    autoStart: process.env.DWS_V3_QUICK_AUTOSTART === '1',
  }),
});

const invokeCache = new Map();
const invokeInFlight = new Map();
const invokeActivityListeners = new Set();
const invokeMetrics = [];
const MAX_METRICS = 160;
const READ_TIMEOUT_MS = 15000;
const DEFAULT_INVOKE_TIMEOUT_MS = 5 * 60 * 1000;
const LONG_INVOKE_TIMEOUT_MS = 20 * 60 * 1000;
const BACKGROUND_INVOKE_TIMEOUT_MS = 60 * 1000;
const MAX_PREWARM_CONCURRENCY = 2;
let cacheGeneration = 0;

// Navigation reads deliberately favor a briefly stale local answer over making
// a tab click wait on filesystem/network work. Managed writes invalidate the
// relevant entries immediately; explicit force/refresh/rescan/verify always
// bypasses this cache. Mod inventories also have a persistent backend profile
// cache, with an idle authoritative rescan scheduled by release-phase3.js.
const READ_POLICIES = Object.freeze({
  'characters.list': { ttl: 15000, stale: 60000 },
  'singleplayer.inventory': { ttl: 60000, stale: 600000 },
  'server.world.inventory': { ttl: 60000, stale: 600000 },
  'singleplayer.config.list': { ttl: 30000, stale: 120000 },
  'server.world.config.list': { ttl: 30000, stale: 120000 },
  'singleplayer.mod.files': { ttl: 30000, stale: 120000 },
  'server.world.mod.files': { ttl: 60000, stale: 600000 },
  'singleplayer.profile.get': { ttl: 30000, stale: 120000 },
  'world.save.editor.read': { ttl: 10000, stale: 30000 },
  'server.world.save.status': { ttl: 10000, stale: 30000 },
  'server.backups.list': { ttl: 30000, stale: 120000 },
  'server.world.starter_characters.list': { ttl: 30000, stale: 120000 },
  'server.world.character_submissions.list': { ttl: 30000, stale: 120000 },
  'server.feedback.list': { ttl: 15000, stale: 60000 },
  'server.access.connections': { ttl: 5000, stale: 15000 },
  'server.spawner.catalog': { ttl: 30000, stale: 120000 },
  'server.console.catalog': { ttl: 3000, stale: 10000 },
  'application.map.status': { ttl: 30000, stale: 120000 },
  'application.map.overlays': { ttl: 60000, stale: 300000 },
  'application.rsdw.status': { ttl: 30000, stale: 120000 },
  'application.storage.paths': { ttl: 300000, stale: 900000 },
});

const DEDUPE_ONLY = new Set([
  'state.get',
  'server.runtime.status',
  'application.trash.list',
]);

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (!value || typeof value !== 'object') return value;
  const out = {};
  for (const key of Object.keys(value).sort()) out[key] = stableValue(value[key]);
  return out;
}

function requestKey(method, params) {
  let suffix = '';
  try { suffix = JSON.stringify(stableValue(params || {})); }
  catch (_) { suffix = '{}'; }
  return `${String(method || '')}::${suffix}`;
}

function cloneValue(value) {
  try { return structuredClone(value); }
  catch (_) {
    try { return JSON.parse(JSON.stringify(value)); }
    catch (_) { return value; }
  }
}

function cacheSafeValue(value) {
  const copy = cloneValue(value);
  // Read RPCs sometimes include a convenience public-state snapshot. Replaying
  // that snapshot later could roll the renderer back after an unrelated write,
  // so cached reads carry only their method-specific payload.
  if (copy && typeof copy === 'object' && !Array.isArray(copy) && Object.prototype.hasOwnProperty.call(copy, 'state')) delete copy.state;
  return copy;
}

function bypassReadCache(params) {
  const p = params && typeof params === 'object' ? params : {};
  return p.force === true || p.refresh === true || p.rescan === true || p.verify === true;
}

function emitInvokeActivity(event) {
  for (const listener of [...invokeActivityListeners]) {
    try { listener(cloneValue(event)); } catch (_) {}
  }
}

function recordMetric(metric) {
  invokeMetrics.push(metric);
  if (invokeMetrics.length > MAX_METRICS) invokeMetrics.splice(0, invokeMetrics.length - MAX_METRICS);
}

function invalidatePrefix(prefix) {
  cacheGeneration += 1;
  for (const key of [...invokeCache.keys()]) if (key.startsWith(prefix)) invokeCache.delete(key);
  // A read that began before a mutation must not become the new cache authority
  // after the mutation completes. Dropping its in-flight key allows a fresh read;
  // generation checks below prevent the old promise from repopulating cache.
  for (const key of [...invokeInFlight.keys()]) if (key.startsWith(prefix)) invokeInFlight.delete(key);
}

function invalidateMethod(method) {
  invalidatePrefix(`${String(method || '')}::`);
}

function invalidateAfterMutation(method) {
  const name = String(method || '');
  if (name.startsWith('characters.') && name !== 'characters.list') invalidatePrefix('characters.list::');
  if (name.startsWith('singleplayer.mod.') || name.startsWith('singleplayer.profile.') || name.startsWith('singleplayer.config.')) {
    invalidatePrefix('singleplayer.inventory::');
    invalidatePrefix('singleplayer.config.list::');
    invalidatePrefix('singleplayer.mod.files::');
    invalidatePrefix('singleplayer.profile.get::');
  }
  if (name.startsWith('server.world.mod.') || name.startsWith('server.world.activate') || name.startsWith('server.world.update')) {
    invalidatePrefix('server.world.inventory::');
    if (name !== 'server.world.mod.files') invalidatePrefix('server.world.mod.files::');
  }
  if (name.startsWith('server.world.config.') && name !== 'server.world.config.list') invalidatePrefix('server.world.config.list::');
  if (name.startsWith('server.backups.') && name !== 'server.backups.list') invalidatePrefix('server.backups.list::');
  if (name.startsWith('world.save.')) invalidatePrefix('world.save.editor.read::');
  if (name.startsWith('world.save.') || name.startsWith('server.world.save.')) invalidatePrefix('server.world.save.status::');
  if (name === 'application.rsdw.refresh') invalidatePrefix('application.rsdw.status::');
  if (name === 'application.map.refresh') {
    invalidatePrefix('application.map.status::');
    invalidatePrefix('application.map.overlays::');
  }
}

function rendererTimeoutFor(method) {
  const name=String(method||'').toLowerCase();
  if(READ_POLICIES[method]||DEDUPE_ONLY.has(method))return READ_TIMEOUT_MS;
  if(['world.discovery.heartbeat','client.background.tick','server.scheduler.tick','server.network.benchmark.maybe','application.rsdw.maybe'].includes(name))return BACKGROUND_INVOKE_TIMEOUT_MS;
  if(/(?:backup|restore|update|install|download|sync|refresh|import|export|scan|reconcile|materialize)/.test(name))return LONG_INVOKE_TIMEOUT_MS;
  return DEFAULT_INVOKE_TIMEOUT_MS;
}

function ipcReadWithTimeout(method, params) {
  const timeoutMs=rendererTimeoutFor(method);
  const request = ipcRenderer.invoke('dragonwilds:invoke', method, params, {timeoutMs});
  let timer = null;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`Backend request timed out after ${Math.round(timeoutMs / 1000)}s: ${method}`)), timeoutMs);
  });
  timer.unref?.();
  return Promise.race([request, timeout]).finally(() => { if (timer) clearTimeout(timer); });
}

async function rawInvoke(method, params = {}, meta = {}) {
  const startedAt = performance.now();
  if (!meta.background) emitInvokeActivity({ phase: 'start', method, key: meta.key || '', background: false, at: Date.now() });
  try {
    const result = await ipcReadWithTimeout(method, params);
    const durationMs = Math.max(0, performance.now() - startedAt);
    recordMetric({ method, duration_ms: Math.round(durationMs * 10) / 10, cache: false, background: !!meta.background, ok: true, at: Date.now() });
    emitInvokeActivity({ phase: 'end', method, key: meta.key || '', duration_ms: durationMs, background: !!meta.background, at: Date.now() });
    return result;
  } catch (error) {
    const durationMs = Math.max(0, performance.now() - startedAt);
    recordMetric({ method: name, duration_ms: Math.round(durationMs * 10) / 10, cache: false, background: !!meta.background, ok: false, at: Date.now() });
    emitInvokeActivity({ phase: 'error', method, key: meta.key || '', duration_ms: durationMs, background: !!meta.background, message: String(error?.message || error || 'Request failed'), at: Date.now() });
    throw error;
  }
}

function refreshCachedRead(method, params, key, background = false) {
  if (invokeInFlight.has(key)) return invokeInFlight.get(key);
  const generation = cacheGeneration;
  const pending = rawInvoke(method, params, { key, background }).then((result) => {
    if (generation === cacheGeneration && invokeInFlight.get(key) === pending) {
      invokeCache.set(key, { value: cacheSafeValue(result), storedAt: Date.now() });
    }
    return cloneValue(result);
  }).finally(() => {
    if (invokeInFlight.get(key) === pending) invokeInFlight.delete(key);
  });
  invokeInFlight.set(key, pending);
  return pending;
}

async function coordinatedInvoke(method, params = {}, options = {}) {
  const name = String(method || '');
  const key = requestKey(name, params);
  const policy = READ_POLICIES[name];
  const background = options?.background === true;
  const explicitRefresh = bypassReadCache(params);

  // Force/Refresh/Rescan/Verify means exactly that: discard cached and in-flight
  // reads for this method before considering deduplication.
  if (policy && explicitRefresh) invalidateMethod(name);

  if (policy && !explicitRefresh) {
    const cached = invokeCache.get(key);
    const age = cached ? Math.max(0, Date.now() - cached.storedAt) : Infinity;
    if (cached && age <= policy.ttl) {
      recordMetric({ method: name, duration_ms: 0, cache: true, stale: false, background, ok: true, at: Date.now() });
      emitInvokeActivity({ phase: 'cache', method: name, key, stale: false, background, age_ms: age, at: Date.now() });
      return cloneValue(cached.value);
    }
    if (cached && policy.stale > 0 && age <= policy.stale) {
      recordMetric({ method: name, duration_ms: 0, cache: true, stale: true, background, ok: true, at: Date.now() });
      emitInvokeActivity({ phase: 'cache', method: name, key, stale: true, background, age_ms: age, at: Date.now() });
      refreshCachedRead(name, params, key, true).catch(() => {});
      return cloneValue(cached.value);
    }
    return refreshCachedRead(name, params, key, background);
  }

  if ((policy || DEDUPE_ONLY.has(name)) && invokeInFlight.has(key)) {
    recordMetric({ method: name, duration_ms: 0, cache: false, deduped: true, background, ok: true, at: Date.now() });
    emitInvokeActivity({ phase: 'dedupe', method: name, key, background, at: Date.now() });
    return cloneValue(await invokeInFlight.get(key));
  }

  const pending = rawInvoke(name, params, { key, background });
  if (policy || DEDUPE_ONLY.has(name)) invokeInFlight.set(key, pending);
  try {
    const result = await pending;
    if (!policy) invalidateAfterMutation(name);
    return cloneValue(result);
  } finally {
    if (invokeInFlight.get(key) === pending) invokeInFlight.delete(key);
  }
}

async function prewarmRequests(requests = []) {
  const unique = new Map();
  for (const row of Array.isArray(requests) ? requests : []) {
    const method = String(row?.method || '');
    if (!READ_POLICIES[method] && !DEDUPE_ONLY.has(method)) continue;
    const params = row?.params && typeof row.params === 'object' ? row.params : {};
    unique.set(requestKey(method, params), { method, params });
  }

  // Background warmups are deliberately bounded. A pointer toward one tab must
  // never fan out enough filesystem/network work to compete with scrolling or
  // another immediate UI action.
  const queue = [...unique.values()];
  let fulfilled = 0;
  let rejected = 0;
  async function worker() {
    while (queue.length) {
      const row = queue.shift();
      try {
        await coordinatedInvoke(row.method, row.params, { background: true });
        fulfilled += 1;
      } catch (_) {
        rejected += 1;
      }
    }
  }
  const workers = Array.from({ length: Math.min(MAX_PREWARM_CONCURRENCY, queue.length) }, () => worker());
  await Promise.all(workers);
  return { requested: unique.size, fulfilled, rejected };
}

contextBridge.exposeInMainWorld('dragonwilds', {
  invoke: (method, params = {}) => coordinatedInvoke(method, params),
  prewarm: (requests = []) => prewarmRequests(requests),
  requestStats: () => cloneValue(invokeMetrics),
  clearRequestCache: () => { cacheGeneration += 1; invokeCache.clear(); invokeInFlight.clear(); return true; },
  onRequestActivity: (callback) => {
    if (typeof callback !== 'function') return () => {};
    invokeActivityListeners.add(callback);
    return () => invokeActivityListeners.delete(callback);
  },
  adminStatus: () => ipcRenderer.invoke('dragonwilds:admin-status'),
  restartAsAdmin: () => ipcRenderer.invoke('dragonwilds:restart-admin'),
  restartApplication: () => ipcRenderer.invoke('dragonwilds:restart-application'),
  pickImage: () => ipcRenderer.invoke('dragonwilds:pick-image'),
  readRendererAsset: (relativePath) => ipcRenderer.invoke('dragonwilds:read-renderer-asset', String(relativePath || '')),
  pickLoadingArt: () => ipcRenderer.invoke('dragonwilds:pick-loading-art'),
  pickDirectory: () => ipcRenderer.invoke('dragonwilds:pick-directory'),
  pickExecutable: () => ipcRenderer.invoke('dragonwilds:pick-executable'),
  pickFile: (kind = 'all') => ipcRenderer.invoke('dragonwilds:pick-file', kind),
  filePath: (file) => { try { return webUtils.getPathForFile(file); } catch (_) { return ''; } },
  saveFile: (opts = {}) => ipcRenderer.invoke('dragonwilds:save-file', opts),
  createWorldShortcut: (data) => ipcRenderer.invoke('dragonwilds:create-world-shortcut', data),
  removeWorldShortcut: (name) => ipcRenderer.invoke('dragonwilds:remove-world-shortcut', name),
  backgroundSettings: (settings) => ipcRenderer.invoke('dragonwilds:background-settings', settings),
  windowPreferences: (settings) => ipcRenderer.invoke('dragonwilds:window-preferences', settings),
  notify: (event) => ipcRenderer.invoke('dragonwilds:notify', event),
  openMainWindow: () => ipcRenderer.invoke('dragonwilds:open-main-window'),
  openMinimalMode: (worldId) => ipcRenderer.invoke('dragonwilds:open-minimal-mode', worldId),
  openPath: (target) => ipcRenderer.invoke('dragonwilds:open-path', target),
  revealPath: (target) => ipcRenderer.invoke('dragonwilds:reveal-path', target),
  copyText: (text) => ipcRenderer.invoke('dragonwilds:copy-text', text),
  fileSha256: (target) => ipcRenderer.invoke('dragonwilds:file-sha256', target),
  openExternal: (target) => ipcRenderer.invoke('dragonwilds:open-external', target),
  openInAppBrowser: (target) => ipcRenderer.invoke('dragonwilds:open-in-app-browser', target),
  captureWebview: (payload = {}) => ipcRenderer.invoke('dragonwilds:capture-webview', payload),
  // Application dialogs intentionally remain renderer-owned. app.js already
  // falls back to its in-app desktop/modal surface when no native managed
  // dialog bridge is exposed. Genuine website content continues through the
  // browser-window bridge above (for example Nexus pages).
  windowMinimize: () => ipcRenderer.invoke('dragonwilds:window-minimize'),
  windowRestore: () => ipcRenderer.invoke('dragonwilds:window-restore'),
  windowToggleMaximize: () => ipcRenderer.invoke('dragonwilds:window-toggle-maximize'),
  windowClose: () => ipcRenderer.invoke('dragonwilds:window-close'),
  windowState: () => ipcRenderer.invoke('dragonwilds:window-state'),
  appUpdateMode: () => ipcRenderer.invoke('dragonwilds:app-update-mode'),
  appUpdateCheck: (opts = {}) => ipcRenderer.invoke('dragonwilds:app-update-check', opts),
  appUpdateApply: (opts = {}) => ipcRenderer.invoke('dragonwilds:app-update-apply', opts),
  appUpdateResult: () => ipcRenderer.invoke('dragonwilds:app-update-result'),
  appUpdateDismissResult: () => ipcRenderer.invoke('dragonwilds:app-update-dismiss-result'),
  rsdwWebviewPreload: () => ipcRenderer.invoke('dragonwilds:rsdw-webview-preload'),
  legalText: () => ipcRenderer.invoke('dragonwilds:legal-text'),
  configureRsdwToolkitRoot: (root) => ipcRenderer.invoke('dragonwilds:rsdw-toolkit-root', root),
  openDetachedWindow: (payload = {}) => ipcRenderer.invoke('dragonwilds:detached-open', payload),
  detachedContext: () => ipcRenderer.invoke('dragonwilds:detached-context'),
  listDetachedWindows: () => ipcRenderer.invoke('dragonwilds:detached-list'),
  restoreDetachedWindow: (id) => ipcRenderer.invoke('dragonwilds:detached-restore', id),
  closeDetachedWindow: (id) => ipcRenderer.invoke('dragonwilds:detached-close', id),
  onDetachedWindowsChanged: (callback) => { if (typeof callback !== 'function') return () => {}; const fn=(_event,items)=>callback(items||[]); ipcRenderer.on('dragonwilds:detached-changed',fn); return ()=>ipcRenderer.removeListener('dragonwilds:detached-changed',fn); },
  openManagedDialog: (payload = {}) => ipcRenderer.invoke('dragonwilds:managed-dialog-open', payload),
  managedDialogContent: (id) => ipcRenderer.invoke('dragonwilds:managed-dialog-content', id),
  managedDialogEvent: (payload = {}) => ipcRenderer.invoke('dragonwilds:managed-dialog-event', payload),
  updateManagedDialog: (payload = {}) => ipcRenderer.invoke('dragonwilds:managed-dialog-update', payload),
  closeManagedDialog: (id) => ipcRenderer.invoke('dragonwilds:managed-dialog-close', id),
  onManagedDialogEvent: (callback) => { if (typeof callback !== 'function') return () => {}; const fn=(_event,payload)=>callback(payload||{}); ipcRenderer.on('dragonwilds:managed-dialog-event',fn); return ()=>ipcRenderer.removeListener('dragonwilds:managed-dialog-event',fn); },
  onManagedDialogUpdate: (callback) => { if (typeof callback !== 'function') return () => {}; const fn=(_event,payload)=>callback(payload||{}); ipcRenderer.on('dragonwilds:managed-dialog-update',fn); return ()=>ipcRenderer.removeListener('dragonwilds:managed-dialog-update',fn); },
  onManagedDialogClosed: (callback) => { if (typeof callback !== 'function') return () => {}; const fn=(_event,payload)=>callback(payload||{}); ipcRenderer.on('dragonwilds:managed-dialog-closed',fn); return ()=>ipcRenderer.removeListener('dragonwilds:managed-dialog-closed',fn); },
  onJoinRequest: (callback) => { if (typeof callback !== 'function') return () => {}; const fn=(_event,payload)=>callback(payload||{}); ipcRenderer.on('dragonwilds:join-request',fn); return ()=>ipcRenderer.removeListener('dragonwilds:join-request',fn); },
  nexusStatus: () => ipcRenderer.invoke('dragonwilds:nexus-status'),
  nexusConnectSSO: () => ipcRenderer.invoke('dragonwilds:nexus-connect-sso'),
  nexusConnectDevelopmentKey: (key) => ipcRenderer.invoke('dragonwilds:nexus-connect-dev-key', key),
  nexusDisconnect: () => ipcRenderer.invoke('dragonwilds:nexus-disconnect'),
  nexusSearch: (query) => ipcRenderer.invoke('dragonwilds:nexus-search', query),
  nexusMod: (modId) => ipcRenderer.invoke('dragonwilds:nexus-mod', modId),
  nexusFiles: (modId) => ipcRenderer.invoke('dragonwilds:nexus-files', modId),
  nexusDownloadDescriptor: (data) => ipcRenderer.invoke('dragonwilds:nexus-download-descriptor', data),
  nexusDownloadStage: (data) => ipcRenderer.invoke('dragonwilds:nexus-download-stage', data),
  nexusPrepareArchive: (target) => ipcRenderer.invoke('dragonwilds:nexus-prepare-archive', target),
  onNexusBrowserDownload: (callback) => { if (typeof callback !== 'function') return () => {}; const fn=(_event,payload)=>callback(payload||{}); ipcRenderer.on('dragonwilds:nexus-browser-download',fn); return ()=>ipcRenderer.removeListener('dragonwilds:nexus-browser-download',fn); },
  discordActivity: (activity) => ipcRenderer.invoke('dragonwilds:discord-activity', activity),
  discordClear: () => ipcRenderer.invoke('dragonwilds:discord-clear'),
  discordStatus: () => ipcRenderer.invoke('dragonwilds:discord-status'),
});
