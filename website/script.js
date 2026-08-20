const API_BASE = ['https://dragonwilds-sync-directory', 'dragonwilds.workers.dev'].join('.');
const RELEASE_API = 'https://api.github.com/repos/gh0sted5456-us/Dragonwilds-Sync/releases/latest';
const THEME_KEY = 'dragonwilds-sync-theme';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function setTheme(theme, persist = true) {
  const allowed = ['dark', 'white', 'glass'];
  const next = allowed.includes(theme) ? theme : 'dark';
  document.documentElement.dataset.theme = next;
  $$('.theme-switcher [data-theme-choice]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.themeChoice === next));
  });
  const meta = $('meta[name="theme-color"]');
  if (meta) meta.content = next === 'white' ? '#f4f3ef' : next === 'glass' ? '#0b1117' : '#0b0d0f';
  if (persist) localStorage.setItem(THEME_KEY, next);
}

setTheme(localStorage.getItem(THEME_KEY) || 'dark', false);
$$('.theme-switcher [data-theme-choice]').forEach((button) => button.addEventListener('click', () => setTheme(button.dataset.themeChoice)));

const navToggle = $('.nav-toggle');
const nav = $('.main-nav');
if (navToggle && nav) {
  navToggle.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    navToggle.setAttribute('aria-expanded', String(open));
  });
  $$('a', nav).forEach((link) => link.addEventListener('click', () => {
    nav.classList.remove('open');
    navToggle.setAttribute('aria-expanded', 'false');
  }));
}

const revealItems = $$('.reveal');
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  revealItems.forEach((item) => observer.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add('visible'));
}

function safeText(value, fallback = '—', max = 180) {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text ? text.slice(0, max) : fallback;
}

function safeList(value, maxItems = 12) {
  const values = Array.isArray(value) ? value : (typeof value === 'string' ? value.split(/\r?\n|[,;]+/) : []);
  return values.slice(0, maxItems).map((item) => safeText(item, '', 80)).filter(Boolean);
}

function safeNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeTimestamp(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n > 1e12 ? n : n * 1000;
}

function relativeTime(value) {
  const timestamp = normalizeTimestamp(value);
  if (!timestamp) return 'Unknown';
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function normalizeRemoteAdmin(raw, worldId, worldName) {
  const remote = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  if (!remote.configured || !remote.enabled || !remote.available || remote.authority !== 'target-world') return null;
  try {
    const endpoint = new URL(String(remote.endpoint || ''));
    if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || endpoint.hash) return null;
    endpoint.search = '';
    endpoint.pathname = endpoint.pathname.replace(/\/$/, '');
    const pingPath = String(remote.ping_path || '/api/v1/remote-admin/ping');
    const loginPath = String(remote.login_path || '/admin/login');
    if (pingPath !== '/api/v1/remote-admin/ping' || loginPath !== '/admin/login') return null;
    return {
      endpoint: endpoint.href.replace(/\/$/, ''),
      pingPath, loginPath,
      worldId: safeText(remote.world_id ?? worldId, worldId, 120),
      worldName: safeText(remote.world_name ?? worldName, worldName, 160),
      fingerprint: safeText(remote.fingerprint, '', 96),
      browserCompatible: remote.browser_compatible !== false,
    };
  } catch (_) { return null; }
}

function normalizeWorld(raw) {
  const players = raw && typeof raw.players === 'object' && raw.players ? raw.players : {};
  const connectSource = raw && typeof raw.public_connect === 'object' && raw.public_connect
    ? raw.public_connect
    : (raw && typeof raw.connection === 'object' && raw.connection ? raw.connection : null);
  const worldId = safeText(raw?.world_id, 'unknown-world', 120);
  const name = safeText(raw?.world_name ?? raw?.name, 'Unnamed World', 90);
  const remoteAdmin = normalizeRemoteAdmin(raw?.remote_management, worldId, name);
  return {
    worldId,
    name,
    description: safeText(raw?.description, 'A public Dragonwilds Sync world.', 240),
    region: safeText(raw?.region, 'Unknown', 40),
    version: safeText(raw?.version ?? raw?.cl, 'Unknown', 40),
    status: safeText(raw?.status, 'offline', 24).toLowerCase(),
    currentPlayers: Math.max(0, safeNumber(players.current ?? raw?.player_current ?? raw?.player_count, 0)),
    maxPlayers: Math.max(0, safeNumber(players.max ?? raw?.player_max ?? raw?.max_players, 0)),
    tags: safeList(raw?.tags, 10),
    mods: safeList(raw?.mods, 18),
    rules: safeList(raw?.rules, 12),
    badges: safeList(raw?.badges, 10),
    lastSeen: raw?.last_seen ?? null,
    heartbeatAge: safeNumber(raw?.heartbeat_age, -1),
    fingerprint: safeText(raw?.fingerprint ?? raw?.fingerprint_claimed ?? remoteAdmin?.fingerprint, '', 96),
    remoteAdmin,
    connect: connectSource ? {
      host: safeText(connectSource.host ?? connectSource.address, '', 180),
      port: safeNumber(connectSource.port ?? connectSource.game_port, 0),
    } : null
  };
}

async function fetchJson(path, timeoutMs = 8000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, { headers: { Accept: 'application/json' }, signal: controller.signal, cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

let allWorlds = [];
let activeFilter = 'all';
let currentBuild = null;

function isOnline(world) {
  return ['active', 'online', 'starting', 'maintenance', 'stopping'].includes(world.status) && world.status !== 'offline';
}

function isModded(world) {
  return world.mods.length > 0 || world.tags.some((tag) => /mod/i.test(tag));
}

function buildState(world) {
  if (!currentBuild || !world.version || world.version === 'Unknown') return 'unknown';
  return world.version.toLowerCase() === String(currentBuild).toLowerCase() ? 'current' : 'outdated';
}

function makeEl(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function appendChips(container, values, emptyText = 'None published') {
  const list = values.length ? values : [emptyText];
  list.forEach((value) => container.appendChild(makeEl('span', '', value)));
}

async function openVerifiedRemoteAdmin(world, button) {
  const remote = world?.remoteAdmin;
  if (!remote?.browserCompatible || !remote.endpoint) throw new Error('This World is not advertising an HTTPS Remote Admin endpoint.');

  // Open synchronously from the click so browsers treat the final handoff as a
  // user-requested tab. Nothing secret is put into the placeholder tab.
  const tab = window.open('about:blank', '_blank');
  if (tab) {
    try { tab.opener = null; } catch (_) {}
    try { tab.document.title = 'Contacting Dragonwilds Sync server…'; } catch (_) {}
  }

  const label = button?.querySelector?.('[data-remote-label]');
  const original = label?.textContent || button?.textContent || 'REMOTE LOGIN ↗';
  const setLabel = (value) => { if (!button) return; const target=button.querySelector?.('[data-remote-label]'); if (target) target.textContent=value; else button.textContent=value; };
  if (button) { button.disabled = true; button.setAttribute('aria-busy','true'); setLabel('CONTACTING SERVER…'); }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const ping = new URL(remote.pingPath, `${remote.endpoint}/`);
    ping.searchParams.set('world_id', world.worldId);
    if (remote.fingerprint || world.fingerprint) ping.searchParams.set('fingerprint', remote.fingerprint || world.fingerprint);
    const response = await fetch(ping.href, { headers: { Accept: 'application/json' }, signal: controller.signal, cache: 'no-store', credentials: 'omit' });
    if (!response.ok) throw new Error(`Target server probe returned HTTP ${response.status}.`);
    const live = await response.json();
    if (!live?.ok || live?.remote_admin_enabled !== true) throw new Error('Remote Admin is not enabled on the target server.');
    if (live?.authority !== 'target-world' || live?.protocol !== 'dragonwilds-sync-remote-admin' || Number(live?.protocol_version) !== 1) throw new Error('The target did not return the Dragonwilds Sync Remote Admin identity protocol.');
    if (String(live?.world_id || '') !== String(world.worldId || '')) throw new Error('The live server World ID does not match this directory placard.');
    const expectedFingerprint = String(remote.fingerprint || world.fingerprint || '');
    if (expectedFingerprint && String(live?.fingerprint || '') !== expectedFingerprint) throw new Error('The live server fingerprint does not match this directory placard.');

    const loginPath = String(live?.login_path || remote.loginPath || '');
    if (loginPath !== '/admin/login') throw new Error('The target advertised an invalid Remote Admin login path.');
    const login = new URL(loginPath, `${remote.endpoint}/`);
    login.searchParams.set('world', world.name);
    if (tab && !tab.closed) tab.location.replace(login.href);
    else window.open(login.href, '_blank', 'noopener');
    setLabel('SERVER VERIFIED ✓');
  } catch (error) {
    try { if (tab && !tab.closed) tab.close(); } catch (_) {}
    if (button) {
      setLabel('REMOTE ADMIN UNAVAILABLE');
      button.title = error?.message || String(error);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    if (button) setTimeout(() => { button.disabled = false; button.removeAttribute('aria-busy'); setLabel(original); }, 2600);
  }
}

function createWorldCard(world) {
  const card = makeEl('article', 'world-card');
  card.tabIndex = 0;
  card.dataset.worldId = world.worldId;
  card.setAttribute('role', 'button');
  card.setAttribute('aria-pressed', 'false');
  const inner = makeEl('div', 'world-card-inner');
  const front = makeEl('div', 'world-card-face world-card-front');
  const back = makeEl('div', 'world-card-face world-card-back');
  const top = makeEl('div', 'world-card-top');
  const status = makeEl('span', `world-status ${isOnline(world) ? 'online' : ''}`, world.status);
  top.append(status, makeEl('span', 'world-id', world.worldId));
  front.appendChild(top);
  front.appendChild(makeEl('h3', '', world.name));
  front.appendChild(makeEl('p', 'world-description', world.description));
  const metrics = makeEl('div', 'world-metrics');
  [['REGION', world.region, ''], ['PLAYERS', `${world.currentPlayers} / ${world.maxPlayers || '—'}`, ''], ['BUILD', world.version, buildState(world) === 'current' ? 'build-current' : buildState(world) === 'outdated' ? 'build-outdated' : '']].forEach(([label, value, cls]) => {
    const metric = makeEl('div', 'world-metric');
    metric.appendChild(makeEl('span', '', label));
    metric.appendChild(makeEl('strong', cls, value));
    metrics.appendChild(metric);
  });
  front.appendChild(metrics);
  const tags = makeEl('div', 'world-card-tags');
  (world.tags.length ? world.tags.slice(0, 5) : ['Public World']).forEach((tag) => tags.appendChild(makeEl('span', '', tag)));
  front.appendChild(tags);
  const footer = makeEl('div', 'world-card-footer');
  footer.append(makeEl('span', '', `Last seen ${relativeTime(world.lastSeen)}`), makeEl('b', '', 'DETAILS ↻'));
  front.appendChild(footer);
  const backTop = makeEl('div', 'world-card-top');
  backTop.append(makeEl('span', 'world-status', 'PUBLIC DETAILS'), makeEl('span', 'world-id', world.worldId));
  back.appendChild(backTop);
  const backGrid = makeEl('div', 'world-back-grid');
  [['Mods', world.mods], ['Rules', world.rules], ['Badges', world.badges], ['Tags', world.tags]].forEach(([heading, values]) => {
    const section = makeEl('section', 'world-back-section');
    section.appendChild(makeEl('h4', '', heading));
    const list = makeEl('div', 'world-back-list');
    appendChips(list, values);
    section.appendChild(list);
    backGrid.appendChild(section);
  });
  back.appendChild(backGrid);
  if (world.connect?.host) {
    const port = world.connect.port > 0 ? `:${world.connect.port}` : '';
    back.appendChild(makeEl('div', 'world-connect', `Public connect: ${world.connect.host}${port}`));
  }
  const backFooter = makeEl('div', 'world-card-footer');
  const footerText = makeEl('span', '', world.remoteAdmin ? 'Remote Admin is verified directly with this server before login.' : 'Public telemetry only — no admin access');
  backFooter.appendChild(footerText);
  if (world.remoteAdmin) {
    const admin = makeEl('button', 'server-admin-button');
    admin.type = 'button';
    admin.title = 'Verify this live server and open its Remote Admin login';
    const icon=makeEl('img','server-admin-icon');icon.src='assets/platforms/remote-login.svg';icon.alt='';
    const label=makeEl('span','', 'REMOTE LOGIN ↗');label.dataset.remoteLabel='';admin.append(icon,label);
    admin.addEventListener('click', async (event) => {
      event.preventDefault(); event.stopPropagation();
      try { await openVerifiedRemoteAdmin(world, admin); }
      catch (error) { console.warn('[Remote Admin handoff]', error?.message || error); }
    });
    backFooter.appendChild(admin);
  } else {
    backFooter.appendChild(makeEl('b', '', 'FRONT ↻'));
  }
  back.appendChild(backFooter);
  inner.append(front, back);
  card.appendChild(inner);
  const flip = (event) => {
    if (event?.target?.closest?.('button,a,input,select,textarea')) return;
    const flipped = card.classList.toggle('flipped');
    card.setAttribute('aria-pressed', String(flipped));
  };
  card.addEventListener('click', flip);
  card.addEventListener('keydown', (event) => {
    if ((event.key === 'Enter' || event.key === ' ') && !event.target.closest('button,a,input,select,textarea')) {
      event.preventDefault(); flip(event);
    }
  });
  return card;
}

function renderWorlds() {
  const grid = $('#world-grid');
  if (!grid) return;
  const query = ($('#world-search')?.value || '').trim().toLowerCase();
  const filtered = allWorlds.filter((world) => {
    const matchesFilter = activeFilter === 'all' || (activeFilter === 'online' && isOnline(world)) || (activeFilter === 'modded' && isModded(world)) || (activeFilter === 'current' && buildState(world) === 'current');
    if (!matchesFilter) return false;
    if (!query) return true;
    return [world.name, world.region, world.version, ...world.tags, ...world.mods].join(' ').toLowerCase().includes(query);
  });
  grid.replaceChildren();
  if (!filtered.length) {
    const empty = makeEl('div', 'directory-placeholder');
    empty.append(makeEl('strong', '', allWorlds.length ? 'No worlds match this view.' : 'No public Worlds are broadcasting right now.'), makeEl('p', '', allWorlds.length ? 'Try another filter or search term.' : 'The directory is online and ready for participating Dragonwilds Sync hosts.'));
    grid.appendChild(empty);
    return;
  }
  filtered.forEach((world) => grid.appendChild(createWorldCard(world)));
}

function setDirectoryState(kind, title, detail) {
  const el = $('#directory-state');
  if (!el) return;
  el.className = `directory-state ${kind}`;
  $('strong', el).textContent = title;
  $('small', el).textContent = detail;
}

function deriveStatsFromWorlds() {
  const online = allWorlds.filter(isOnline);
  $('#stat-worlds').textContent = String(online.length);
  $('#stat-players').textContent = String(online.reduce((sum, world) => sum + world.currentPlayers, 0));
}

async function loadWorlds() {
  try {
    const data = await fetchJson('/api/v1/worlds');
    const rows = Array.isArray(data?.worlds) ? data.worlds : [];
    const deduped = new Map();
    rows.map(normalizeWorld).forEach((world) => deduped.set(world.worldId, world));
    allWorlds = [...deduped.values()].sort((a, b) => Number(isOnline(b)) - Number(isOnline(a)) || (normalizeTimestamp(b.lastSeen) || 0) - (normalizeTimestamp(a.lastSeen) || 0) || a.name.localeCompare(b.name));
    setDirectoryState('online', 'Directory online', `${allWorlds.length} public world${allWorlds.length === 1 ? '' : 's'} received`);
    deriveStatsFromWorlds();
    const network = data?.network && typeof data.network === 'object' ? data.network : null;
    if (network) {
      const users = network.active_users;
      const worlds = network.active_worlds;
      const players = network.players_in_listed_worlds;
      currentBuild = safeText(network.current_build ?? network.version, '', 40) || null;
      $('#stat-users').textContent = Number.isFinite(Number(users)) ? String(Number(users)) : '—';
      $('#stat-worlds').textContent = Number.isFinite(Number(worlds)) ? String(Number(worlds)) : $('#stat-worlds').textContent;
      $('#stat-players').textContent = Number.isFinite(Number(players)) ? String(Number(players)) : $('#stat-players').textContent;
      $('#stat-build').textContent = currentBuild || '—';
      $('#network-message').textContent = 'Live aggregate presence from participating Dragonwilds Sync installations and public Worlds.';
      $('#network-live-dot').className = 'network-live-dot';
    } else {
      $('#stat-users').textContent = '—';
      $('#stat-build').textContent = 'Pending';
      $('#network-message').textContent = 'Public World telemetry is live. Anonymous active-user totals will appear automatically when the directory includes aggregate presence.';
      $('#network-live-dot').className = 'network-live-dot offline';
    }
    renderWorlds();
  } catch (error) {
    setDirectoryState('error', 'Directory unavailable', 'Live world data could not be reached');
    const grid = $('#world-grid');
    if (grid) {
      grid.replaceChildren();
      const state = makeEl('div', 'directory-placeholder');
      state.append(makeEl('strong', '', 'Public directory temporarily unavailable'), makeEl('p', '', 'Downloads, documentation, and the rest of the site are still available.'));
      grid.appendChild(state);
    }
  }
}

$$('[data-world-filter]').forEach((button) => button.addEventListener('click', () => {
  activeFilter = button.dataset.worldFilter;
  $$('[data-world-filter]').forEach((item) => item.classList.toggle('active', item === button));
  renderWorlds();
}));
$('#world-search')?.addEventListener('input', renderWorlds);

async function loadLatestRelease() {
  const releaseVersion = $('#release-version');
  const releaseDate = $('#release-date');
  const releaseChannel = $('#release-channel');
  const releaseLink = $('#release-link');
  try {
    const response = await fetch(RELEASE_API, { headers: { Accept: 'application/vnd.github+json' } });
    if (!response.ok) throw new Error('No public release');
    const release = await response.json();
    const date = new Date(release.published_at || release.created_at);
    releaseVersion.textContent = safeText(release.tag_name || release.name, 'Latest');
    releaseDate.textContent = Number.isNaN(date.getTime()) ? 'GitHub Releases' : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    releaseChannel.textContent = 'Main';
    if (release.html_url) releaseLink.href = release.html_url;
  } catch (_) {
    releaseVersion.textContent = 'Latest available';
    releaseDate.textContent = 'GitHub Releases';
    releaseChannel.textContent = 'Main';
  }
}

// The public site is static. Remote Admin credentials never cross GitHub or the
// directory Worker: only the advertised target is probed, then the browser is
// handed directly to that server's own authenticated login surface.
const remoteStyle = document.createElement('style');
remoteStyle.textContent = '.server-admin-button{min-height:34px;padding:6px 10px;border:1px solid #9f7938;border-radius:8px;background:rgba(213,165,74,.1);color:inherit;font:800 10px/1 system-ui;letter-spacing:.04em;cursor:pointer}.server-admin-button:hover{border-color:#d5a54a}.server-admin-button:disabled{cursor:wait;opacity:.72}';
document.head.appendChild(remoteStyle);

async function refreshNetworkData() {
  await loadWorlds();
}

refreshNetworkData();
loadLatestRelease();

const refreshTimer = setInterval(() => {
  if (!document.hidden) refreshNetworkData();
}, 60000);
window.addEventListener('beforeunload', () => clearInterval(refreshTimer));
