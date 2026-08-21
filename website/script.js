const API_BASE = 'https://dragonwilds-sync-directory.dragonwilds.workers.dev';
const RELEASE_API = 'https://api.github.com/repos/gh0sted5456-us/Dragonwilds-Sync/releases/latest';
const THEME_KEY = 'dragonwilds-sync-theme';
const CURRENT_CL_FALLBACK = 'CL-232224';

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
  return Array.isArray(value) ? value.slice(0, maxItems).map((item) => safeText(item, '', 80)).filter(Boolean) : [];
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

function normalizeWorld(raw) {
  const players = raw && typeof raw.players === 'object' && raw.players ? raw.players : {};
  const connect = raw && typeof raw.public_connect === 'object' && raw.public_connect ? raw.public_connect : null;
  return {
    worldId: safeText(raw?.world_id, 'unknown-world', 120),
    name: safeText(raw?.world_name ?? raw?.name, 'Unnamed World', 90),
    description: safeText(raw?.description, 'A public Dragonwilds Sync world.', 240),
    region: safeText(raw?.region, 'Unknown', 40),
    version: safeText(raw?.version, 'Unknown', 40),
    status: safeText(raw?.status, 'offline', 24).toLowerCase(),
    currentPlayers: Math.max(0, safeNumber(players.current ?? raw?.player_current, 0)),
    maxPlayers: Math.max(0, safeNumber(players.max ?? raw?.player_max, 0)),
    tags: safeList(raw?.tags, 10),
    mods: safeList(raw?.mods, 18),
    rules: safeList(raw?.rules, 12),
    badges: safeList(raw?.badges, 10),
    lastSeen: raw?.last_seen ?? null,
    heartbeatAge: safeNumber(raw?.heartbeat_age, -1),
    connect: connect ? { host: safeText(connect.host, '', 180), port: safeNumber(connect.port, 0) } : null
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

function canonicalCl(value) {
  const match = String(value || '').trim().match(/^cl-?(\d{4,})$/i);
  return match ? `CL-${match[1]}` : '';
}

function choosePublishedCl(rows) {
  const counts = new Map();
  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const cl = canonicalCl(row?.version ?? row?.build ?? row?.current_build);
    if (cl) counts.set(cl, (counts.get(cl) || 0) + 1);
  });
  return [...counts].sort((a, b) => b[1] - a[1] || Number(b[0].slice(3)) - Number(a[0].slice(3)))[0]?.[0] || '';
}

function publishCurrentCl(value) {
  const cl = canonicalCl(value) || CURRENT_CL_FALLBACK;
  window.DWS_CURRENT_CL = cl;
  $$('[data-current-cl]').forEach((node) => { node.textContent = cl; });
  window.dispatchEvent(new CustomEvent('dws-current-cl', { detail: { cl } }));
  return cl;
}

publishCurrentCl(CURRENT_CL_FALLBACK);

function isOnline(world) {
  return ['online', 'starting', 'maintenance'].includes(world.status) && world.status !== 'offline';
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

function createWorldCard(world) {
  const card = makeEl('article', 'world-card');
  card.tabIndex = 0;
  card.dataset.worldId = world.worldId;
  card.setAttribute('role', 'button');
  card.setAttribute('aria-label', `View details for ${world.name}`);
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
  const metricData = [
    ['REGION', world.region, ''],
    ['PLAYERS', `${world.currentPlayers} / ${world.maxPlayers || '—'}`, ''],
    ['BUILD', world.version, buildState(world) === 'current' ? 'build-current' : buildState(world) === 'outdated' ? 'build-outdated' : '']
  ];
  metricData.forEach(([label, value, cls]) => {
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
  backFooter.append(makeEl('span', '', 'Public telemetry only — no admin access'), makeEl('b', '', 'FRONT ↻'));
  back.appendChild(backFooter);

  inner.append(front, back);
  card.appendChild(inner);
  const flip = () => {
    const flipped = card.classList.toggle('flipped');
    card.setAttribute('aria-pressed', String(flipped));
  };
  card.addEventListener('click', flip);
  card.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      flip();
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
    publishCurrentCl(choosePublishedCl(rows));
    const deduped = new Map();
    rows.map(normalizeWorld).forEach((world) => deduped.set(world.worldId, world));
    allWorlds = [...deduped.values()].sort((a, b) => Number(isOnline(b)) - Number(isOnline(a)) || (normalizeTimestamp(b.lastSeen) || 0) - (normalizeTimestamp(a.lastSeen) || 0) || a.name.localeCompare(b.name));
    setDirectoryState('online', 'Directory online', `${allWorlds.length} public world${allWorlds.length === 1 ? '' : 's'} received`);
    deriveStatsFromWorlds();
    renderWorlds();
  } catch (error) {
    if (allWorlds.length) {
      setDirectoryState('online', 'Directory cached', `${allWorlds.length} public world${allWorlds.length === 1 ? '' : 's'} retained while the directory reconnects`);
      deriveStatsFromWorlds();
      renderWorlds();
    } else {
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
}

async function loadNetwork() {
  const message = $('#network-message');
  const dot = $('#network-live-dot');
  try {
    const data = await fetchJson('/api/v1/network');
    const users = data?.active_users;
    const worlds = data?.active_worlds;
    const players = data?.players_in_listed_worlds;
    currentBuild = safeText(data?.current_build ?? data?.version, '', 40) || null;
    const productionCl = publishCurrentCl(canonicalCl(currentBuild) || CURRENT_CL_FALLBACK);
    $('#stat-users').textContent = Number.isFinite(Number(users)) ? String(Number(users)) : '—';
    $('#stat-worlds').textContent = Number.isFinite(Number(worlds)) ? String(Number(worlds)) : $('#stat-worlds').textContent;
    $('#stat-players').textContent = Number.isFinite(Number(players)) ? String(Number(players)) : $('#stat-players').textContent;
    $('#stat-build').textContent = productionCl;
    message.textContent = 'Live aggregate presence from participating Dragonwilds Sync installations and public Worlds.';
    dot.className = 'network-live-dot';
    renderWorlds();
  } catch (_) {
    $('#stat-users').textContent = '—';
    $('#stat-build').textContent = publishCurrentCl(CURRENT_CL_FALLBACK);
    message.textContent = 'Public World telemetry is live. Anonymous active-user totals will appear automatically when the network-presence endpoint is enabled.';
    dot.className = 'network-live-dot offline';
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
  const releaseLink = $('#release-link');
  try {
    const response = await fetch(RELEASE_API, { headers: { Accept: 'application/vnd.github+json' } });
    if (!response.ok) throw new Error('No public release');
    const release = await response.json();
    const date = new Date(release.published_at || release.created_at);
    releaseVersion.textContent = safeText(release.tag_name || release.name, 'Latest');
    releaseDate.textContent = Number.isNaN(date.getTime()) ? 'GitHub Releases' : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    const executable = (release.assets || []).find((asset) => /\.exe$/i.test(String(asset?.name || '')) && asset?.browser_download_url);
    if (executable) {
      releaseLink.href = executable.browser_download_url;
      releaseLink.setAttribute('download', '');
    }
  } catch (_) {
    releaseVersion.textContent = 'Latest available';
    releaseDate.textContent = 'GitHub Releases';
  }
}

async function refreshNetworkData() {
  await Promise.allSettled([loadWorlds(), loadNetwork()]);
}

refreshNetworkData();
loadLatestRelease();

const refreshTimer = setInterval(() => {
  if (!document.hidden) refreshNetworkData();
}, 60000);
window.addEventListener('beforeunload', () => clearInterval(refreshTimer));
