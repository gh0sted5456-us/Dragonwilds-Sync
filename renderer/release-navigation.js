(() => {
  'use strict';

  // Release navigation cleanup. The underlying V2 routes/RPCs stay intact for
  // backwards compatibility; this layer removes legacy menu entry points and
  // presents their successor names consistently in the shipped client.
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();

  function hideLegacyEntry(node) {
    if (!node || node.dataset?.dwsLegacyHidden === '1') return;
    node.dataset.dwsLegacyHidden = '1';
    node.hidden = true;
    node.setAttribute('aria-hidden', 'true');
    node.setAttribute('tabindex', '-1');
  }

  function replaceText(node, from, to) {
    if (!node || !node.textContent) return;
    const value = node.textContent;
    if (value.includes(from)) node.textContent = value.replace(from, to);
  }

  function applyNavigationCleanup(root = document) {
    // The old Shared Worlds/static-feed and External Declaration surfaces were
    // superseded by Worlds discovery/import and Server Management respectively.
    root.querySelectorAll('[data-route="shared-worlds"], [data-nav-route="shared-worlds"], [data-settings-tab="external"]').forEach(hideLegacyEntry);

    // Legacy sub-tabs can survive in imported/pre-release state. Keep their RPCs
    // available for migration, but do not expose a second settings hierarchy.
    root.querySelectorAll('[data-external-tab]').forEach(hideLegacyEntry);

    // The top-level Sync workspace is now the consolidated Server Management
    // surface. It still owns WebHost/public-directory and permission-scoped
    // remote administration; actual hosted Worlds remain reachable from Worlds.
    root.querySelectorAll('aside.sidebar button, aside.sidebar [role="button"]').forEach((node) => {
      const text = normalize(node.textContent);
      if (text === 'sync' || text.endsWith(' sync')) {
        const label = [...node.childNodes].find((child) => child.nodeType === Node.TEXT_NODE && normalize(child.textContent) === 'sync');
        if (label) label.textContent = 'Server Management';
        else {
          const candidates = node.querySelectorAll('span, strong, div');
          for (const candidate of candidates) {
            if (normalize(candidate.textContent) === 'sync') { candidate.textContent = 'Server Management'; break; }
          }
        }
        node.setAttribute('aria-label', 'Server Management');
        node.title = 'Server Management';
      }
    });

    // User-facing terminology: WebHost is an implementation name. Keep it in
    // diagnostics/help where useful, but use Website & Directory for controls.
    root.querySelectorAll('button, [role="tab"], .settings-nav button, .tabs button').forEach((node) => {
      const text = normalize(node.textContent);
      if (text === 'webhost' || text === 'web hosting') {
        node.textContent = text === 'webhost' ? 'Website & Directory' : 'Website & Directory';
      }
      if (text === 'remote server' || text === 'remote server admin') {
        node.textContent = 'Remote Users & Access';
      }
    });

    // Keep Nexus account integration intentionally hidden in the release UI.
    // Per-mod Nexus URLs and Recommended Mods links remain usable; this only
    // prevents account/login controls from becoming a first-class surface.
    root.querySelectorAll('[data-nexus-account], [data-nexus-login], #nexus-account-panel, #nexus-auth-panel').forEach(hideLegacyEntry);

    // Explain the successor home when an old migration-only Shared Worlds view
    // is restored from persisted renderer state and happens to render visibly.
    root.querySelectorAll('h1,h2,h3,.page-title,.panel-title').forEach((node) => {
      if (normalize(node.textContent) === 'shared worlds') replaceText(node, 'Shared Worlds', 'Worlds · Imported & Shared');
      if (normalize(node.textContent) === 'external declaration') replaceText(node, 'External Declaration', 'Server Management');
    });
  }

  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      applyNavigationCleanup(document);
    });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule, { once: true });
  else schedule();

  // app.js is a renderer-driven SPA and replaces large DOM sections on every
  // route/state update. Re-apply only after mutation bursts, not per mutation.
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
})();
