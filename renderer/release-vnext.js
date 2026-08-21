(() => {
  'use strict';

  const api = window.dragonwilds;
  const HELP_MANIFEST_URL = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/help/manifest.json';
  const HELP_CACHE = 'dragonwilds-sync-help-v1';
  let stateCache = null;
  let stateFetchedAt = 0;
  let declaredMode = false;
  let declaredRows = [];
  let declaredLoading = false;
  let declaredError = '';
  let declaredView = 'cards';
  let helpBusy = false;

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const safeUrl = (value) => {
    try {
      const url = new URL(String(value || ''), HELP_MANIFEST_URL);
      return url.protocol === 'https:' && ['raw.githubusercontent.com', 'github.com'].includes(url.hostname) ? url.href : '';
    } catch (_) { return ''; }
  };

  async function appState(force = false) {
    if (!api?.invoke) return stateCache || {};
    if (!force && stateCache && Date.now() - stateFetchedAt < 2500) return stateCache;
    try {
      stateCache = await api.invoke('state.get', {});
      stateFetchedAt = Date.now();
    } catch (_) {}
    return stateCache || {};
  }

  function allWorlds(state) {
    const rows = [
      ...(state?.client?.worlds || []),
      ...(state?.client?.discovered_worlds || []),
      ...(state?.client?.directory_worlds || []),
      ...(state?.client?.private_worlds || []),
      ...(state?.server_profiles || []),
    ];
    const map = new Map();
    rows.forEach((row) => {
      if (!row || !row.id) return;
      const key = String(row.id);
      map.set(key, {...(map.get(key) || {}), ...row});
    });
    return map;
  }

  function badgeLabel(value) {
    if (typeof value === 'string' || typeof value === 'number') return String(value).trim();
    if (!value || typeof value !== 'object') return '';
    return String(value.label || value.name || value.title || value.id || '').trim();
  }

  function profileBadges(world) {
    const presentation = world?.presentation || world?.metadata_cache?.world_metadata || {};
    const candidates = [
      ...(Array.isArray(world?.badges) ? world.badges : []),
      ...(Array.isArray(world?.profile_badges) ? world.profile_badges : []),
      ...(Array.isArray(presentation?.badges) ? presentation.badges : []),
      ...(Array.isArray(presentation?.profile_badges) ? presentation.profile_badges : []),
      ...(Array.isArray(presentation?.mod_badges) ? presentation.mod_badges : []),
    ];
    const labels = candidates.map(badgeLabel).filter(Boolean);
    if (world?.auto_ue4ss) labels.push('UE4SS');
    if (world?.auto_runeschema) labels.push('RUNESCHEMA');
    return [...new Set(labels.map((label) => label.toUpperCase()))].slice(0, 12);
  }

  function enhanceProfileBadges(root = document) {
    void appState().then((state) => {
      const worlds = allWorlds(state);
      root.querySelectorAll('[data-world-id]').forEach((node) => {
        const world = worlds.get(String(node.dataset.worldId || ''));
        if (!world) return;
        const labels = profileBadges(world);
        node.classList.toggle('dws-has-profile-badges', labels.length > 0);
        node.dataset.profileBadgeCount = String(labels.length);
        let strip = node.querySelector(':scope .dws-profile-badges');
        if (!labels.length) {
          strip?.remove();
          return;
        }
        if (!strip) {
          strip = document.createElement('div');
          strip.className = 'dws-profile-badges';
          const anchor = node.classList.contains('world-list-row')
            ? (node.querySelector('.world-list-title') || node.querySelector('.world-list-main'))
            : (node.querySelector('.badges') || node.querySelector('.world-card-body'));
          anchor?.appendChild(strip);
        }
        if (strip) strip.innerHTML = labels.map((label) => `<span class="dws-profile-badge">${esc(label)}</span>`).join('');
      });
    });
  }

  function declaredBase(state) {
    const status = state?.application?.world_directory_host_status || {};
    const cfg = state?.application?.world_directory_host || {};
    const direct = String(status.local_url || '').replace(/\/$/, '');
    if (direct) return direct;
    const port = Number(cfg.port || 27080);
    return `http://127.0.0.1:${port}`;
  }

  function isDeclared(row) {
    return Boolean(row && row.directory_verified && row.fingerprint_claimed && Number(row.last_seen || 0) > 0);
  }

  async function fetchDeclared(force = false) {
    if (declaredLoading) return declaredRows;
    if (!force && declaredRows.length) return declaredRows;
    declaredLoading = true;
    declaredError = '';
    try {
      const state = await appState(true);
      const status = state?.application?.world_directory_host_status || {};
      if (!status.serving) {
        declaredRows = [];
        declaredError = 'Start WebHost to receive declared World heartbeats on this machine.';
        return declaredRows;
      }
      const base = declaredBase(state);
      const firstResponse = await fetch(`${base}/api/v1/worlds?active=sync&page=1&sort=featured`, {cache:'no-store'});
      if (!firstResponse.ok) throw new Error(`WebHost returned ${firstResponse.status}`);
      const first = await firstResponse.json();
      const pages = Math.max(1, Math.min(25, Number(first.page_count || 1)));
      const payloads = [first];
      for (let page = 2; page <= pages; page += 1) {
        const response = await fetch(`${base}/api/v1/worlds?active=sync&page=${page}&sort=featured`, {cache:'no-store'});
        if (!response.ok) break;
        payloads.push(await response.json());
      }
      const seen = new Set();
      declaredRows = payloads.flatMap((payload) => payload.worlds || []).filter(isDeclared).filter((row) => {
        const key = String(row.fingerprint_claimed || row.id || '');
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      }).sort((a,b) => Number(b.last_seen || 0) - Number(a.last_seen || 0));
      return declaredRows;
    } catch (error) {
      declaredRows = [];
      declaredError = error.message || String(error);
      return declaredRows;
    } finally {
      declaredLoading = false;
    }
  }

  function dataImage(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    if (/^data:image\//i.test(text) || /^https:\/\//i.test(text) || /^http:\/\/127\.0\.0\.1/i.test(text)) return text;
    return '';
  }

  function declaredBadges(row) {
    const labels = [
      'SYNC', 'DECLARED',
      ...(Array.isArray(row.badges) ? row.badges.map(badgeLabel) : []),
      ...(Array.isArray(row.mod_badges) ? row.mod_badges.map(badgeLabel) : []),
    ].filter(Boolean);
    return [...new Set(labels.map((value) => String(value).toUpperCase()))].slice(0, 10)
      .map((label) => `<span class="dws-profile-badge">${esc(label)}</span>`).join('');
  }

  function declaredCard(row) {
    const title = row.world_name || row.name || 'Declared World';
    const icon = dataImage(row.icon_b64);
    const banner = dataImage(row.banner_b64);
    const players = Number(row.players || row.player_count || 0);
    const maxPlayers = Number(row.max_players || 0);
    const age = Math.max(0, Math.round(Date.now()/1000 - Number(row.last_seen || 0)));
    const route = row.external_ip || row.internal_ip || '';
    return `<article class="world-card dws-declared-card" data-declared-fingerprint="${esc(row.fingerprint_claimed || '')}">
      <div class="world-mode-banner dedicated">DECLARED · SYNC</div>
      ${banner ? `<img class="world-card-banner" src="${esc(banner)}" alt=""/>` : '<div class="world-card-banner-fallback"></div>'}
      <div class="world-card-body">
        ${icon ? `<img class="world-icon" src="${esc(icon)}" alt=""/>` : `<div class="world-icon fallback">${esc(String(title).slice(0,2).toUpperCase())}</div>`}
        <div class="card-topline"><div class="card-title"><h3>${esc(title)}</h3><small>${esc(route)}${row.game_port ? `:${Number(row.game_port)}` : ''}</small></div><span class="status-pill online">LIVE</span></div>
        <div class="card-description">${esc(row.description || 'This World is actively declaring its Dragonwilds Sync heartbeat to this WebHost.')}</div>
        <div class="dws-profile-badges">${declaredBadges(row)}</div>
        <div class="card-footer"><div class="card-metrics"><span>${players}${maxPlayers ? ` / ${maxPlayers}` : ''} players</span><span>${row.ping_ms != null ? `${Math.round(Number(row.ping_ms))} ms` : 'Sync verified'}</span><span>${age < 60 ? `${age}s ago` : `${Math.round(age/60)}m ago`}</span></div></div>
      </div>
      <div class="placard-actions integrated"><button class="btn primary compact-btn" data-declared-details="${esc(row.id || '')}">Web Details</button></div>
    </article>`;
  }

  function declaredRow(row) {
    const title = row.world_name || row.name || 'Declared World';
    const icon = dataImage(row.icon_b64);
    const banner = dataImage(row.banner_b64);
    const route = row.external_ip || row.internal_ip || '';
    return `<article class="world-list-row hosted-list-row dws-declared-row" data-declared-fingerprint="${esc(row.fingerprint_claimed || '')}">
      <div class="world-list-icon">${icon ? `<img src="${esc(icon)}" alt=""/>` : `<span>${esc(String(title).slice(0,2).toUpperCase())}</span>`}</div>
      <div class="world-list-main"><div class="world-list-title"><h3>${esc(title)}</h3><span class="status-pill online">DECLARED</span><div class="dws-profile-badges">${declaredBadges(row)}</div></div><div class="world-list-meta"><span>Sync-capable heartbeat</span><span>${esc(route)}${row.sync_port ? ` · Sync ${Number(row.sync_port)}` : ''}</span><span>${row.players != null ? `${Number(row.players)} players` : 'Live fingerprint verified'}</span></div></div>
      <div class="world-list-banner">${banner ? `<img src="${esc(banner)}" alt=""/>` : ''}</div>
      <div class="world-row-actions"><button class="btn primary compact-btn" data-declared-details="${esc(row.id || '')}">Web Details</button></div>
    </article>`;
  }

  function worldGalleryParts() {
    const tabs = document.querySelector('.world-source-tabs');
    if (!tabs) return null;
    const content = tabs.closest('.content');
    if (!content || !content.querySelector('.world-browser-toolbar')) return null;
    return {tabs, content};
  }

  function setOriginalWorldVisibility(content, hidden) {
    content.querySelectorAll('.world-browser-toolbar,.world-selector-filters,.manifest-workspace,.advanced-strip,.world-pagination').forEach((node) => {
      if (node.id === 'dws-declared-panel') return;
      node.classList.toggle('dws-declared-hidden', hidden);
    });
    content.querySelectorAll(':scope > .world-grid,:scope > .world-list').forEach((node) => node.classList.toggle('dws-declared-hidden', hidden));
  }

  async function renderDeclaredPanel(force = false) {
    const parts = worldGalleryParts();
    if (!parts || !declaredMode) return;
    const {tabs, content} = parts;
    setOriginalWorldVisibility(content, true);
    let panel = content.querySelector('#dws-declared-panel');
    if (!panel) {
      panel = document.createElement('section');
      panel.id = 'dws-declared-panel';
      tabs.insertAdjacentElement('afterend', panel);
    }
    panel.innerHTML = '<div class="dws-declared-loading"><div class="spinner"></div><strong>Reading live WebHost heartbeats…</strong></div>';
    await fetchDeclared(force);
    if (!declaredMode || !document.body.contains(panel)) return;
    const rows = declaredRows;
    panel.innerHTML = `<div class="dws-declared-toolbar"><div><div class="eyebrow">Heartbeat projection</div><h2>Declared Worlds</h2><p>Only currently live, fingerprint-verified Dragonwilds Sync heartbeats received by this WebHost appear here.</p></div><div class="header-actions"><span class="status-pill ${rows.length ? 'online' : 'unknown'}">${rows.length} DECLARED</span><div class="world-view-toggle"><button class="btn ${declaredView==='cards'?'primary':'ghost'} compact-btn" data-declared-view="cards">▦</button><button class="btn ${declaredView==='list'?'primary':'ghost'} compact-btn" data-declared-view="list">☰</button></div><button class="btn ghost" data-declared-refresh>↻ Refresh</button></div></div>${declaredError ? `<div class="warning-box"><strong>Declared feed unavailable</strong><br/>${esc(declaredError)}</div>` : ''}<div class="${declaredView==='cards'?'world-grid':'world-list'} dws-declared-results">${rows.length ? rows.map((row) => declaredView==='cards' ? declaredCard(row) : declaredRow(row)).join('') : '<div class="empty-state"><strong>No active declarations.</strong><span>A Sync-capable World appears here after its heartbeat reaches this WebHost and its fingerprint probe verifies.</span></div>'}</div>`;
    panel.querySelector('[data-declared-refresh]')?.addEventListener('click', () => renderDeclaredPanel(true));
    panel.querySelectorAll('[data-declared-view]').forEach((button) => button.addEventListener('click', () => {declaredView = button.dataset.declaredView === 'list' ? 'list' : 'cards'; renderDeclaredPanel(false);}));
    panel.querySelectorAll('[data-declared-details]').forEach((button) => button.addEventListener('click', async () => {
      const state = await appState();
      const base = declaredBase(state);
      const id = button.dataset.declaredDetails;
      if (id && api?.openExternal) api.openExternal(`${base}/servers/${encodeURIComponent(id)}`);
    }));
  }

  function enhanceDeclaredTab() {
    const parts = worldGalleryParts();
    if (!parts) return;
    const {tabs, content} = parts;
    let button = tabs.querySelector('[data-vnext-world-tab="declared"]');
    if (!button) {
      button = document.createElement('button');
      button.dataset.vnextWorldTab = 'declared';
      button.innerHTML = '<strong>Declared</strong><span>Live Sync heartbeats to this host</span>';
      tabs.appendChild(button);
      button.addEventListener('click', (event) => {
        event.preventDefault(); event.stopPropagation();
        declaredMode = true;
        tabs.querySelectorAll('button').forEach((node) => node.classList.toggle('active', node === button));
        renderDeclaredPanel(true);
      });
    }
    button.classList.toggle('active', declaredMode);
    if (!declaredMode) {
      content.querySelector('#dws-declared-panel')?.remove();
      setOriginalWorldVisibility(content, false);
    }
  }

  async function cachedFetch(url, force = false) {
    const resolved = safeUrl(url);
    if (!resolved) throw new Error('Help content URL was rejected.');
    if (!('caches' in window)) return fetch(resolved, {cache: force ? 'reload' : 'default'});
    const cache = await caches.open(HELP_CACHE);
    if (!force) {
      const saved = await cache.match(resolved);
      if (saved) return saved.clone();
    }
    const response = await fetch(resolved, {cache:'no-store'});
    if (!response.ok) throw new Error(`Help source returned ${response.status}.`);
    await cache.put(resolved, response.clone());
    return response;
  }

  function inlineMarkdown(text) {
    let value = esc(text);
    value = value.replace(/`([^`]+)`/g, '<code>$1</code>');
    value = value.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    value = value.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    value = value.replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g, (_m, label, href) => `<a href="#" data-help-link="${esc(href)}">${label}</a>`);
    return value;
  }

  function markdown(text) {
    const lines = String(text || '').replace(/\r/g, '').split('\n');
    const out = [];
    let listOpen = false;
    const closeList = () => { if (listOpen) {out.push('</ul>'); listOpen = false;} };
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (!line.trim()) { closeList(); continue; }
      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) { closeList(); out.push(`<h${heading[1].length}>${inlineMarkdown(heading[2])}</h${heading[1].length}>`); continue; }
      const bullet = line.match(/^[-*]\s+(.+)$/);
      if (bullet) { if (!listOpen) {out.push('<ul>'); listOpen = true;} out.push(`<li>${inlineMarkdown(bullet[1])}</li>`); continue; }
      closeList();
      if (/^>\s?/.test(line)) out.push(`<blockquote>${inlineMarkdown(line.replace(/^>\s?/, ''))}</blockquote>`);
      else out.push(`<p>${inlineMarkdown(line)}</p>`);
    }
    closeList();
    return out.join('');
  }

  async function loadHelpManifest(force = false) {
    const response = await cachedFetch(HELP_MANIFEST_URL, force);
    const manifest = await response.json();
    if (!manifest || manifest.schema !== 'DragonwildsSync.Help.v1' || !Array.isArray(manifest.pages)) throw new Error('Help manifest schema is unsupported.');
    return manifest;
  }

  async function loadHelpPage(page, force = false) {
    const url = new URL(String(page.markdown || ''), HELP_MANIFEST_URL).href;
    const response = await cachedFetch(url, force);
    return response.text();
  }

  async function mountLiveHelp(force = false) {
    const page = document.querySelector('.help-page');
    if (page?.classList.contains('helpy-website-shell')) return;
    if (!page || page.dataset.liveHelpBusy === '1') return;
    page.dataset.liveHelpBusy = '1';
    const header = page.querySelector('.help-page-header');
    let refresh = page.querySelector('#dws-help-refresh');
    if (!refresh && header) {
      refresh = document.createElement('button');
      refresh.className = 'btn ghost';
      refresh.id = 'dws-help-refresh';
      refresh.textContent = '↻ Refresh Help';
      (header.querySelector('.help-search') || header).appendChild(refresh);
      refresh.addEventListener('click', async () => {
        if (helpBusy) return;
        helpBusy = true; refresh.disabled = true; refresh.textContent = 'Refreshing…';
        try { await mountLiveHelp(true); }
        finally { helpBusy = false; refresh.disabled = false; refresh.textContent = '↻ Refresh Help'; }
      });
    }
    try {
      const manifest = await loadHelpManifest(force);
      const pages = manifest.pages.filter((row) => row && row.id && row.title && row.markdown);
      if (!pages.length) throw new Error('Help manifest contains no pages.');
      let selectedId = page.dataset.liveHelpSelected || pages[0].id;
      if (!pages.some((row) => row.id === selectedId)) selectedId = pages[0].id;
      const selected = pages.find((row) => row.id === selectedId);
      const body = await loadHelpPage(selected, force);
      const existing = page.querySelector('.help-layout');
      if (existing) existing.classList.add('dws-builtin-help-fallback');
      let host = page.querySelector('#dws-live-help');
      if (!host) {
        host = document.createElement('section');
        host.id = 'dws-live-help';
        existing?.insertAdjacentElement('beforebegin', host);
      }
      const query = String(page.querySelector('#help-search')?.value || '').trim().toLowerCase();
      const filtered = query ? pages.filter((row) => `${row.title} ${row.summary || ''} ${row.category || ''}`.toLowerCase().includes(query)) : pages;
      host.innerHTML = `<aside class="dws-live-help-nav"><div><div class="eyebrow">Live Help</div><strong>${esc(manifest.title || 'Dragonwilds Sync Help')}</strong><small>Updated ${esc(manifest.updated_at || manifest.version || 'from GitHub')}</small></div>${filtered.map((row) => `<button class="${row.id===selectedId?'active':''}" data-live-help-page="${esc(row.id)}"><strong>${esc(row.title)}</strong><span>${esc(row.summary || row.category || '')}</span></button>`).join('') || '<div class="empty-state compact">No live help page matches this search.</div>'}</aside><article class="dws-live-help-article"><div class="dws-live-help-meta"><span class="status-pill online">GITHUB CACHED</span><span>${esc(selected.category || 'Guide')}</span></div><div class="dws-live-help-markdown">${markdown(body)}</div></article>`;
      host.querySelectorAll('[data-live-help-page]').forEach((button) => button.addEventListener('click', () => {page.dataset.liveHelpSelected = button.dataset.liveHelpPage; page.dataset.liveHelpBusy = ''; mountLiveHelp(false);}));
      host.querySelectorAll('[data-help-link]').forEach((link) => link.addEventListener('click', (event) => {event.preventDefault(); const href = link.dataset.helpLink; if (href && api?.openExternal) api.openExternal(href);}));
      page.dataset.liveHelpSelected = selectedId;
      page.classList.add('dws-live-help-active');
    } catch (error) {
      page.classList.remove('dws-live-help-active');
      const host = page.querySelector('#dws-live-help');
      if (host) host.innerHTML = `<div class="warning-box"><strong>Live Help is using the built-in fallback.</strong><br/>${esc(error.message || error)} The last application-bundled guide remains available offline.</div>`;
      page.querySelector('.help-layout')?.classList.remove('dws-builtin-help-fallback');
    } finally {
      page.dataset.liveHelpBusy = '';
    }
  }

  function enhanceHelpSearch() {
    const input = document.querySelector('.help-page #help-search');
    if (!input || input.dataset.vnextHelpSearch === '1') return;
    input.dataset.vnextHelpSearch = '1';
    let timer = 0;
    input.addEventListener('input', () => {clearTimeout(timer); timer = setTimeout(() => {const page = input.closest('.help-page'); if (page) page.dataset.liveHelpBusy=''; mountLiveHelp(false);}, 180);});
  }

  function enhance() {
    enhanceProfileBadges();
    enhanceDeclaredTab();
    enhanceHelpSearch();
    if (document.querySelector('.help-page')) void mountLiveHelp(false);
  }

  document.addEventListener('click', (event) => {
    const existingTab = event.target.closest('.world-source-tabs button:not([data-vnext-world-tab="declared"])');
    if (existingTab && declaredMode) {
      declaredMode = false;
      declaredRows = [];
    }
  }, true);

  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {scheduled = false; enhance();});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule, {once:true}); else schedule();
  new MutationObserver(schedule).observe(document.documentElement, {childList:true, subtree:true});
})();
