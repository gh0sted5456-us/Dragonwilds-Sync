/* Website-backed Public Server List tab for Dragonwilds Sync desktop.
   This is discovery-only UI. It consumes the same merged Cloudflare response as
   the website and never imports admin credentials, World passwords, or runtime authority. */
(() => {
  const PAGE_LINK = 'https://gh0sted5456-us.github.io/Dragonwilds-Sync/servers.html';
  const API_URL = 'https://dragonwilds-sync-directory.dragonwilds.workers.dev/api/v1/worlds';
  const LINK_KEY = 'dragonwilds-sync-public-server-list-link';
  const VIEW_KEY = 'dragonwilds-sync-public-server-list-view';
  const REFRESH_MS = 30000;

  let active = false;
  let rows = [];
  let lastLoadedAt = 0;
  let refreshTimer = null;

  const byId = (id, root = document) => root.querySelector(`#${id}`);
  const text = (value, fallback = '') => {
    const next = value == null ? '' : String(value).trim();
    return next || fallback;
  };
  const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const list = (value, max = 12) => Array.isArray(value) ? value.map((item) => text(item)).filter(Boolean).slice(0, max) : [];
  const make = (tag, className = '', value = '') => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== '') node.textContent = value;
    return node;
  };

  function resolveFeed(raw) {
    const value = text(raw);
    if (!value) throw new Error('Paste the Public Server Directory webpage link first.');
    let url;
    try { url = new URL(value); } catch (_) { throw new Error('The Public Server List link is not a valid URL.'); }
    if (url.protocol !== 'https:') throw new Error('Public Server List links must use HTTPS.');

    const host = url.hostname.toLowerCase();
    const path = url.pathname.toLowerCase();
    if (host === 'gh0sted5456-us.github.io' && path.startsWith('/dragonwilds-sync')) return API_URL;
    if (host === 'dragonwilds-sync-directory.dragonwilds.workers.dev') {
      if (path === '/api/v1/worlds' || path === '/worlds' || path === '/api/worlds' || path === '/manifest') return url.toString();
      url.pathname = '/api/v1/worlds';
      url.search = '';
      url.hash = '';
      return url.toString();
    }
    if (host.endsWith('.workers.dev')) {
      if (!/\/(?:api\/v1\/worlds|worlds|api\/worlds|manifest)\/?$/i.test(url.pathname)) url.pathname = '/api/v1/worlds';
      url.search = '';
      url.hash = '';
      return url.toString();
    }
    throw new Error('Use the Dragonwilds Sync Public Server Directory webpage link or an approved workers.dev directory feed.');
  }

  function normalizeWorld(raw) {
    const players = raw && typeof raw.players === 'object' && raw.players ? raw.players : {};
    const connect = raw && typeof raw.public_connect === 'object' && raw.public_connect ? raw.public_connect : null;
    return {
      id: text(raw?.world_id ?? raw?.source_world_id, 'public-world'),
      name: text(raw?.world_name ?? raw?.name, 'Unnamed World'),
      description: text(raw?.description, raw?.is_sync_world ? 'Dragonwilds Sync World' : 'Public Dragonwilds server'),
      region: text(raw?.country_name ?? raw?.region ?? raw?.country_code, 'Unknown'),
      version: text(raw?.version, 'Unknown'),
      status: text(raw?.status, 'offline').toLowerCase(),
      current: Math.max(0, number(players.current ?? raw?.players_current, 0)),
      max: Math.max(0, number(players.max ?? raw?.players_max, 0)),
      tags: list(raw?.tags, 10),
      badges: list(raw?.badges, 8),
      source: text(raw?.source_name, raw?.is_sync_world ? 'Dragonwilds Sync' : 'Public source'),
      isSync: Boolean(raw?.is_sync_world),
      host: text(connect?.host ?? raw?.public_connect_host, ''),
      port: number(connect?.port ?? raw?.public_connect_port, 0),
      lastSeen: number(raw?.last_seen, 0),
    };
  }

  function isOnline(world) {
    return ['online', 'starting', 'maintenance'].includes(world.status);
  }

  function setStatus(message, kind = '') {
    const status = byId('dws-public-server-status');
    if (!status) return;
    status.className = `dws-public-server-status ${kind}`.trim();
    status.textContent = message;
  }

  function currentView() {
    return localStorage.getItem(VIEW_KEY) === 'cards' ? 'cards' : 'horizontal';
  }

  function renderRows() {
    const panel = document.querySelector('.dws-public-server-panel');
    if (!panel) return;
    const results = byId('dws-public-server-results', panel);
    const summary = byId('dws-public-server-summary', panel);
    const search = text(byId('dws-public-server-search', panel)?.value).toLowerCase();
    if (!results || !summary) return;

    const filtered = rows
      .filter((world) => !search || [world.name, world.region, world.version, world.source, ...world.tags, ...world.badges].join(' ').toLowerCase().includes(search))
      .sort((a, b) => Number(isOnline(b)) - Number(isOnline(a)) || b.current - a.current || b.lastSeen - a.lastSeen || a.name.localeCompare(b.name));

    const syncCount = rows.filter((world) => world.isSync).length;
    const publicCount = rows.length - syncCount;
    const onlineCount = rows.filter(isOnline).length;
    summary.replaceChildren();
    const pieces = [
      ['Loaded', rows.length],
      ['Online', onlineCount],
      ['Sync Worlds', syncCount],
      ['Public Servers', publicCount],
      ['Showing', filtered.length],
    ];
    pieces.forEach(([label, value]) => {
      const span = make('span');
      span.append(document.createTextNode(`${label} `), make('b', '', String(value)));
      summary.appendChild(span);
    });

    const view = currentView();
    results.className = `dws-public-server-results ${view === 'horizontal' ? 'horizontal' : ''}`.trim();
    panel.querySelectorAll('[data-dws-public-view]').forEach((button) => button.classList.toggle('active', button.dataset.dwsPublicView === view));
    results.replaceChildren();

    if (!filtered.length) {
      results.appendChild(make('div', 'dws-public-empty', rows.length ? 'No public servers match this search.' : 'No public servers have been loaded yet.'));
      return;
    }

    const fragment = document.createDocumentFragment();
    filtered.forEach((world) => {
      const card = make('article', 'dws-public-server-card');

      const identity = make('div');
      const head = make('div', 'dws-public-server-card-head');
      const title = make('div');
      title.append(make('h3', '', world.name), make('small', '', `${world.source} · ${world.id}`));
      head.append(title, make('span', `dws-public-type ${world.isSync ? 'sync' : 'public'}`, world.isSync ? 'SYNC WORLD' : 'PUBLIC SERVER'));
      identity.append(head, make('div', 'dws-public-server-description', world.description));

      const metrics = make('div', 'dws-public-server-metrics');
      metrics.append(
        make('span', '', isOnline(world) ? 'ONLINE' : world.status.toUpperCase()),
        make('span', '', world.region),
        make('span', '', `${world.current} / ${world.max || '—'} players`),
        make('span', '', world.version),
      );

      const detail = make('div');
      const tags = make('div', 'dws-public-server-tags');
      (world.tags.length ? world.tags : world.badges).slice(0, 6).forEach((tag) => tags.appendChild(make('span', '', tag)));
      detail.appendChild(tags);
      if (world.host) detail.appendChild(make('div', 'dws-public-server-route', `Public route: ${world.host}${world.port ? `:${world.port}` : ''}`));
      else detail.appendChild(make('div', 'dws-public-server-route', world.isSync ? 'Sync metadata published; public route not exposed.' : 'Public source does not expose a direct route.'));

      card.append(identity, metrics, detail);
      fragment.appendChild(card);
    });
    results.appendChild(fragment);
  }

  async function loadDirectory({ force = false } = {}) {
    const panel = document.querySelector('.dws-public-server-panel');
    if (!panel) return;
    const input = byId('dws-public-server-link', panel);
    if (!input) return;
    const pageLink = text(input.value, PAGE_LINK);
    let endpoint;
    try { endpoint = resolveFeed(pageLink); } catch (error) { setStatus(error.message || String(error), 'error'); return; }
    localStorage.setItem(LINK_KEY, pageLink);

    if (!force && rows.length && Date.now() - lastLoadedAt < 5000) {
      renderRows();
      return;
    }

    setStatus('Loading public servers…');
    try {
      const response = await fetch(endpoint, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (!response.ok) throw new Error(`Directory returned HTTP ${response.status}.`);
      const payload = await response.json();
      const source = Array.isArray(payload?.worlds) ? payload.worlds : Array.isArray(payload) ? payload : [];
      const unique = new Map();
      source.map(normalizeWorld).forEach((world) => unique.set(world.id, world));
      rows = [...unique.values()];
      lastLoadedAt = Date.now();
      setStatus(`${rows.length} public server${rows.length === 1 ? '' : 's'} loaded`, 'ok');
      const endpointNode = byId('dws-public-server-endpoint', panel);
      if (endpointNode) endpointNode.textContent = endpoint;
      renderRows();
    } catch (error) {
      setStatus(`Public Server List unavailable: ${error.message || error}`, 'error');
      renderRows();
    }
  }

  function deactivate() {
    active = false;
    const content = document.querySelector('.world-source-tabs')?.closest('.content');
    content?.classList.remove('dws-public-server-mode');
    document.querySelector('.dws-public-server-tab')?.classList.remove('active');
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  }

  function activate() {
    const tabs = document.querySelector('.world-source-tabs');
    const panel = document.querySelector('.dws-public-server-panel');
    const content = tabs?.closest('.content');
    if (!tabs || !panel || !content) return;
    active = true;
    tabs.querySelectorAll('button').forEach((button) => button.classList.remove('active'));
    tabs.querySelector('.dws-public-server-tab')?.classList.add('active');
    content.classList.add('dws-public-server-mode');
    loadDirectory({ force: !rows.length });
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => { if (active) loadDirectory({ force: true }); }, REFRESH_MS);
  }

  function buildPanel() {
    const panel = make('section', 'dws-public-server-panel');
    panel.innerHTML = `
      <div class="dws-public-server-head">
        <div><div class="eyebrow">Website-backed discovery</div><h2>Public Server List</h2><p>Paste the Dragonwilds Sync Public Server Directory webpage link. The application resolves it to the same read-only, deduplicated Cloudflare feed used by the website. Sync Worlds win strong duplicate matches; ordinary public servers remain limited discovery records.</p></div>
        <span class="dws-public-server-status" id="dws-public-server-status">Not loaded</span>
      </div>
      <div class="dws-public-server-controls">
        <label><small>Public directory webpage or feed</small><input class="field" id="dws-public-server-link" type="url" spellcheck="false" /></label>
        <button class="btn primary" id="dws-public-server-load" type="button">Load Public Servers</button>
        <label class="dws-public-search-wrap"><small>Search loaded servers</small><input class="field" id="dws-public-server-search" type="search" placeholder="World, region, build, source…" /></label>
        <div class="dws-public-view-toggle" role="group" aria-label="Public Server List view"><button type="button" data-dws-public-view="cards">▦ Placards</button><button type="button" data-dws-public-view="horizontal">☰ Horizontal</button></div>
      </div>
      <div class="dws-public-server-summary" id="dws-public-server-summary"></div>
      <div class="dws-public-server-results" id="dws-public-server-results"><div class="dws-public-empty">Paste or keep the default website link, then load the Public Server List.</div></div>
      <div class="muted-small" style="margin-top:9px">Resolved read-only endpoint: <span id="dws-public-server-endpoint">—</span> · refreshes every 30 seconds while this tab is open.</div>
    `;
    const input = byId('dws-public-server-link', panel);
    input.value = localStorage.getItem(LINK_KEY) || PAGE_LINK;

    byId('dws-public-server-load', panel)?.addEventListener('click', () => loadDirectory({ force: true }));
    byId('dws-public-server-search', panel)?.addEventListener('input', renderRows);
    input.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); loadDirectory({ force: true }); } });
    input.addEventListener('paste', () => setTimeout(() => loadDirectory({ force: true }), 60));
    panel.querySelectorAll('[data-dws-public-view]').forEach((button) => button.addEventListener('click', () => {
      const next = button.dataset.dwsPublicView === 'cards' ? 'cards' : 'horizontal';
      localStorage.setItem(VIEW_KEY, next);
      renderRows();
    }));
    return panel;
  }

  function ensure() {
    const tabs = document.querySelector('.world-source-tabs');
    if (!tabs) {
      if (active) deactivate();
      return;
    }
    if (!tabs.querySelector('.dws-public-server-tab')) {
      const button = make('button', 'dws-public-server-tab');
      const strong = make('strong', '', 'Public Server List');
      const span = make('span', '', 'Website-backed combined public directory');
      button.append(strong, span);
      button.type = 'button';
      button.addEventListener('click', activate);
      tabs.appendChild(button);
    }
    if (!document.querySelector('.dws-public-server-panel')) {
      tabs.insertAdjacentElement('afterend', buildPanel());
    }
    if (active) activate();
  }

  document.addEventListener('click', (event) => {
    if (event.target.closest('[data-world-tab]')) deactivate();
  }, true);

  const observer = new MutationObserver(() => ensure());
  observer.observe(document.querySelector('#app') || document.body, { childList: true, subtree: true });
  ensure();
})();
