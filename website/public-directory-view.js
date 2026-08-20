/* Public Server Directory view mode + resilient public-list fallback. */
(() => {
  const VIEW_KEY = 'dragonwilds-sync-public-directory-view';
  const PAGE_LINK = 'https://gh0sted5456-us.github.io/Dragonwilds-Sync/servers.html';
  const FALLBACK_URL = 'assets/public-worlds-fallback.json';
  const grid = document.querySelector('#world-grid');
  if (!grid) return;

  const buttons = [...document.querySelectorAll('[data-directory-view]')];
  const normalizeView = (value) => value === 'horizontal' ? 'horizontal' : 'placards';
  let view = normalizeView(localStorage.getItem(VIEW_KEY));
  let fallbackRequest = null;

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
        if (!source.length || typeof normalizeWorld !== 'function' || typeof renderWorlds !== 'function') return;

        const deduped = new Map();
        source.map(normalizeWorld).forEach((world) => deduped.set(world.worldId, world));
        const next = [...deduped.values()].sort((a, b) => {
          const aOnline = typeof isOnline === 'function' ? Number(isOnline(a)) : 0;
          const bOnline = typeof isOnline === 'function' ? Number(isOnline(b)) : 0;
          return bOnline - aOnline || b.currentPlayers - a.currentPlayers || a.name.localeCompare(b.name);
        });
        if (!next.length) return;

        allWorlds = next;
        grid.dataset.directorySource = 'github-pages-fallback';
        if (typeof setDirectoryState === 'function') {
          const generated = payload?.generated_at && typeof relativeTime === 'function' ? ` · snapshot ${relativeTime(payload.generated_at)}` : '';
          setDirectoryState('online', 'Public list loaded', `${next.length} public worlds from resilient snapshot${generated}`);
        }
        if (typeof deriveStatsFromWorlds === 'function') deriveStatsFromWorlds();
        renderWorlds();
        applyView();
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
  setTimeout(applyFallbackSnapshot, 900);
  setTimeout(applyFallbackSnapshot, 3500);
})();
