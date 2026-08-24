(() => {
  'use strict';

  // Release navigation cleanup. The underlying V2 routes/RPCs stay intact for
  // backwards compatibility; this layer removes legacy menu entry points and
  // presents their successor names consistently in the shipped client.
  //
  // Navigation-critical cleanup is intentionally separate from decorative
  // enhancement. The app root receives a targeted native MutationObserver so
  // menu visibility/names settle in the same microtask as app.js render and
  // before Chromium paints. Broader recommendation/presentation work remains
  // on the shared idle-time coordinator installed by release-performance.js.
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

  function matchingNodes(root, selector) {
    if (!root || root.nodeType !== Node.ELEMENT_NODE) return [];
    const rows = root.matches?.(selector) ? [root] : [];
    return rows.concat([...root.querySelectorAll(selector)]);
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

  function applyNavigationCritical(root = document) {
    matchingNodes(root, '[data-route="shared-worlds"], [data-nav-route="shared-worlds"], [data-settings-tab="external"]').forEach(hideLegacyEntry);
    matchingNodes(root, '[data-external-tab]').forEach(hideLegacyEntry);
    matchingNodes(root, '#detach-private-world, #detach-server-world').forEach((button)=>{
      if(button.textContent!=='▣ Open Placard')button.textContent='▣ Open Placard';
      button.title='Open an application-owned placard window without reloading Dragonwilds Sync';
    });

    matchingNodes(root, 'button, [role="tab"], .settings-nav button, .tabs button').forEach((node) => {
      const text = normalize(node.textContent);
      if ((text === 'webhost' || text === 'web hosting') && node.textContent !== 'Website & Directory') node.textContent = 'Website & Directory';
      if ((text === 'remote server' || text === 'remote server admin') && node.textContent !== 'Remote Users & Access') node.textContent = 'Remote Users & Access';
    });

    matchingNodes(root, '[data-nexus-account], [data-nexus-login], #nexus-account-panel, #nexus-auth-panel, .nexus-account-settings').forEach(hideLegacyEntry);
  }

  function applyPresentationEnhancements(root = document) {
    root.querySelectorAll('h1,h2,h3,.page-title,.panel-title').forEach((node) => {
      if (normalize(node.textContent) === 'shared worlds') replaceText(node, 'Shared Worlds', 'Worlds · Imported & Shared');
      if (normalize(node.textContent) === 'external declaration') replaceText(node, 'External Declaration', 'Server Management');
      if (normalize(node.textContent) === 'creator recommended mods') node.textContent = 'Dragonwilds Sync Recommended Mods';
    });

    void enhanceRecommendedMods(root);
  }

  // Critical menu structure gets a targeted observer. release-performance.js
  // only defers documentElement-wide observers, so this callback is delivered
  // as a native MutationObserver microtask before the next browser paint.
  const appRoot = document.getElementById('app');
  if (appRoot) {
    new MutationObserver((records) => {
      const added = new Set();
      for (const record of records) {
        for (const node of record.addedNodes || []) if (node.nodeType === Node.ELEMENT_NODE) added.add(node);
      }
      for (const node of added) applyNavigationCritical(node);
    }).observe(appRoot, { childList: true, subtree: true });
    applyNavigationCritical(appRoot);
  }

  let scheduled = false;
  const scheduleEnhancements = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      applyPresentationEnhancements(document);
    });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scheduleEnhancements, { once: true });
  else scheduleEnhancements();

  // Noncritical presentation remains on the coordinated broad observer so large
  // editor/mod DOM updates do not trigger several whole-document scans per frame.
  new MutationObserver(scheduleEnhancements).observe(document.documentElement, { childList: true, subtree: true });
})();
