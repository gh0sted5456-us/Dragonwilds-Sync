(() => {
  'use strict';

  const bridge = window.dragonwilds;
  if (!bridge?.invoke) return;

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
  const number = (value, fallback = '—') => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed.toLocaleString() : fallback;
  };
  const text = (value) => String(value ?? '').trim();
  const invoke = (method, params = {}) => bridge.invoke(method, params);

  let appState = null;
  let appStateAt = 0;
  let recommendationByUrl = new Map();
  let itemCatalogCache = { worldId: '', at: 0, items: [] };
  let lastNativeContextTarget = null;
  let consoleFilter = 'all';
  let consolePaused = false;
  let consoleRequestBusy = false;
  let lastConsolePayload = null;

  async function stateSnapshot(force = false) {
    if (window.__DWSYNC_STATE__) {
      appState = window.__DWSYNC_STATE__; appStateAt = Date.now();
      const rows = appState?.application?.recommended_mods?.mods || [];
      recommendationByUrl = new Map(rows.map((row) => [text(row.page_url), row]).filter(([url]) => url));
      return appState;
    }
    if (!force && appState && Date.now() - appStateAt < 2500) return appState;
    appState = await invoke('state.get', {});
    appStateAt = Date.now();
    const rows = appState?.application?.recommended_mods?.mods || [];
    recommendationByUrl = new Map(rows.map((row) => [text(row.page_url), row]).filter(([url]) => url));
    return appState;
  }

  function activeServerId(state = appState) {
    return text(state?.server?.active_world_id || state?.server?.runtime?.active_profile_id);
  }

  function externalImageUrl(value) {
    const raw = text(value);
    if (!raw) return '';
    if (/^data:image\//i.test(raw) || /^file:/i.test(raw) || /^https:\/\//i.test(raw) || /^http:\/\/127\.0\.0\.1(?::\d+)?\//i.test(raw)) return raw;
    const normalized = raw.replace(/\\/g, '/');
    if (/^[A-Za-z]:\//.test(normalized)) return `file:///${encodeURI(normalized)}`;
    if (normalized.startsWith('/')) return `file://${encodeURI(normalized)}`;
    return raw.startsWith('assets/') ? raw : '';
  }

  function providerLabel(row) {
    const provider = text(row?.provider).toLowerCase();
    if (provider === 'nexus') return 'NEXUS MODS';
    if (provider === 'github') return 'GITHUB';
    return text(row?.source_name || row?.provider || 'COMMUNITY').toUpperCase();
  }

  async function openRecommendationUrl(url) {
    if (!url) return;
    try {
      if (bridge.openInAppBrowser) await bridge.openInAppBrowser({ url, purpose: 'nexus' });
      else if (bridge.openExternal) await bridge.openExternal(url);
    } catch (_) {
      if (bridge.openExternal) await bridge.openExternal(url);
    }
  }

  function enhanceRecommendationCard(card) {
    const sourceButton = card.querySelector('[data-recommended-open]');
    const url = text(sourceButton?.dataset.recommendedOpen);
    const row = recommendationByUrl.get(url);
    if (!row || card.dataset.dwsRecommendationEnhanced === '1') return;
    card.dataset.dwsRecommendationEnhanced = '1';
    card.classList.add('dws-recommended-card');

    const imageUrl = externalImageUrl(row.banner_url || row.artwork_url || row.icon_url);
    const media = document.createElement('div');
    media.className = 'dws-recommended-media';
    media.innerHTML = imageUrl
      ? `<img src="${escapeHtml(imageUrl)}" alt="" loading="lazy"><span>${escapeHtml(providerLabel(row))}</span>`
      : `<div class="dws-recommended-fallback">◆</div><span>${escapeHtml(providerLabel(row))}</span>`;
    card.prepend(media);

    const copy = card.querySelector(':scope > div:not(.dws-recommended-media):not(.dws-recommended-actions)');
    if (copy && text(row.description) && !copy.querySelector('.dws-recommended-description')) {
      const description = document.createElement('p');
      description.className = 'dws-recommended-description';
      description.textContent = text(row.description);
      copy.appendChild(description);
    }

    if (sourceButton) {
      sourceButton.textContent = row.provider === 'nexus' ? 'Open Nexus' : 'View Source';
      const actions = document.createElement('div');
      actions.className = 'dws-recommended-actions';
      sourceButton.replaceWith(actions);
      actions.appendChild(sourceButton);
      const downloadUrl = text(row.download_url);
      if (downloadUrl && downloadUrl !== url) {
        const download = document.createElement('button');
        download.className = 'btn primary compact-btn';
        download.type = 'button';
        download.textContent = 'Direct Download';
        download.title = 'Open the curator-provided direct download link';
        download.addEventListener('click', (event) => {
          event.preventDefault(); event.stopPropagation();
          openRecommendationUrl(downloadUrl);
        });
        actions.appendChild(download);
      }
    }
  }

  async function enhanceRecommendations() {
    const cards = [...document.querySelectorAll('.recommended-mod-card:not([data-dws-recommendation-enhanced="1"]):not(:has(.recommended-mod-media))')];
    if (!cards.length) return;
    try { await stateSnapshot(); } catch (_) { return; }
    cards.forEach(enhanceRecommendationCard);
    const activityRow = [...document.querySelectorAll('.settings-row .settings-copy')]
      .find((node) => node.querySelector('strong')?.textContent?.trim() === 'Nexus Activity');
    const copy = activityRow?.querySelector('span');
    if (copy && !copy.dataset.dwsCopyUpdated) {
      copy.dataset.dwsCopyUpdated = '1';
      copy.textContent = 'Opens the Dragonwilds Nexus activity page. Recommended-mod cards may use public page metadata for banner/icon presentation; downloads and ownership remain with the original host.';
    }
  }

  function itemIdentity(row) {
    return text(row?.runtime_path || row?.item_data || row?.persistence_id || row?.id).toLowerCase();
  }

  async function allSpawnerItems(worldId, force = false) {
    if (!worldId) return [];
    if (!force && itemCatalogCache.worldId === worldId && Date.now() - itemCatalogCache.at < 30000) return itemCatalogCache.items;
    const payload = await invoke('server.spawner.catalog', { id: worldId, kind: 'item', query: '', category: '', limit: 2500 });
    itemCatalogCache = { worldId, at: Date.now(), items: payload?.items || [] };
    return itemCatalogCache.items;
  }

  async function resolveItemById(id, worldId = '') {
    const wanted = text(id).toLowerCase();
    if (!wanted) return null;
    if (worldId) {
      try {
        const rows = await allSpawnerItems(worldId);
        const found = rows.find((row) => [row.runtime_path, row.item_data, row.persistence_id, row.id, row.internal_name]
          .some((value) => text(value).toLowerCase() === wanted));
        if (found) return found;
      } catch (_) {}
    }
    try {
      const canonical = await invoke('application.rsdw.items.search', { query: id, limit: 40 });
      const found = (canonical?.items || []).find((row) => [row.item_data, row.persistence_id, row.id, row.internal_name]
        .some((value) => text(value).toLowerCase() === wanted));
      if (found) return found;
    } catch (_) {}
    try {
      const custom = await invoke('application.custom_items.list', {});
      return (custom?.items || []).find((row) => [row.persistence_id, row.runtime_path, row.internal_name]
        .some((value) => text(value).toLowerCase() === wanted)) || null;
    } catch (_) {
      return null;
    }
  }

  function itemDetailMarkup(row, compact = false) {
    if (!row) return '<div class="dws-item-detail-empty">Item metadata is unavailable.</div>';
    const image = externalImageUrl(row.icon_path || row.icon_data || row.icon_ref || row.icon);
    const name = text(row.display_name || row.name || row.internal_name || 'Item');
    const description = text(row.description);
    const stats = [
      ['Category', row.category || row.raw_category],
      ['Internal', row.internal_name || row.item_name || row.summon_name],
      ['Persistence ID', row.persistence_id || row.item_data || row.id],
      ['Stack', row.max_stack],
      ['Weight', row.weight],
      ['Equipment', row.equipment],
      ['Power', row.power_level],
      ['Durability', row.base_durability],
      ['Source', row.custom ? 'Server / mod manifest' : row.source],
    ].filter(([, value]) => value !== undefined && value !== null && text(value));
    return `<div class="dws-item-detail ${compact ? 'compact' : ''}">
      <div class="dws-item-detail-art">${image ? `<img src="${escapeHtml(image)}" alt="" loading="lazy">` : '<span>◆</span>'}</div>
      <div class="dws-item-detail-copy"><div class="dws-item-detail-head"><div><small>${escapeHtml(row.custom ? 'MODDED ITEM' : 'RSDW CANONICAL ITEM')}</small><strong>${escapeHtml(name)}</strong></div>${row.custom ? '<b class="dws-item-origin custom">CUSTOM</b>' : '<b class="dws-item-origin">RSDW</b>'}</div>
      ${description ? `<p>${escapeHtml(description)}</p>` : ''}
      <dl>${stats.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}</dl>
      ${text(row.runtime_path) ? `<code>${escapeHtml(row.runtime_path)}</code>` : ''}</div>
    </div>`;
  }

  function closeItemInspector() {
    document.querySelector('.dws-item-inspector-backdrop')?.remove();
  }

  function showItemInspector(row) {
    closeItemInspector();
    const backdrop = document.createElement('div');
    backdrop.className = 'dws-item-inspector-backdrop';
    backdrop.innerHTML = `<section class="dws-item-inspector panel"><header><div><div class="eyebrow">ITEM DETAILS</div><h2>${escapeHtml(row?.display_name || row?.name || 'Item')}</h2></div><button class="btn ghost dws-item-inspector-close" type="button">Close</button></header>${itemDetailMarkup(row)}</section>`;
    backdrop.addEventListener('click', (event) => { if (event.target === backdrop) closeItemInspector(); });
    backdrop.querySelector('.dws-item-inspector-close')?.addEventListener('click', closeItemInspector);
    document.body.appendChild(backdrop);
  }

  async function enhanceSelectedSpawnerItem() {
    const card = document.querySelector('.spawner-page .selected-spawn-card');
    if (!card || !document.querySelector('.spawner-page [data-spawner-kind="item"].active')) return;
    const path = text(card.querySelector('code')?.textContent);
    if (!path || path.startsWith('Choose an entry')) return;
    if (card.dataset.dwsItemDetail === path) return;
    card.dataset.dwsItemDetail = path;
    try {
      const state = await stateSnapshot();
      const row = await resolveItemById(path, activeServerId(state));
      if (!row || card.dataset.dwsItemDetail !== path) return;
      card.querySelector('.dws-selected-item-detail')?.remove();
      const detail = document.createElement('div');
      detail.className = 'dws-selected-item-detail';
      detail.innerHTML = itemDetailMarkup(row, true);
      card.appendChild(detail);
    } catch (_) {}
  }

  function attachSpawnerInspectors() {
    document.querySelectorAll('.spawner-page [data-spawn-path][draggable="true"]:not([data-dws-inspector-ready])').forEach((node) => {
      node.dataset.dwsInspectorReady = '1';
      node.title = `${node.title || text(node.dataset.spawnName)} · Right-click for full item details`;
      node.addEventListener('contextmenu', async (event) => {
        event.preventDefault(); event.stopPropagation();
        try {
          const state = await stateSnapshot();
          const row = await resolveItemById(node.dataset.spawnPath, activeServerId(state));
          if (row) showItemInspector(row);
        } catch (_) {}
      });
    });
  }

  async function enrichNativeContextMenu() {
    const target = lastNativeContextTarget;
    const menu = document.querySelector('#native-item-context-menu');
    if (!target || !menu || menu.hidden) return;
    const itemId = text(target.dataset.itemData);
    if (!itemId) return;
    let detail = menu.querySelector('.dws-native-context-detail');
    if (!detail) {
      detail = document.createElement('div');
      detail.className = 'dws-native-context-detail';
      menu.prepend(detail);
    }
    detail.innerHTML = '<small>Loading item metadata…</small>';
    const row = await resolveItemById(itemId);
    if (lastNativeContextTarget !== target || menu.hidden) return;
    detail.innerHTML = itemDetailMarkup(row || {
      name: target.dataset.itemName || itemId,
      item_data: itemId,
      max_stack: target.dataset.itemCount,
      equipment: target.dataset.itemEquipment,
      custom: target.dataset.itemCustom === '1',
    }, true);
  }

  document.addEventListener('contextmenu', (event) => {
    const target = event.target.closest?.('[data-native-catalog-slot][data-item-data]:not([data-item-data=""]), [data-native-item-slot][data-item-data]:not([data-item-data=""])');
    if (!target) return;
    lastNativeContextTarget = target;
    setTimeout(() => enrichNativeContextMenu().catch(() => {}), 0);
  }, true);

  function consoleEntryMarkup(row) {
    const source = text(row.source || 'server').toLowerCase();
    const level = text(row.level || 'info').toLowerCase();
    const when = new Date(Number(row.ts || 0) * 1000);
    const timeLabel = Number.isFinite(when.getTime()) ? when.toLocaleTimeString() : '—';
    return `<div class="dws-console-row source-${escapeHtml(source)} level-${escapeHtml(level)}"><time>${escapeHtml(timeLabel)}</time><b>${escapeHtml(source.toUpperCase())}</b><span>${escapeHtml(row.message || '')}</span></div>`;
  }

  function renderUnifiedConsole(payload) {
    lastConsolePayload = payload;
    let host = document.querySelector('#dws-unified-console');
    const workspace = document.querySelector('.console-workspace');
    if (!workspace) return;
    if (!host) {
      host = document.createElement('section');
      host.id = 'dws-unified-console';
      host.className = 'panel dws-unified-console';
      const intro = workspace.querySelector('.spawner-intro');
      (intro || workspace.firstElementChild)?.insertAdjacentElement('afterend', host);
      [...workspace.querySelectorAll('.panel')].find((panel) => panel.querySelector('h2')?.textContent?.trim() === 'Console activity')?.classList.add('dws-legacy-console-activity');
    }
    const rows = (payload?.entries || []).filter((row) => consoleFilter === 'all' || row.source === consoleFilter);
    const counts = payload?.counts || {};
    const body = host.querySelector('.dws-unified-console-body');
    const pinned = !body || body.scrollHeight - body.scrollTop - body.clientHeight < 80;
    host.innerHTML = `<div class="panel-header dws-unified-console-head"><div><h2>Unified Console</h2><span class="panel-subtitle">Game CMD/stdout, UE4SS, dedicated-server events, and World Sync traffic in one stream.</span></div><div class="dws-console-controls"><button class="btn ghost compact-btn" data-dws-console-pause>${consolePaused ? 'Resume' : 'Pause'}</button></div></div>
      <div class="dws-console-filters"><button class="${consoleFilter === 'all' ? 'active' : ''}" data-dws-console-filter="all">ALL <b>${number(Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0), '0')}</b></button><button class="${consoleFilter === 'game' ? 'active' : ''}" data-dws-console-filter="game">GAME <b>${number(counts.game || 0, '0')}</b></button><button class="${consoleFilter === 'ue4ss' ? 'active' : ''}" data-dws-console-filter="ue4ss">UE4SS <b>${number(counts.ue4ss || 0, '0')}</b></button><button class="${consoleFilter === 'runeschema' ? 'active' : ''}" data-dws-console-filter="runeschema">RUNESCHEMA <b>${number(counts.runeschema || 0, '0')}</b></button><button class="${consoleFilter === 'server' ? 'active' : ''}" data-dws-console-filter="server">SERVER <b>${number(counts.server || 0, '0')}</b></button><button class="${consoleFilter === 'sync' ? 'active' : ''}" data-dws-console-filter="sync">SYNC <b>${number(counts.sync || 0, '0')}</b></button></div>
      <div class="dws-unified-console-body">${rows.length ? rows.map(consoleEntryMarkup).join('') : '<div class="empty-state compact">No activity has been recorded for this session yet.</div>'}</div>
      <footer class="dws-console-log-footer"><div><small>CURRENT SESSION LOG</small><code title="${escapeHtml(payload?.current_log || '')}">${escapeHtml(payload?.current_log || 'Log path unavailable')}</code></div>${payload?.ue4ss_log ? `<div><small>UE4SS LOG</small><code title="${escapeHtml(payload.ue4ss_log)}">${escapeHtml(payload.ue4ss_log)}</code></div>` : (payload?.previous_log ? `<div><small>PREVIOUS SESSION BACKUP</small><code title="${escapeHtml(payload.previous_log)}">${escapeHtml(payload.previous_log)}</code></div>` : '')}</footer>`;
    const nextBody = host.querySelector('.dws-unified-console-body');
    if (pinned && nextBody) nextBody.scrollTop = nextBody.scrollHeight;
    host.querySelector('[data-dws-console-pause]')?.addEventListener('click', () => { consolePaused = !consolePaused; renderUnifiedConsole(lastConsolePayload || payload); });
    host.querySelectorAll('[data-dws-console-filter]').forEach((button) => button.addEventListener('click', () => { consoleFilter = button.dataset.dwsConsoleFilter || 'all'; renderUnifiedConsole(lastConsolePayload || payload); }));
  }

  async function refreshUnifiedConsole() {
    if (consolePaused || consoleRequestBusy || !document.querySelector('.console-workspace')) return;
    consoleRequestBusy = true;
    try {
      const state = await stateSnapshot(true);
      const id = activeServerId(state);
      if (!id) return;
      const payload = await invoke('server.console.unified', { id, limit: 350 });
      if (document.querySelector('.console-workspace')) renderUnifiedConsole(payload);
    } catch (_) {
      // The additive pane stays quiet if an older service binary is being used.
    } finally {
      consoleRequestBusy = false;
    }
  }

  async function enhance() {
    await enhanceRecommendations();
    attachSpawnerInspectors();
    await enhanceSelectedSpawnerItem();
    if (document.querySelector('.console-workspace') && !consolePaused) refreshUnifiedConsole();
  }

  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      enhance().catch(() => {});
    });
  };

  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  setInterval(() => {
    if (document.querySelector('.console-workspace')) refreshUnifiedConsole();
    if (document.querySelector('.recommended-mod-card:not([data-dws-recommendation-enhanced="1"])')) schedule();
  }, 2200);
  schedule();
})();
