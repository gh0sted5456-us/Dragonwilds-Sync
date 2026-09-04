(() => {
  'use strict';

  const api = window.dragonwilds;
  if (!api?.invoke) return;

  const fresh = new Map();
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const text = (value) => String(value ?? '').trim();
  const assets = { UE4SS:'assets/platforms/ue4ss.webp', RuneSchema:'assets/platforms/runeschema.webp', Pak:'assets/platforms/paks.svg' };
  const state = () => (window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object') ? window.__DWSYNC_STATE__ : {};
  const selection = (window.__DWSYNC_PROFILE_SELECTION__ ||= { local:'', server:'' });

  function rowsFor(kind) {
    const root = state();
    return kind === 'server'
      ? (Array.isArray(root?.server_profiles) ? root.server_profiles : [])
      : (Array.isArray(root?.client?.private_worlds) ? root.client.private_worlds : (root?.client?.singleplayer ? [root.client.singleplayer] : []));
  }

  function selectedProfile(kind) {
    const rows = rowsFor(kind);
    const remembered = text(selection[kind]);
    if (remembered) {
      const found = rows.find((row) => text(row?.id) === remembered);
      if (found) return found;
    }
    const title = text(document.querySelector('.detail-hero h1')?.textContent || document.querySelector('.phase5-explorer-world strong')?.textContent);
    if (title) {
      const matching = rows.filter((row) => text(row?.name || row?.nickname) === title);
      if (matching.length === 1) {
        selection[kind] = text(matching[0]?.id);
        return matching[0];
      }
    }
    const root = state();
    const activeId = text(kind === 'server'
      ? root?.server?.active_world_id
      : (root?.client?.active_private_world_id || root?.client?.live_world_id));
    const selected = rows.find((row) => text(row?.id) === activeId) || rows[0] || null;
    if (selected?.id) selection[kind] = text(selected.id);
    return selected;
  }

  function family(row) {
    const raw = text(`${row?.group || ''} ${row?.type || ''} ${row?.kind || ''} ${row?.loader || ''}`).toLowerCase();
    if (raw.includes('rune')) return 'RuneSchema';
    if (raw.includes('pak')) return 'Pak';
    return 'UE4SS';
  }

  function familyRows(rows, wanted) { return rows.filter((row) => family(row) === wanted); }

  function ecosystemMarkup(id, rows) {
    const families = ['Pak','UE4SS','RuneSchema'].filter((name) => familyRows(rows, name).length);
    if (!families.length) return '';
    return `<div class="v3p4-ecosystems compact" data-live-mod-inventory="1" aria-label="Loaded mod frameworks">${families.map((name) => `<button type="button" class="v3p4-ecosystem" data-live-mod-family="${esc(name)}" data-live-mod-world="${esc(id)}" title="Show loaded ${esc(name)} mods"><img src="${assets[name]}" alt=""/><span>${esc(name)}</span></button>`).join('')}</div>`;
  }

  function refreshPlacards(id, rows) {
    document.querySelectorAll(`.v3p4-placard[data-world-id="${CSS.escape(id)}"], .app-world-placard[data-world-id="${CSS.escape(id)}"]`).forEach((card) => {
      card.querySelectorAll('.v3p4-ecosystems').forEach((node) => node.remove());
      const markup = ecosystemMarkup(id, rows);
      if (!markup) return;
      const mount = card.classList.contains('app-world-placard')
        ? card.querySelector('.world-card-front .world-card-body')
        : card.querySelector('.v3p4-front-live');
      mount?.insertAdjacentHTML('beforeend', markup);
    });
  }

  function notifyFresh(id, kind, rows, reconciliation = {}) {
    fresh.set(id, { rows, kind, at: Date.now(), reconciliation });
    refreshPlacards(id, rows);
  }

  function openFreshPopup(id, wanted) {
    const cached = fresh.get(id);
    if (!cached) return false;
    const rows = familyRows(cached.rows, wanted);
    const world = rowsFor(cached.kind).find((row) => text(row?.id) === id) || {};
    const worldName = text(world?.name || world?.nickname || 'World');
    const desktop = window.__DWSYNC_DESKTOP_WINDOWS__;
    const body = `<div class="modal-header v3p4-mod-window-header"><div class="v3p4-mod-window-title"><img src="${assets[wanted]}" alt=""/><span><small>PROFILE MODS · ${esc(wanted)}</small><h2>${esc(worldName)}</h2></span></div></div><div class="modal-body v3p4-mod-window-body"><h3>${esc(wanted)} profile mods</h3>${rows.length ? `<div class="v3p4-mod-list">${rows.map((row) => `<div><strong>${esc(row.name || row.display_name || row.key || 'Mod')}</strong><span>${esc(row.version || row.mod_version || 'Version not advertised')} · ${esc(String(row.distribution || row.classification || row.runtime_role || row.role || 'both').toUpperCase())}</span></div>`).join('')}</div>` : `<div class="v3p4-empty">No ${esc(wanted)} mods are recorded for this profile.</div>`}</div>`;
    if (desktop?.open) desktop.open(body, { title:`${wanted} mods · ${worldName}`, width:680, height:Math.min(760, Math.max(420, 210 + rows.length * 38)) });
    return true;
  }

  window.addEventListener('dragonwilds:mod-inventory-refreshed', (event) => {
    const detail = event?.detail || {};
    const id = text(detail.id);
    const kind = detail.kind === 'server' ? 'server' : 'local';
    const rows = Array.isArray(detail.rows) ? detail.rows : [];
    if (!id) return;
    selection[kind] = id;
    notifyFresh(id, kind, rows, detail.reconciliation || {});
  });

  window.addEventListener('dragonwilds:profile-selection-changed', (event) => {
    const detail = event?.detail || {};
    const kind = detail.kind === 'server' ? 'server' : 'local';
    const id = text(detail.id);
    if (id) selection[kind] = id;
  });

  document.addEventListener('click', (event) => {
    const familyButton = event.target.closest('[data-live-mod-family]');
    if (familyButton) {
      event.preventDefault();
      event.stopImmediatePropagation();
      openFreshPopup(text(familyButton.dataset.liveModWorld), text(familyButton.dataset.liveModFamily));
      return;
    }

    // release-profile-mod-folders.js owns explicit Refresh and emits the
    // authoritative profile inventory event consumed above. Do not issue a
    // second scan here or fall back to a title/active-profile guess.
    const button = event.target.closest('#sp-refresh, #refresh-server-inventory');
    if (button) selectedProfile(button.id === 'refresh-server-inventory' ? 'server' : 'local');
  }, true);
})();
