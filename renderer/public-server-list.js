/* Sync Public World Directory workspace for Dragonwilds Sync desktop.
   Discovery-only: this consumes authenticated launcher heartbeats and never
   imports admin credentials, World passwords, or authority. */
(() => {
  const PAGE_LINK = 'https://gh0sted5456-us.github.io/Dragonwilds-Sync-Web/servers.html';
  const API_URL = 'https://dragonwilds-sync-directory.dragonwilds.workers.dev/api/v1/worlds';
  const VIEW_KEY = 'dragonwilds-sync-public-server-list-view';
  const REFRESH_MS = 30000;
  const PAGE_SIZE = 50;

  let active = false;
  let rows = [];
  let lastLoadedAt = 0;
  let refreshTimer = null;
  let currentPage = 1;

  const text = (value, fallback = '') => {
    const valueText = value == null ? '' : String(value).trim();
    return valueText || fallback;
  };
  const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const list = (value, max = 12) => Array.isArray(value) ? value.map((item) => text(item)).filter(Boolean).slice(0, max) : [];
  const make = (tag, className = '', value = '') => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== '') node.textContent = value;
    return node;
  };
  const panel = () => document.querySelector('.dws-public-server-panel');
  const withinPanel = (selector) => panel()?.querySelector(selector) || null;

  function resolveFeed(raw) {
    const value = text(raw);
    if (!value) throw new Error('The Sync Public World Directory link is unavailable.');
    let url;
    try { url = new URL(value); } catch (_) { throw new Error('The Sync Public World Directory link is not a valid URL.'); }
    if (url.protocol !== 'https:') throw new Error('Sync Public World Directory links must use HTTPS.');

    const host = url.hostname.toLowerCase();
    const path = url.pathname.toLowerCase().replace(/\/$/, '');
    if (host === 'gh0sted5456-us.github.io' && path.startsWith('/dragonwilds-sync')) return API_URL;
    if (host === 'dragonwilds-sync-directory.dragonwilds.workers.dev') {
      if (['/api/v1/worlds', '/worlds', '/api/worlds', '/manifest'].includes(path)) return url.toString();
      url.pathname = '/api/v1/worlds'; url.search = ''; url.hash = '';
      return url.toString();
    }
    if (host.endsWith('.workers.dev')) {
      if (!['/api/v1/worlds', '/worlds', '/api/worlds', '/manifest'].includes(path)) url.pathname = '/api/v1/worlds';
      url.search = ''; url.hash = '';
      return url.toString();
    }
    throw new Error('Use the Dragonwilds Sync Public Server Directory webpage link or an approved workers.dev directory feed.');
  }

  function normalizeWorld(raw) {
    const players = raw && typeof raw.players === 'object' && raw.players ? raw.players : {};
    const connect = raw && typeof raw.public_connect === 'object' && raw.public_connect ? raw.public_connect : null;
    const id = text(raw?.world_id ?? raw?.source_world_id, 'sync-world');
    const isSync = raw?.is_sync_world === true
      || text(raw?.directory_source).toLowerCase() === 'dragonwilds-sync'
      || !id.toLowerCase().startsWith('public-');
    const syncBroadcasting = raw?.sync_broadcasting == null
      ? isSync && text(raw?.status, 'offline').toLowerCase() !== 'offline'
      : Boolean(raw.sync_broadcasting);
    const gameActive = raw?.game_active == null
      ? syncBroadcasting && ['online', 'starting', 'maintenance', 'stopping'].includes(text(raw?.status, 'offline').toLowerCase())
      : Boolean(raw.game_active);
    return {
      id,
      name: text(raw?.world_name ?? raw?.name, 'Unnamed World'),
      description: text(raw?.description, raw?.is_sync_world ? 'Dragonwilds Sync World' : 'Public Dragonwilds server'),
      region: text(raw?.country_name ?? raw?.region ?? raw?.country_code, 'Unknown'),
      version: text(raw?.version, 'Unknown'),
      status: text(raw?.status, 'offline').toLowerCase(),
      current: Math.max(0, number(players.current ?? raw?.players_current, 0)),
      max: Math.max(0, number(players.max ?? raw?.players_max, 0)),
      tags: list(raw?.tags, 10), badges: list(raw?.badges, 8),
      source: text(raw?.source_name, isSync ? 'Dragonwilds Sync' : 'Unverified source'),
      isSync,
      syncBroadcasting,
      gameActive,
      broadcastState: text(raw?.broadcast_state, gameActive ? 'sync-and-game' : 'sync-only'),
      host: text(connect?.host ?? raw?.public_connect_host, ''),
      port: number(connect?.port ?? raw?.public_connect_port, 0),
      lastSeen: number(raw?.last_seen, 0),
    };
  }

  const isOnline = (world) => ['online', 'starting', 'maintenance'].includes(world.status);
  const currentView = () => localStorage.getItem(VIEW_KEY) === 'cards' ? 'cards' : 'horizontal';

  function setStatus(message, kind = '') {
    const status = withinPanel('#dws-public-server-status');
    if (!status) return;
    status.className = `dws-public-server-status ${kind}`.trim();
    status.textContent = message;
  }

  function renderRows() {
    const root = panel();
    if (!root) return;
    const results = root.querySelector('#dws-public-server-results');
    const summary = root.querySelector('#dws-public-server-summary');
    const search = text(root.querySelector('#dws-public-server-search')?.value).toLowerCase();
    const searchTerms = search.split(/\s+/).filter(Boolean);
    if (!results || !summary) return;

    const filtered = rows
      .filter((world) => {
        if (!searchTerms.length) return true;
        const searchable = [world.name, world.host, world.port, world.region, world.version, world.source, ...world.tags, ...world.badges].join(' ').toLowerCase();
        return searchTerms.every((term) => searchable.includes(term));
      })
      .sort((a, b) => Number(isOnline(b)) - Number(isOnline(a)) || b.current - a.current || b.lastSeen - a.lastSeen || a.name.localeCompare(b.name));
    const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    currentPage = Math.max(1, Math.min(currentPage, pageCount));
    const pageStart = (currentPage - 1) * PAGE_SIZE;
    const visible = filtered.slice(pageStart, pageStart + PAGE_SIZE);

    summary.replaceChildren();
    const counts = [
      ['Sync Broadcasts', rows.length],
      ['Dragonwilds Active', rows.filter((world) => world.gameActive).length],
      ['Sync Only', rows.filter((world) => !world.gameActive).length],
      ['Showing', filtered.length],
    ];
    counts.forEach(([label, value]) => {
      const item = make('span');
      item.append(document.createTextNode(`${label} `), make('b', '', String(value)));
      summary.appendChild(item);
    });

    const view = currentView();
    results.className = `dws-public-server-results ${view === 'horizontal' ? 'horizontal' : ''}`.trim();
    root.querySelectorAll('[data-dws-public-view]').forEach((button) => button.classList.toggle('active', button.dataset.dwsPublicView === view));
    results.replaceChildren();
    if (!visible.length) {
      results.appendChild(make('div', 'dws-public-empty', rows.length ? 'No Sync Worlds match this search.' : 'No Dragonwilds Sync Worlds are broadcasting right now.'));
      renderPagination(0);
      return;
    }

    const fragment = document.createDocumentFragment();
    visible.forEach((world) => {
      const card = make('article', 'dws-public-server-card');
      const identity = make('div');
      const head = make('div', 'dws-public-server-card-head');
      const title = make('div');
      title.append(make('h3', '', world.name), make('small', '', `${world.source} · ${world.id}`));
      head.append(title, make('span', `dws-public-type sync ${world.gameActive ? 'game-active' : 'sync-only'}`, world.gameActive ? 'SYNC + GAME ACTIVE' : 'SYNC ONLY'));
      identity.append(head, make('div', 'dws-public-server-description', world.description));

      const metrics = make('div', 'dws-public-server-metrics');
      metrics.append(
        make('span', '', world.gameActive ? 'DRAGONWILDS ACTIVE' : 'SYNC BROADCAST'),
        make('span', '', world.region),
        make('span', '', `${world.current} / ${world.max || '—'} players`),
        make('span', '', world.version),
      );

      const detail = make('div');
      const tags = make('div', 'dws-public-server-tags');
      (world.tags.length ? world.tags : world.badges).slice(0, 6).forEach((tag) => tags.appendChild(make('span', '', tag)));
      detail.appendChild(tags);
      detail.appendChild(make('div', 'dws-public-server-route', world.host
        ? `Public route: ${world.host}${world.port ? `:${world.port}` : ''}`
        : world.isSync ? 'Sync metadata published; public route not exposed.' : 'Public source does not expose a direct route.'));
      if (world.isSync && world.syncBroadcasting) {
        const connect = make('button', 'btn primary', 'Connect');
        connect.type = 'button';
        connect.addEventListener('click', () => {
          const openJoin = window.__DWSYNC_OPEN_DIRECTORY_JOIN__;
          if (typeof openJoin !== 'function') {
            setStatus('The verified connection dialog is not ready yet. Reopen this tab and try again.', 'error');
            return;
          }
          openJoin({ directoryUrl: API_URL.replace(/\/api\/v1\/worlds$/, ''), worldId: world.id });
        });
        detail.appendChild(connect);
      }
      card.append(identity, metrics, detail);
      fragment.appendChild(card);
    });
    results.appendChild(fragment);
    results.scrollTop = 0;
    renderPagination(filtered.length);
  }

  function renderPagination(total) {
    const pagination = withinPanel('#dws-public-server-pagination');
    if (!pagination) return;
    pagination.replaceChildren();
    pagination.hidden = total <= PAGE_SIZE;
    if (pagination.hidden) return;

    const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const button = (label, page, disabled = false) => {
      const control = make('button', 'btn secondary', label);
      control.type = 'button';
      control.disabled = disabled;
      control.addEventListener('click', () => {
        if (control.disabled) return;
        currentPage = page;
        renderRows();
      });
      return control;
    };
    const first = (currentPage - 1) * PAGE_SIZE + 1;
    const last = Math.min(total, currentPage * PAGE_SIZE);
    pagination.append(
      button('← Previous', currentPage - 1, currentPage === 1),
      make('span', '', `Showing ${first}–${last} of ${total} · Page ${currentPage} of ${pageCount}`),
      button('Next →', currentPage + 1, currentPage === pageCount),
    );
  }

  async function loadDirectory({ force = false } = {}) {
    const root = panel();
    if (!root) return;

    let endpoint;
    try { endpoint = resolveFeed(PAGE_LINK); }
    catch (error) { setStatus(error.message || String(error), 'error'); return; }

    if (!force && rows.length && Date.now() - lastLoadedAt < 5000) { renderRows(); return; }
    setStatus('Loading public servers…');
    try {
      const response = await fetch(endpoint, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (!response.ok) throw new Error(`Live directory HTTP ${response.status}`);
      const directorySource = 'live directory';
      const payload = await response.json();
      const source = Array.isArray(payload?.worlds) ? payload.worlds : Array.isArray(payload) ? payload : [];
      const unique = new Map();
      source.map(normalizeWorld)
        .filter((world) => world.isSync && world.syncBroadcasting)
        .forEach((world) => unique.set(world.id, world));
      rows = [...unique.values()];
      currentPage = 1;
      lastLoadedAt = Date.now();
      setStatus(`${rows.length} Sync World${rows.length === 1 ? '' : 's'} broadcasting from ${directorySource}`, 'ok');
      const endpointNode = root.querySelector('#dws-public-server-endpoint');
      if (endpointNode) endpointNode.textContent = endpoint;
      renderRows();
    } catch (error) {
      setStatus(`Sync Public World Directory unavailable: ${error.message || error}`, 'error');
      renderRows();
    }
  }

  function stopRefreshTimer() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = null;
  }

  function buildPanel() {
    const root = make('section', 'dws-public-server-panel');
    root.innerHTML = `
      <div class="dws-public-server-head">
        <div><div class="eyebrow">Authenticated launcher heartbeats</div><h2>Sync Public World Directory</h2><p>Only Worlds actively broadcasting through Dragonwilds Sync appear here. Connect hands a World identifier to the verified login and synchronization dialog; passwords are never carried in the link.</p></div>
        <span class="dws-public-server-status" id="dws-public-server-status">Not loaded</span>
      </div>
      <div class="dws-public-server-controls">
        <button class="btn primary" id="dws-public-server-load" type="button">Refresh Sync Worlds</button>
        <label class="dws-public-search-wrap"><small>Search broadcasting Worlds</small><input class="field" id="dws-public-server-search" type="search" placeholder="World name, IP address, region, build…" /></label>
        <div class="dws-public-view-toggle" role="group" aria-label="Sync Public World Directory view"><button type="button" data-dws-public-view="cards">▦ Placards</button><button type="button" data-dws-public-view="horizontal">☰ Horizontal</button></div>
      </div>
      <div class="dws-public-server-summary" id="dws-public-server-summary"></div>
      <div class="dws-public-server-results" id="dws-public-server-results"><div class="dws-public-empty">Loading the Sync Public World Directory…</div></div>
      <nav class="dws-public-server-pagination" id="dws-public-server-pagination" aria-label="Sync World result pages" hidden></nav>
      <div class="muted-small" style="margin-top:9px">Resolved read-only endpoint: <span id="dws-public-server-endpoint">—</span> · refreshes every 30 seconds while this tab is open.</div>`;

    root.querySelector('#dws-public-server-load')?.addEventListener('click', () => loadDirectory({ force: true }));
    root.querySelector('#dws-public-server-search')?.addEventListener('input', () => { currentPage = 1; renderRows(); });
    root.querySelectorAll('[data-dws-public-view]').forEach((button) => button.addEventListener('click', () => {
      localStorage.setItem(VIEW_KEY, button.dataset.dwsPublicView === 'cards' ? 'cards' : 'horizontal');
      renderRows();
    }));
    return root;
  }

  function ensure() {
    const mount = document.querySelector('#dws-public-server-list-mount');
    if (!mount) { active = false; stopRefreshTimer(); return; }
    if (!mount.querySelector('.dws-public-server-panel')) mount.appendChild(buildPanel());
    active = true;
    if (!rows.length) loadDirectory({ force: true });
    else renderRows();
    if (!refreshTimer) refreshTimer = setInterval(() => { if (active) loadDirectory({ force: true }); }, REFRESH_MS);
  }

  const observer = new MutationObserver((mutations) => {
    const relevant = mutations.some((mutation) => {
      const target = mutation.target;
      return !(target instanceof Element && target.closest('.dws-public-server-panel'));
    });
    if (relevant) ensure();
  });
  observer.observe(document.querySelector('#app') || document.body, { childList: true, subtree: true });
  ensure();
})();
