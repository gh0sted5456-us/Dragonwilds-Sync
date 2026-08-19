(() => {
  'use strict';

  const bridge = window.dragonwilds;
  if (!bridge?.prewarm || !bridge?.onRequestActivity) return;

  const query = new URLSearchParams(window.location.search);
  const minimalMode = query.get('minimal') === '1';
  const detachedMode = query.get('detached') === '1';
  const uiMetrics = [];
  const MAX_UI_METRICS = 120;
  const activeRequests = new Map();
  const delayedIndicators = new Map();
  const inventoryVerifiedAt = new Map();
  let lastWarmAt = 0;

  const text = (value) => String(value ?? '').trim();
  const now = () => performance.now();
  const clone = (value) => { try { return structuredClone(value); } catch (_) { return value; } };

  function pushUiMetric(metric) {
    uiMetrics.push({ ...metric, at: Date.now() });
    if (uiMetrics.length > MAX_UI_METRICS) uiMetrics.splice(0, uiMetrics.length - MAX_UI_METRICS);
  }

  function requestIdle(work, timeout = 1200) {
    if (typeof requestIdleCallback === 'function') return requestIdleCallback(work, { timeout });
    return setTimeout(work, 80);
  }

  function stateSnapshot() {
    return window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object' ? window.__DWSYNC_STATE__ : null;
  }

  function localProfileId(state) {
    return text(state?.client?.active_private_world_id || state?.client?.live_world_id || state?.client?.private_worlds?.[0]?.id || state?.client?.singleplayer?.id);
  }

  function serverProfileId(state) {
    return text(state?.server?.active_world_id || state?.server?.runtime?.active_profile_id || state?.server_profiles?.[0]?.id);
  }

  // Startup must make the shell usable first. Heavy modules (RSDW, map,
  // characters, inventories, backups, configs) are intentionally omitted here
  // and warmed only when the user actually heads toward that surface.
  function criticalRequests() {
    return minimalMode ? [] : [{ method: 'application.storage.paths', params: {} }];
  }

  async function prewarmCritical(force = false) {
    const state = stateSnapshot();
    if (!state) return;
    const stamp = Date.now();
    if (!force && stamp - lastWarmAt < 60000) return;
    lastWarmAt = stamp;
    const requests = criticalRequests(state);
    if (!requests.length) return;
    try { await bridge.prewarm(requests); } catch (_) {}
  }

  function prewarmProfile(kind, id, tab = '') {
    id = text(id);
    if (!id) return;
    const requests = [];
    if (kind === 'server') {
      // Opening a World defaults to Overview. Do not prewarm Mods, Config and
      // Backups merely because the World card was clicked.
      if (!tab || ['overview', 'maintenance', 'save-editor'].includes(tab)) requests.push({ method: 'server.world.save.status', params: { id } });
      if (tab === 'mods') requests.push({ method: 'server.world.inventory', params: { id, rescan: false } });
      if (['configuration', 'maintenance'].includes(tab)) requests.push({ method: 'server.world.config.list', params: { id } });
      if (tab === 'maintenance') requests.push({ method: 'server.backups.list', params: { id } });
      if (tab === 'save-editor') requests.push({ method: 'world.save.editor.read', params: { id, kind: 'server' } });
      if (tab === 'feedback') requests.push({ method: 'server.feedback.list', params: { id } });
      if (tab === 'players') requests.push({ method: 'server.access.connections', params: {} });
      if (tab === 'map') requests.push({ method: 'application.map.status', params: {} }, { method: 'application.map.overlays', params: {} });
    } else {
      if (!tab || ['overview', 'networking'].includes(tab)) requests.push({ method: 'singleplayer.profile.get', params: { profile_id: id } });
      if (tab === 'mods') requests.push({ method: 'singleplayer.inventory', params: { profile_id: id, rescan: false } });
      if (['configuration', 'maintenance'].includes(tab)) requests.push({ method: 'singleplayer.config.list', params: { profile_id: id } });
      if (tab === 'save-editor') requests.push({ method: 'world.save.editor.read', params: { id, kind: 'private' } });
      if (tab === 'map') requests.push({ method: 'application.map.status', params: {} }, { method: 'application.map.overlays', params: {} });
    }
    if (requests.length) bridge.prewarm(requests).catch(() => {});
  }

  function scheduleInventoryVerification(kind, id) {
    id = text(id);
    if (!id) return;
    const key = `${kind}:${id}`;
    const stamp = Date.now();
    if (stamp - Number(inventoryVerifiedAt.get(key) || 0) < 120000) return;
    inventoryVerifiedAt.set(key, stamp);
    // Found Mods opens from the persistent profile cache. A real filesystem
    // rescan follows only at idle, never on the click/scroll critical path.
    requestIdle(() => {
      const request = kind === 'server'
        ? { method: 'server.world.inventory', params: { id, rescan: true } }
        : { method: 'singleplayer.inventory', params: { profile_id: id, rescan: true } };
      bridge.prewarm([request]).catch(() => {});
    }, 2200);
  }

  function requestLabel(method) {
    if (method === 'characters.list' || method.startsWith('characters.')) return 'Character data';
    if (method === 'singleplayer.mod.files') return 'Mod files';
    if (method.includes('inventory')) return 'Mod inventory';
    if (method.includes('save')) return 'World save';
    if (method.includes('profile')) return 'World profile';
    if (method.includes('config')) return 'Configuration';
    if (method.includes('backups')) return 'Backups';
    if (method.includes('map.')) return 'Map data';
    if (method.includes('rsdw')) return 'RSDW data';
    if (method.includes('feedback')) return 'World feedback';
    if (method.includes('connections')) return 'Connections';
    if (method.includes('spawner')) return 'Spawner catalog';
    if (method.includes('console')) return 'Console data';
    if (method === 'state.get' || method === 'server.runtime.status') return 'Live status';
    return 'Details';
  }

  function indicatorHost() {
    return document.querySelector('.page-header .header-actions, .server-shell-card .header-actions, .detail-header .header-actions, .topbar-actions');
  }

  function clearIndicator(key) {
    const timer = delayedIndicators.get(key);
    if (timer) clearTimeout(timer);
    delayedIndicators.delete(key);
    document.querySelector(`[data-phase3-request="${CSS.escape(key)}"]`)?.remove();
  }

  function showIndicator(key, method, error = '') {
    const host = indicatorHost();
    if (!host || host.querySelector(`[data-phase3-request="${CSS.escape(key)}"]`)) return;
    const pill = document.createElement('span');
    pill.className = `phase3-load-pill${error ? ' error' : ''}`;
    pill.dataset.phase3Request = key;
    pill.title = error || `${requestLabel(method)} is loading in the background.`;
    pill.innerHTML = error
      ? `<span class="phase3-load-dot"></span><span>${requestLabel(method)} unavailable</span>`
      : `<span class="phase3-load-dot"></span><span>Loading ${requestLabel(method).toLowerCase()}…</span>`;
    host.prepend(pill);
    if (error) setTimeout(() => pill.remove(), 5000);
  }

  bridge.onRequestActivity((event) => {
    const key = text(event?.key || `${event?.method || 'request'}:${event?.at || Date.now()}`);
    const method = text(event?.method);
    if (!method || event?.background) return;
    if (event.phase === 'start') {
      activeRequests.set(key, { method, started: now() });
      const timer = setTimeout(() => {
        delayedIndicators.delete(key);
        if (activeRequests.has(key)) showIndicator(key, method);
      }, 220);
      delayedIndicators.set(key, timer);
      return;
    }
    if (event.phase === 'cache' || event.phase === 'dedupe') {
      clearIndicator(key);
      activeRequests.delete(key);
      return;
    }
    const active = activeRequests.get(key);
    if (active) {
      pushUiMetric({ type: 'backend_visible_request', method, duration_ms: Math.round((event.duration_ms ?? (now() - active.started)) * 10) / 10, ok: event.phase !== 'error' });
    }
    activeRequests.delete(key);
    clearIndicator(key);
    if (event.phase === 'error') showIndicator(key, method, text(event.message || 'Refresh failed'));
  });

  function markInteraction(kind, value) {
    window.__DWSYNC_FAST_NAV__?.markInteraction?.(180);
    const started = now();
    requestAnimationFrame(() => requestAnimationFrame(() => {
      pushUiMetric({ type: 'requested_to_first_paint', surface: kind, value: text(value), duration_ms: Math.round((now() - started) * 10) / 10 });
    }));
  }

  document.addEventListener('pointerdown', (event) => {
    const route = event.target?.closest?.('[data-route]');
    if (route) {
      markInteraction('route', route.dataset.route || '');
      return;
    }
    const server = event.target?.closest?.('[data-server-manage], [data-server-launch]');
    if (server) {
      const id = server.dataset.serverManage || server.dataset.serverLaunch;
      markInteraction('server-world', id);
      prewarmProfile('server', id);
      return;
    }
    const local = event.target?.closest?.('[data-private-manage], [data-private-launch]');
    if (local) {
      const id = local.dataset.privateManage || local.dataset.privateLaunch;
      markInteraction('local-world', id);
      prewarmProfile('local', id);
      return;
    }
    const serverTab = event.target?.closest?.('[data-server-tab]');
    if (serverTab) {
      const id = text(document.querySelector('[data-server-manage]')?.dataset.serverManage || stateSnapshot()?.server?.active_world_id || stateSnapshot()?.server?.runtime?.active_profile_id);
      const tab = serverTab.dataset.serverTab || '';
      markInteraction('server-tab', tab);
      prewarmProfile('server', id, tab);
      if (tab === 'mods') scheduleInventoryVerification('server', id);
      return;
    }
    const localTab = event.target?.closest?.('[data-private-tab]');
    if (localTab) {
      const id = text(document.querySelector('[data-private-manage]')?.dataset.privateManage || stateSnapshot()?.client?.active_private_world_id || stateSnapshot()?.client?.live_world_id);
      const tab = localTab.dataset.privateTab || '';
      markInteraction('local-tab', tab);
      prewarmProfile('local', id, tab);
      if (tab === 'mods') scheduleInventoryVerification('local', id);
      return;
    }
    const profileTab = event.target?.closest?.('[data-profile-tab]');
    if (profileTab?.dataset.profileTab === 'characters') {
      markInteraction('profile-tab', 'characters');
      requestIdle(() => bridge.prewarm([{ method: 'characters.list', params: {} }]).catch(() => {}), 900);
    }
  }, true);

  function waitForBootstrap() {
    if (stateSnapshot()) {
      requestIdle(() => prewarmCritical(true), 1800);
      return;
    }
    setTimeout(waitForBootstrap, 100);
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) requestIdle(() => prewarmCritical(false), 1800);
  });

  window.__DWSYNC_PERF__ = {
    snapshot: async () => ({
      backend: await bridge.requestStats(),
      ui: clone(uiMetrics),
      navigation: window.__DWSYNC_FAST_NAV__?.snapshot?.() || {},
    }),
    warm: () => prewarmCritical(true),
  };

  if (!detachedMode) waitForBootstrap();
})();
