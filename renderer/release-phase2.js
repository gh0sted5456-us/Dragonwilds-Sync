(() => {
  'use strict';

  const bridge = window.dragonwilds;
  if (!bridge?.invoke) return;

  let cachedState = null;
  let cachedAt = 0;
  let lastSelection = { kind: '', id: '' };
  const serverSaveCache = new Map();
  const serverSaveInFlight = new Map();
  let serverCardRefreshActive = false;

  const text = (value) => String(value ?? '').trim();
  const invoke = (method, params = {}) => bridge.invoke(method, params);

  async function stateSnapshot(force = false) {
    const shared = window.__DWSYNC_STATE__;
    if (shared && !force) {
      cachedState = shared;
      cachedAt = Date.now();
      return shared;
    }
    if (!force && cachedState && Date.now() - cachedAt < 1800) return cachedState;
    cachedState = await invoke('state.get', {});
    cachedAt = Date.now();
    return cachedState;
  }

  function localWorlds(state) {
    return state?.client?.private_worlds || (state?.client?.singleplayer ? [state.client.singleplayer] : []);
  }

  function serverWorlds(state) {
    return state?.server_profiles || [];
  }

  function worldFor(state, kind, id) {
    const rows = kind === 'server' ? serverWorlds(state) : localWorlds(state);
    return rows.find((row) => text(row?.id) === text(id)) || null;
  }

  function rememberSelection(node) {
    const directServer = node.closest?.('[data-server-manage], [data-server-launch], [data-server-stop]');
    const directLocal = node.closest?.('[data-private-manage], [data-private-launch], [data-private-coop]');
    if (directServer) {
      const id = directServer.dataset.serverManage || directServer.dataset.serverLaunch || directServer.dataset.serverStop;
      if (id) lastSelection = { kind: 'server', id };
      return;
    }
    if (directLocal) {
      const id = directLocal.dataset.privateManage || directLocal.dataset.privateLaunch || directLocal.dataset.privateCoop;
      if (id) lastSelection = { kind: 'local', id };
      return;
    }
    const card = node.closest?.('[data-world-id][data-server-card]');
    if (card?.dataset.worldId) {
      lastSelection = { kind: card.dataset.serverCard === '1' ? 'server' : 'local', id: card.dataset.worldId };
    }
  }

  document.addEventListener('pointerdown', (event) => rememberSelection(event.target), true);
  document.addEventListener('click', (event) => rememberSelection(event.target), true);

  function localDetectedSave(state, id) {
    return (state?.client?.detected_world_saves || []).find((row) => text(row?.id) === text(id)) || null;
  }

  function normalizedSaveState(state, kind, world) {
    if (!world) return { known: false, loaded: false, file: '', count: 0 };
    const summary = world.save_state && typeof world.save_state === 'object' ? world.save_state : null;
    if (kind === 'server') {
      const live = serverSaveCache.get(text(world.id));
      if (live) return live;
      // settings.json can prove a configured association immediately, but an
      // older dedicated profile may still own a valid stored snapshot that has
      // not been migrated into save associations yet. Never display a false
      // "no save" while that cheap local status check is still pending.
      if (summary && (summary.loaded === true || Number(summary.associated_count || 0) > 0)) {
        return {
          known: true,
          loaded: summary.loaded === true,
          file: text(summary.active_file),
          count: Number(summary.associated_count || 0),
        };
      }
      return { known: false, loaded: false, file: '', count: 0 };
    }
    if (summary) {
      return {
        known: true,
        loaded: summary.loaded === true,
        file: text(summary.active_file),
        count: Number(summary.associated_count || 0),
      };
    }
    const detected = localDetectedSave(state, world.id);
    if (detected) return { known: true, loaded: true, file: text(detected.save_file), count: 1 };
    return { known: true, loaded: false, file: '', count: 0 };
  }

  function saveIndicatorMarkup(save, compact = false) {
    const loaded = save?.loaded === true;
    const known = save?.known !== false;
    const label = !known ? 'SAVE STATUS PENDING' : (loaded ? 'WORLD SAVE LOADED' : 'NO WORLD SAVE LOADED');
    const detail = loaded && save.file ? ` · ${save.file}` : (loaded && Number(save.count) > 1 ? ` · ${save.count} associated` : '');
    return `<span class="phase2-save-indicator ${!known ? 'unknown' : (loaded ? 'loaded' : 'empty')} ${compact ? 'compact' : ''}" title="${loaded && save.file ? String(save.file).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;') : label}">${label}${compact ? '' : detail}</span>`;
  }

  async function refreshServerSave(worldId) {
    const id = text(worldId);
    if (!id) return null;
    const cached = serverSaveCache.get(id);
    if (cached && Date.now() - Number(cached.at || 0) < 10000) return cached;
    if (serverSaveInFlight.has(id)) return serverSaveInFlight.get(id);
    const pending = invoke('server.world.save.status', { id }).then((payload) => {
      const loaded = Boolean(
        Number(payload?.live_files || 0) > 0 || Number(payload?.snapshot_files || 0) > 0 ||
        text(payload?.live_path) || text(payload?.snapshot_path)
      );
      const path = text(payload?.live_path || payload?.snapshot_path);
      const row = {
        known: true,
        loaded,
        file: path ? path.split(/[\\/]/).filter(Boolean).pop() || '' : '',
        count: loaded ? 1 : 0,
        at: Date.now(),
      };
      serverSaveCache.set(id, row);
      return row;
    }).catch(() => {
      const row = { known: false, loaded: false, file: '', count: 0, at: Date.now() };
      serverSaveCache.set(id, row);
      return row;
    }).finally(() => serverSaveInFlight.delete(id));
    serverSaveInFlight.set(id, pending);
    return pending;
  }

  function enhanceWorldManagementDirectConnect() {
    const heading = [...document.querySelectorAll('h1')].find((node) => text(node.textContent) === 'World Management');
    if (!heading) return;
    const pageHeader = heading.closest('.page-header');
    const actions = pageHeader?.querySelector('.header-actions');
    if (!actions || actions.querySelector('#phase2-direct-connect')) return;
    const button = document.createElement('button');
    button.id = 'phase2-direct-connect';
    button.type = 'button';
    button.className = 'btn ghost';
    button.textContent = '+ Direct Connect';
    button.title = 'Add or open a Direct Connect World profile';
    button.addEventListener('click', () => document.querySelector('#add-world-card')?.click());
    const dedicated = actions.querySelector('#add-server-world');
    if (dedicated) dedicated.insertAdjacentElement('afterend', button);
    else actions.appendChild(button);
  }

  function addCardSaveIndicator(card, state) {
    if (card.querySelector('.phase2-card-save-state')) return;
    const id = text(card.dataset.worldId);
    if (!id) return;
    const kind = card.dataset.serverCard === '1' ? 'server' : 'local';
    const world = worldFor(state, kind, id);
    if (!world) return; // public/favorite World cards are not managed profiles.
    const save = normalizedSaveState(state, kind, world);
    const holder = document.createElement('span');
    holder.className = 'phase2-card-save-state';
    holder.innerHTML = saveIndicatorMarkup(save, true);
    const listTitle = card.querySelector('.world-list-title');
    const cardBody = card.querySelector('.world-card-body');
    if (listTitle) listTitle.appendChild(holder);
    else if (cardBody) cardBody.prepend(holder);
    else card.appendChild(holder);
  }

  function enhanceWorldCards(state) {
    document.querySelectorAll('[data-world-id][data-server-card]').forEach((card) => addCardSaveIndicator(card, state));
  }

  function updateServerCardIndicators(id, save) {
    document.querySelectorAll('[data-world-id][data-server-card="1"]').forEach((card) => {
      if (text(card.dataset.worldId) !== text(id)) return;
      const holder = card.querySelector('.phase2-card-save-state');
      if (holder) holder.innerHTML = saveIndicatorMarkup(save, true);
    });
  }

  async function refreshVisibleServerCardSaves(state) {
    if (serverCardRefreshActive) return;
    const ids = [...new Set([...document.querySelectorAll('[data-world-id][data-server-card="1"]')]
      .map((card) => text(card.dataset.worldId))
      .filter((id) => id && worldFor(state, 'server', id)))];
    if (!ids.length) return;
    serverCardRefreshActive = true;
    try {
      // Resolve sequentially so opening World Management never launches a
      // burst of directory probes. Cached profile state paints first; these
      // local checks refine only the visible dedicated cards afterward.
      for (const id of ids) {
        const world = worldFor(state, 'server', id);
        if (normalizedSaveState(state, 'server', world).known) continue;
        const save = await refreshServerSave(id);
        updateServerCardIndicators(id, save);
      }
    } finally {
      serverCardRefreshActive = false;
    }
  }

  function joinProfilePath(base, kind, id) {
    const separator = String(base || '').includes('\\') ? '\\' : '/';
    const clean = String(base || '').replace(/[\\/]+$/, '');
    const branch = kind === 'server' ? ['profiles', 'world', 'dedicated', id] : ['profiles', 'world', 'local', id];
    return [clean, ...branch].join(separator);
  }

  async function openProfileFolder(kind, id) {
    const state = await stateSnapshot();
    const world = worldFor(state, kind, id);
    let target = text(world?.profile_path);
    if (!target) {
      const paths = await invoke('application.storage.paths', {});
      target = joinProfilePath(paths?.app_data, kind, id);
    }
    const ok = await bridge.openPath?.(target);
    if (ok === false) throw new Error(`Windows Explorer could not open ${target}`);
    return target;
  }

  function clickModsTab(kind) {
    const selector = kind === 'server' ? '[data-server-tab="mods"]' : '[data-private-tab="mods"]';
    document.querySelector(selector)?.click();
  }

  function groupTabs(kind) {
    const marker = kind === 'server' ? '#detach-server-world' : '#detach-private-world';
    if (!document.querySelector(marker)) return;
    const tabs = document.querySelector('.server-shell-card > .server-tabs');
    if (!tabs || tabs.dataset.phase2Grouped === '1') return;
    const attr = kind === 'server' ? 'serverTab' : 'privateTab';
    const buttons = new Map([...tabs.querySelectorAll(`button[data-${kind === 'server' ? 'server-tab' : 'private-tab'}]`)]
      .map((button) => [button.dataset[attr], button]));
    const groups = kind === 'server'
      ? [
          ['Profile', ['overview', 'save-editor', 'mods', 'configuration']],
          ['Tools', ['spawner', 'console']],
          ['Hosting', ['networking', 'maintenance']],
          ['Roster', ['players', 'map']],
          ['History', ['feedback', 'activity']],
        ]
      : [
          ['Profile', ['overview', 'save-editor', 'mods', 'configuration']],
          ['Hosting', ['broadcast', 'networking', 'maintenance']],
          ['Roster', ['players', 'map']],
        ];
    tabs.querySelectorAll('.server-tab-group').forEach((label) => label.remove());
    const fragment = document.createDocumentFragment();
    const used = new Set();
    for (const [label, ids] of groups) {
      const present = ids.map((id) => buttons.get(id)).filter(Boolean);
      if (!present.length) continue;
      const groupLabel = document.createElement('span');
      groupLabel.className = `server-tab-group phase2-tab-group tab-group-${label.toLowerCase()}`;
      groupLabel.textContent = label;
      fragment.appendChild(groupLabel);
      present.forEach((button) => { fragment.appendChild(button); used.add(button); });
    }
    [...buttons.values()].filter((button) => !used.has(button)).forEach((button) => fragment.appendChild(button));
    tabs.replaceChildren(fragment);
    tabs.dataset.phase2Grouped = '1';
  }

  function resolveDetailIdentity(state, kind) {
    if (lastSelection.kind === kind && lastSelection.id && worldFor(state, kind, lastSelection.id)) return lastSelection.id;
    if (kind === 'server') return text(state?.server?.active_world_id || state?.server?.runtime?.active_profile_id || serverWorlds(state)[0]?.id);
    return text(state?.client?.active_private_world_id || state?.client?.live_world_id || localWorlds(state)[0]?.id);
  }

  function addDetailActions(state, kind) {
    const detach = document.querySelector(kind === 'server' ? '#detach-server-world' : '#detach-private-world');
    if (!detach) return;
    const actions = detach.closest('.header-actions');
    if (!actions) return;
    const id = resolveDetailIdentity(state, kind);
    if (!id) return;
    lastSelection = { kind, id };

    if (!actions.querySelector('#phase2-view-mods')) {
      const viewMods = document.createElement('button');
      viewMods.id = 'phase2-view-mods';
      viewMods.type = 'button';
      viewMods.className = 'btn ghost';
      viewMods.textContent = 'View Mods';
      viewMods.title = 'Open this World profile\'s Mods view';
      viewMods.addEventListener('click', () => clickModsTab(kind));
      detach.insertAdjacentElement('afterend', viewMods);
    }

    if (!actions.querySelector('#phase2-see-profile')) {
      const explorer = document.createElement('button');
      explorer.id = 'phase2-see-profile';
      explorer.type = 'button';
      explorer.className = 'btn ghost';
      explorer.textContent = 'See in Explorer';
      explorer.title = 'Open this managed World profile in Windows Explorer';
      explorer.addEventListener('click', async () => {
        explorer.disabled = true;
        try { await openProfileFolder(kind, id); }
        catch (error) { console.error('[Phase 2] See in Explorer failed:', error); }
        finally { explorer.disabled = false; }
      });
      actions.querySelector('#phase2-view-mods')?.insertAdjacentElement('afterend', explorer);
    }

    if (!actions.querySelector('.phase2-detail-save-state')) {
      const world = worldFor(state, kind, id);
      const holder = document.createElement('span');
      holder.className = 'phase2-detail-save-state';
      holder.innerHTML = saveIndicatorMarkup(normalizedSaveState(state, kind, world));
      actions.prepend(holder);
    }
  }

  async function refreshDedicatedDetailSave(state) {
    if (!document.querySelector('#detach-server-world')) return;
    const id = resolveDetailIdentity(state, 'server');
    if (!id) return;
    const save = await refreshServerSave(id);
    const holder = document.querySelector('.phase2-detail-save-state');
    if (holder && resolveDetailIdentity(await stateSnapshot(), 'server') === id) holder.innerHTML = saveIndicatorMarkup(save);
    updateServerCardIndicators(id, save);
  }

  async function enhance() {
    let state;
    try { state = await stateSnapshot(); }
    catch (_) { return; }
    enhanceWorldManagementDirectConnect();
    enhanceWorldCards(state);
    refreshVisibleServerCardSaves(state).catch(() => {});
    if (document.querySelector('#detach-private-world')) {
      addDetailActions(state, 'local');
    }
    if (document.querySelector('#detach-server-world')) {
      addDetailActions(state, 'server');
      refreshDedicatedDetailSave(state).catch(() => {});
    }
  }

  let queued = false;
  function queueEnhance() {
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      enhance().catch(() => {});
    });
  }

  const observer = new MutationObserver(queueEnhance);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', queueEnhance, { once: true });
  queueEnhance();
})();
