(() => {
  'use strict';

  const query = new URLSearchParams(window.location.search);
  if (query.get('phase5Internal') !== '1' || window.parent === window) return;

  const text = (value) => String(value ?? '').trim();
  let lastModContext = null;

  function decodeContext() {
    try {
      const raw = query.get('ctx') || '';
      return raw ? JSON.parse(atob(raw.replace(/-/g, '+').replace(/_/g, '/'))) : {};
    } catch (_) { return {}; }
  }

  function currentKindAndId() {
    const route = query.get('route') || '';
    const ctx = decodeContext();
    const state = window.__DWSYNC_STATE__ || {};
    if (route === 'server-detail' || ctx.selectedServerWorldId) {
      return {
        kind: 'server',
        id: text(ctx.selectedServerWorldId || state?.server?.active_world_id || state?.server?.runtime?.active_profile_id || state?.server_profiles?.[0]?.id),
      };
    }
    return {
      kind: 'local',
      id: text(ctx.selectedWorldId || state?.client?.active_private_world_id || state?.client?.live_world_id || state?.client?.private_worlds?.[0]?.id),
    };
  }

  function parentExplorer() {
    try { return window.parent?.__DWSYNC_INTERNAL_WINDOWS__?.openExplorer; }
    catch (_) { return null; }
  }

  document.addEventListener('contextmenu', (event) => {
    const row = event.target.closest?.('.mod-row, .config-file-row, [data-sp-tags], [data-mod-tags]');
    const single = row?.querySelector?.('[data-sp-tags]') || event.target.closest?.('[data-sp-tags]');
    const server = row?.querySelector?.('[data-mod-tags]') || event.target.closest?.('[data-mod-tags]');
    const key = text(single?.dataset?.spTags || server?.dataset?.modTags);
    if (key) lastModContext = { kind: single ? 'local' : 'server', key };
  }, true);

  document.addEventListener('click', (event) => {
    const target = event.target.closest?.('button,[role="menuitem"]');
    if (!target) return;
    const openExplorer = parentExplorer();
    if (typeof openExplorer !== 'function') return;

    if (target.dataset.action === 'open' && lastModContext) {
      const context = currentKindAndId();
      const mod = lastModContext;
      lastModContext = null;
      if (!context.id) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      target.closest('.context-menu')?.remove();
      openExplorer(mod.kind || context.kind, context.id, mod.key);
    }
  }, true);
})();
