/* Public Server Directory view mode, pagination, Sync retention, and resilient fallback. */
(() => {
  const VIEW_KEY = 'dragonwilds-sync-public-directory-view';
  const PAGE_LINK = 'https://gh0sted5456-us.github.io/Dragonwilds-Sync/servers.html';
  const FALLBACK_URL = 'assets/public-worlds-fallback.json';
  const PAGE_SIZE = 10;
  const SYNC_FORGET_MS = 6 * 60 * 60 * 1000;
  const grid = document.querySelector('#world-grid');
  const pagination = document.querySelector('#world-pagination');
  if (!grid) return;

  const buttons = [...document.querySelectorAll('[data-directory-view]')];
  const normalizeView = (value) => value === 'horizontal' ? 'horizontal' : 'placards';
  let view = normalizeView(localStorage.getItem(VIEW_KEY));
  let fallbackRequest = null;
  let currentPage = 1;

  const baseNormalizeWorld = typeof normalizeWorld === 'function' ? normalizeWorld : null;
  if (baseNormalizeWorld) {
    normalizeWorld = function publicDirectoryNormalizeWorld(raw) {
      const world = baseNormalizeWorld(raw);
      world.isSyncWorld = Boolean(raw?.is_sync_world || raw?.directory_source === 'dragonwilds-sync');
      world.directoryCategory = String(raw?.directory_category || '');
      return world;
    };
  }

  function isSync(world) {
    if (typeof world?.isSyncWorld === 'boolean') return world.isSyncWorld;
    return !String(world?.worldId || '').startsWith('public-');
  }

  function timestampMs(value) {
    if (typeof normalizeTimestamp === 'function') return normalizeTimestamp(value) || 0;
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) return 0;
    return number > 1e12 ? number : number * 1000;
  }

  function isForgottenSync(world) {
    if (!isSync(world)) return false;
    const seen = timestampMs(world?.lastSeen);
    return !seen || Date.now() - seen > SYNC_FORGET_MS;
  }

  function syncFirstCompare(a, b) {
    const aSync = Number(isSync(a));
    const bSync = Number(isSync(b));
    if (aSync !== bSync) return bSync - aSync;

    const aOnline = typeof isOnline === 'function' ? Number(isOnline(a)) : 0;
    const bOnline = typeof isOnline === 'function' ? Number(isOnline(b)) : 0;
    if (aOnline !== bOnline) return bOnline - aOnline;

    const seenDiff = timestampMs(b?.lastSeen) - timestampMs(a?.lastSeen);
    if (seenDiff) return seenDiff;
    const playerDiff = Number(b?.currentPlayers || 0) - Number(a?.currentPlayers || 0);
    if (playerDiff) return playerDiff;
    return String(a?.name || '').localeCompare(String(b?.name || ''));
  }

  function filteredWorlds() {
    const query = (document.querySelector('#world-search')?.value || '').trim().toLowerCase();
    return allWorlds.filter((world) => {
      if (isForgottenSync(world)) return false;
      const online = typeof isOnline === 'function' && isOnline(world);
      const matchesFilter = activeFilter === 'all'
        || (activeFilter === 'online' && online)
        || (activeFilter === 'modded' && typeof isModded === 'function' && isModded(world))
        || (activeFilter === 'current' && typeof buildState === 'function' && buildState(world) === 'current')
        || (activeFilter === 'offline-sync' && isSync(world) && !online);
      if (!matchesFilter) return false;
      if (!query) return true;
      return [world.name, world.region, world.version, ...(world.tags || []), ...(world.mods || [])]
        .join(' ').toLowerCase().includes(query);
    }).sort(syncFirstCompare);
  }

  function makeButton(label, page, options = {}) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.dataset.page = String(page);
    if (options.active) button.setAttribute('aria-current', 'page');
    if (options.disabled) button.disabled = true;
    button.addEventListener('click', () => {
      if (button.disabled || page === currentPage) return;
      currentPage = page;
      renderWorlds();
      document.querySelector('#servers')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    return button;
  }

  function renderPagination(total) {
    if (!pagination) return;
    pagination.replaceChildren();
    if (!total) {
      pagination.hidden = true;
      return;
    }

    const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
    currentPage = Math.max(1, Math.min(currentPage, pageCount));
    pagination.hidden = false;

    const status = document.createElement('span');
    status.className = 'directory-page-status';
    const first = (currentPage - 1) * PAGE_SIZE + 1;
    const last = Math.min(total, currentPage * PAGE_SIZE);
    status.textContent = `Showing ${first}–${last} of ${total} · ${PAGE_SIZE} per page`;

    const controls = document.createElement('div');
    controls.className = 'directory-page-controls';
    controls.appendChild(makeButton('← Prev', currentPage - 1, { disabled: currentPage === 1 }));

    const candidates = new Set([1, pageCount, currentPage - 2, currentPage - 1, currentPage, currentPage + 1, currentPage + 2]);
    const pages = [...candidates].filter((page) => page >= 1 && page <= pageCount).sort((a, b) => a - b);
    let previous = 0;
    pages.forEach((page) => {
      if (previous && page - previous > 1) {
        const gap = document.createElement('span');
        gap.className = 'directory-page-gap';
        gap.textContent = '…';
        controls.appendChild(gap);
      }
      controls.appendChild(makeButton(String(page), page, { active: page === currentPage }));
      previous = page;
    });

    controls.appendChild(makeButton('Next →', currentPage + 1, { disabled: currentPage === pageCount }));
    pagination.append(status, controls);
  }

  renderWorlds = function pagedPublicDirectoryRender() {
    const rows = filteredWorlds();
    const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    currentPage = Math.max(1, Math.min(currentPage, pageCount));
    const start = (currentPage - 1) * PAGE_SIZE;
    const visible = rows.slice(start, start + PAGE_SIZE);

    grid.replaceChildren();
    if (!visible.length) {
      const empty = document.createElement('div');
      empty.className = 'directory-placeholder';
      const strong = document.createElement('strong');
      strong.textContent = allWorlds.length ? 'No worlds match this view.' : 'No public Worlds are broadcasting right now.';
      const detail = document.createElement('p');
      detail.textContent = allWorlds.length ? 'Try another filter or search term.' : 'The directory is online and ready for participating Dragonwilds Sync hosts.';
      empty.append(strong, detail);
      grid.appendChild(empty);
      renderPagination(0);
      applyView();
      return;
    }

    visible.forEach((world) => grid.appendChild(createWorldCard(world)));
    renderPagination(rows.length);
    applyView();
  };

  function applyView() {
    grid.classList.toggle('directory-horizontal', view === 'horizontal');
    buttons.forEach((button) => {
      const active = normalizeView(button.dataset.directoryView) === view;
      button.setAttribute('aria-pressed', String(active));
    });
  }

  buttons.forEach((button) => button.addEventListener('click', () => {
    view = normalizeView(button.dataset.directoryView);
    localStorage.setItem(VIEW_KEY, view);
    applyView();
  }));

  document.querySelectorAll('[data-world-filter]').forEach((button) => button.addEventListener('click', () => {
    currentPage = 1;
    setTimeout(() => renderWorlds(), 0);
  }));
  document.querySelector('#world-search')?.addEventListener('input', () => {
    currentPage = 1;
    setTimeout(() => renderWorlds(), 0);
  });

  function applyDirectoryMeta(meta) {
    const target = document.querySelector('#stat-total-sync-starts');
    if (!target || !meta || typeof meta !== 'object') return;
    const count = Number(meta.total_sync_world_starts);
    target.textContent = Number.isFinite(count) && count >= 0 ? count.toLocaleString() : '—';
  }

  window.addEventListener('dws-directory-meta', (event) => applyDirectoryMeta(event.detail));
  applyDirectoryMeta(window.__DWS_DIRECTORY_META__);

  const copyButton = document.querySelector('#copy-app-directory-link');
  const copyStatus = document.querySelector('#copy-app-directory-status');
  copyButton?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(PAGE_LINK);
      copyButton.textContent = 'Copied ✓';
      if (copyStatus) copyStatus.textContent = 'Paste this webpage link into Dragonwilds Sync → Public Server List.';
      setTimeout(() => { copyButton.textContent = 'Copy App Link'; }, 1800);
    } catch (_) {
      if (copyStatus) copyStatus.textContent = PAGE_LINK;
    }
  });

  function liveRowsPresent() {
    try {
      return typeof allWorlds !== 'undefined' && Array.isArray(allWorlds) && allWorlds.length > 0;
    } catch (_) {
      return false;
    }
  }

  async function applyFallbackSnapshot() {
    if (liveRowsPresent() || fallbackRequest) return;
    fallbackRequest = (async () => {
      try {
        const response = await fetch(FALLBACK_URL, { headers: { Accept: 'application/json' }, cache: 'no-store' });
        if (!response.ok) return;
        const payload = await response.json();
        const source = Array.isArray(payload?.worlds) ? payload.worlds : [];
        if (!source.length || typeof normalizeWorld !== 'function') return;

        const deduped = new Map();
        source.map(normalizeWorld).forEach((world) => deduped.set(world.worldId, world));
        const next = [...deduped.values()].filter((world) => !isForgottenSync(world)).sort(syncFirstCompare);
        if (!next.length) return;

        allWorlds = next;
        currentPage = 1;
        grid.dataset.directorySource = 'github-pages-fallback';
        if (payload?.directory) applyDirectoryMeta(payload.directory);
        if (typeof setDirectoryState === 'function') {
          const generated = payload?.generated_at && typeof relativeTime === 'function' ? ` · snapshot ${relativeTime(payload.generated_at)}` : '';
          setDirectoryState('online', 'Public list loaded', `${next.length} public worlds from resilient snapshot${generated}`);
        }
        if (typeof deriveStatsFromWorlds === 'function') deriveStatsFromWorlds();
        renderWorlds();
      } catch (_) {
        // The base script already presents the live-directory error state. This
        // fallback is intentionally silent if both public sources are unavailable.
      }
    })();
    try { await fallbackRequest; } finally { fallbackRequest = null; }
  }

  // The main script starts the live Worker request before this helper loads.
  // Observe its render result so a zero-row/error response cannot erase a valid
  // same-origin fallback snapshot that GitHub Actions refreshes independently.
  const fallbackObserver = new MutationObserver(() => {
    if (!liveRowsPresent() && grid.querySelector('.directory-placeholder')) applyFallbackSnapshot();
  });
  fallbackObserver.observe(grid, { childList: true, subtree: false });

  applyView();
  if (liveRowsPresent()) renderWorlds();
  setTimeout(applyFallbackSnapshot, 900);
  setTimeout(applyFallbackSnapshot, 3500);
})();
