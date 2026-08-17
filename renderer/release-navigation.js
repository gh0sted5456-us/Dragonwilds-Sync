(() => {
  'use strict';

  // Release navigation cleanup. The underlying V2 routes/RPCs stay intact for
  // backwards compatibility; this layer removes legacy menu entry points and
  // presents their successor names consistently in the shipped client.
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  let recommendationRows = null;
  let recommendationLoading = null;
  let recommendationLoadedAt = 0;

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

  async function loadRecommendations() {
    if (recommendationRows && Date.now() - recommendationLoadedAt < 5 * 60 * 1000) return recommendationRows;
    if (recommendationLoading) return recommendationLoading;
    if (!window.dragonwilds?.invoke) return [];
    recommendationLoading = window.dragonwilds.invoke('application.recommended_mods.refresh', {})
      .then((response) => {
        const state = response?.state || response;
        const config = state?.application?.recommended_mods || response?.recommended_mods || {};
        recommendationRows = Array.isArray(response?.mods) ? response.mods : (Array.isArray(config.mods) ? config.mods : []);
        recommendationLoadedAt = Date.now();
        return recommendationRows;
      })
      .catch(() => recommendationRows || [])
      .finally(() => { recommendationLoading = null; });
    return recommendationLoading;
  }

  function recommendationByUrl(rows, url) {
    const key = String(url || '').trim().replace(/\/$/, '').toLowerCase();
    return rows.find((row) => String(row?.page_url || '').trim().replace(/\/$/, '').toLowerCase() === key) || null;
  }

  function attachRecommendedActions(card, row, sourceButton) {
    if (!card || card.dataset.dwsRecommendationEnhanced === '1') return;
    card.dataset.dwsRecommendationEnhanced = '1';
    const pageUrl = String(row?.page_url || sourceButton?.dataset?.recommendedOpen || '').trim();
    const downloadUrl = String(row?.download_url || '').trim();

    if (row?.artwork_url) {
      const art = document.createElement('div');
      art.className = 'recommended-mod-artwork';
      const img = document.createElement('img');
      img.src = String(row.artwork_url);
      img.alt = '';
      img.loading = 'lazy';
      img.referrerPolicy = 'no-referrer';
      img.addEventListener('error', () => art.remove(), { once: true });
      art.appendChild(img);
      card.insertBefore(art, card.firstChild);
    } else {
      // Preserve the horizontal layout even when a provider blocks anonymous
      // artwork requests; the card simply collapses back to its text content.
      card.style.gridTemplateColumns = 'minmax(0, 1fr) auto';
    }

    const content = [...card.children].find((node) => node.tagName === 'DIV' && !node.classList.contains('recommended-mod-artwork'));
    if (content && row?.description && !content.querySelector('.recommended-mod-summary')) {
      const summary = document.createElement('div');
      summary.className = 'recommended-mod-summary';
      summary.textContent = String(row.description);
      content.appendChild(summary);
    }

    const actions = document.createElement('div');
    actions.className = 'recommended-mod-actions';
    if (sourceButton) {
      sourceButton.textContent = 'View Details';
      sourceButton.title = 'Open this mod page in the Dragonwilds Sync browser';
      actions.appendChild(sourceButton);
    }
    if (downloadUrl) {
      const download = document.createElement('button');
      download.type = 'button';
      download.className = 'btn primary compact-btn';
      download.textContent = 'Download';
      download.title = 'Open the curator-provided direct archive in the managed in-app browser';
      download.addEventListener('click', (event) => {
        event.preventDefault(); event.stopPropagation();
        window.dragonwilds?.openInAppBrowser?.(downloadUrl);
      });
      actions.appendChild(download);
    }
    if (actions.childElementCount) card.appendChild(actions);

    // Right-click is a fast details gesture, matching World placard behavior.
    if (pageUrl) {
      card.title = 'Right-click to view mod details';
      card.addEventListener('contextmenu', (event) => {
        event.preventDefault();
        window.dragonwilds?.openInAppBrowser?.(pageUrl);
      });
    }
  }

  async function enhanceRecommendedMods(root = document) {
    const cards = [...root.querySelectorAll('.recommended-mod-card')].filter((card) => card.dataset.dwsRecommendationEnhanced !== '1');
    if (!cards.length) return;
    const rows = await loadRecommendations();
    for (const card of cards) {
      const sourceButton = card.querySelector('[data-recommended-open]');
      const url = String(sourceButton?.dataset?.recommendedOpen || '').trim();
      const row = recommendationByUrl(rows, url) || { page_url: url };
      attachRecommendedActions(card, row, sourceButton);
    }
  }

  function applyNavigationCleanup(root = document) {
    // The old Shared Worlds/static-feed and External Declaration surfaces were
    // superseded by Worlds discovery/import and Server Management respectively.
    root.querySelectorAll('[data-route="shared-worlds"], [data-nav-route="shared-worlds"], [data-settings-tab="external"]').forEach(hideLegacyEntry);

    // Legacy sub-tabs can survive in imported/pre-release state. Keep their RPCs
    // available for migration, but do not expose a second settings hierarchy.
    root.querySelectorAll('[data-external-tab]').forEach(hideLegacyEntry);

    // The top-level Sync workspace is now the consolidated Server Management
    // surface. It still owns Website/Directory and permission-scoped remote
    // administration; hosted Worlds remain reachable from Worlds.
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

    // User-facing terminology: WebHost remains the implementation name in logs
    // and Help, while the ordinary control surface is Website & Directory.
    root.querySelectorAll('button, [role="tab"], .settings-nav button, .tabs button').forEach((node) => {
      const text = normalize(node.textContent);
      if (text === 'webhost' || text === 'web hosting') node.textContent = 'Website & Directory';
      if (text === 'remote server' || text === 'remote server admin') node.textContent = 'Remote Users & Access';
    });

    // Keep Nexus account integration intentionally hidden in the release UI.
    // Public mod-page links/artwork are unaffected.
    root.querySelectorAll('[data-nexus-account], [data-nexus-login], #nexus-account-panel, #nexus-auth-panel, .nexus-account-settings').forEach(hideLegacyEntry);

    // Explain the successor home when migration-only legacy views are restored.
    root.querySelectorAll('h1,h2,h3,.page-title,.panel-title').forEach((node) => {
      if (normalize(node.textContent) === 'shared worlds') replaceText(node, 'Shared Worlds', 'Worlds · Imported & Shared');
      if (normalize(node.textContent) === 'external declaration') replaceText(node, 'External Declaration', 'Server Management');
      if (normalize(node.textContent) === 'creator recommended mods') node.textContent = 'Dragonwilds Sync Recommended Mods';
    });

    void enhanceRecommendedMods(root);
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
