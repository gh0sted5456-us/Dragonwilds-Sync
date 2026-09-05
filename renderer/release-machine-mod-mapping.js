(() => {
  'use strict';

  const api = window.dragonwilds;
  if (!api?.invoke || !api?.pickDirectory) return;
  const text = (value) => String(value ?? '').trim();
  const lanes = [
    ['ue4ss', 'UE4SS Mods', 'Where profile UE4SS mods are deployed for this installation.'],
    ['runeschema', 'RuneSchema Mods', 'Where profile RuneSchema child mods are deployed for this installation.'],
    ['paks', 'PAKs / ~mods', 'Where profile PAK payloads are deployed for this installation.'],
  ];
  let statusCache = null;
  let rendering = false;
  let customLocations = null;
  // Fix for the reported "map-pasting doesn't persist" bug: this panel is
  // rebuilt (shell.innerHTML replaced) on every DOM mutation anywhere in the
  // app via the MutationObserver below, using values from statusCache -- not
  // whatever the user just typed or pasted. Any unrelated UI activity (a
  // toast, another card's poll-driven refresh, console output) was enough to
  // silently discard an unsaved paste before "Save mapped paths" was ever
  // clicked. Track which inputs currently hold unsaved edits so a rebuild
  // can carry those exact values forward instead of overwriting them with
  // stale cached data.
  const dirty = new Set(); // keys of the form `${role}:${lane}`

  function dirtyKey(role, lane) { return `${role}:${lane}`; }

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  function currentState() {
    return (window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object') ? window.__DWSYNC_STATE__ : {};
  }

  async function loadStatus(force = false) {
    if (!force && statusCache) return statusCache;
    statusCache = await api.invoke('application.machine_paths.get', { force: !!force });
    return statusCache || {};
  }

  function roleMarkup(role, row) {
    const label = role === 'server' ? 'Dedicated Server' : 'Player';
    const ready = row?.ready === true;
    const saved = currentState()?.application?.machine_mod_paths?.[role] || {};
    const fields = lanes.map(([lane, title, help]) => {
      const defaultValue = text(row?.mod_defaults?.[lane]);
      const mapped = text(row?.mod_overrides?.[lane] || saved?.[lane]);
      const value = mapped || text(row?.[lane]) || defaultValue;
      return `<label class="machine-mod-map-row" data-machine-mod-lane="${lane}">
        <span><strong>${esc(title)}</strong><small>${esc(help)}</small></span>
        <div class="machine-mod-map-input"><input id="machine-map-${role}-${lane}" value="${esc(value)}" data-default="${esc(defaultValue)}" data-mapped="${esc(mapped)}" /><button type="button" class="secondary" data-machine-map-browse="${role}:${lane}">Browse</button></div>
      </label>`;
    }).join('');
    const runtimePaths = ready ? `<div class="machine-runtime-paths"><strong>Resolved loader layout</strong><small>Game root: ${esc(row.game_root || '')}</small><small>Bootstrap: ${esc(row.ue4ss_bootstrap || '')}</small><small>UE4SS root: ${esc(row.ue4ss_root || '')}</small>${role === 'server' ? `<small>Dedicated loader: ${esc(row.server_loader || '')}</small>` : ''}</div>` : '';
    return `<section class="machine-mod-map-role" data-machine-map-role="${role}">
      <div class="machine-mod-map-heading"><div><strong>${label} mod destinations</strong><small>${ready ? `Installation: ${esc(row.game_root || row.install_root || '')}` : esc(row?.error || 'Configure the executable and Saved directory first.')}</small></div><span class="badge ${ready ? 'ok' : 'warn'}">${ready ? 'MAPPED' : 'SETUP REQUIRED'}</span></div>
      ${runtimePaths}${fields}
      <div class="machine-mod-map-actions"><button type="button" class="secondary" data-machine-map-defaults="${role}">Use detected defaults</button><button type="button" class="primary" data-machine-map-save="${role}">Save mapped paths</button></div>
      <p class="hint" data-machine-map-note="${role}">${ready ? 'These are deployment targets only. The selected World profile Mods folder remains the content source of truth.' : 'Link the executable and Saved directory above first.'}</p>
    </section>`;
  }

  function customLocationsMarkup() {
    const rows = (customLocations || []).map((row, index) => `<div class="machine-custom-path-row" data-machine-custom-index="${index}">
      <select aria-label="Location scope"><option value="shared" ${row.role === 'shared' ? 'selected' : ''}>Shared</option><option value="player" ${row.role === 'player' ? 'selected' : ''}>Player</option><option value="server" ${row.role === 'server' ? 'selected' : ''}>Server</option></select>
      <input data-machine-custom-label value="${esc(row.label)}" placeholder="Name (for example: Config exports)" aria-label="Location name" />
      <input data-machine-custom-path value="${esc(row.path)}" placeholder="Choose a folder" aria-label="Folder path" />
      <button type="button" class="secondary" data-machine-custom-browse="${index}">Browse</button>
      <button type="button" class="secondary" data-machine-custom-remove="${index}" aria-label="Remove location">Remove</button>
    </div>`).join('');
    return `<section class="machine-custom-paths"><div class="machine-mod-map-heading"><div><strong>Additional managed locations</strong><small>Add named folder references for tools or content introduced later. These are saved with this computer, but are not treated as mod deployment lanes until a feature explicitly uses them.</small></div><button type="button" class="secondary" data-machine-custom-add>Add Location</button></div>${rows || '<p class="hint">No additional locations have been added.</p>'}<div class="machine-mod-map-actions"><button type="button" class="primary" data-machine-custom-save>Save Additional Locations</button></div><p class="hint" data-machine-custom-note></p></section>`;
  }

  function ensureStyles() {
    if (document.querySelector('#machine-mod-mapping-style')) return;
    const style = document.createElement('style');
    style.id = 'machine-mod-mapping-style';
    style.textContent = `
      .machine-mod-map-shell{margin-top:18px;padding-top:16px;border-top:1px solid var(--border,#39404b)}
      .machine-mod-map-shell>header{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:12px}
      .machine-mod-map-shell>header p{margin:4px 0 0;max-width:760px;opacity:.78}
      .machine-mod-map-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}
      .machine-mod-map-role{border:1px solid var(--border,#39404b);border-radius:12px;padding:14px;background:color-mix(in srgb,var(--surface,#181b21) 94%,transparent)}
      .machine-mod-map-heading{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;margin-bottom:12px}.machine-mod-map-heading small{display:block;margin-top:3px;opacity:.72;word-break:break-all}
      .machine-mod-map-row{display:block;margin:10px 0}.machine-mod-map-row>span{display:block;margin-bottom:5px}.machine-mod-map-row small{display:block;opacity:.68;margin-top:2px}
      .machine-runtime-paths{display:grid;gap:4px;margin:10px 0 14px;padding:10px;border-radius:8px;background:var(--panel-2,#111516)}.machine-runtime-paths small{word-break:break-all;opacity:.76}
      .machine-mod-map-input{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.machine-mod-map-input input{width:100%;min-width:0}
      .machine-mod-map-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}.machine-mod-map-role .hint{margin:9px 0 0;font-size:.84em;opacity:.72}
      .machine-custom-paths{margin-top:14px;border:1px solid var(--border,#39404b);border-radius:12px;padding:14px}.machine-custom-path-row{display:grid;grid-template-columns:110px minmax(150px,.7fr) minmax(240px,1.5fr) auto auto;gap:8px;margin-top:8px}.machine-custom-path-row input,.machine-custom-path-row select{min-width:0;width:100%}@media(max-width:900px){.machine-custom-path-row{grid-template-columns:1fr auto}.machine-custom-path-row input[data-machine-custom-path]{grid-column:1/-1}}
    `;
    document.head.appendChild(style);
  }

  async function render() {
    if (rendering) return;
    const card = document.querySelector('#machine-paths-card');
    if (!card) return;
    rendering = true;
    try {
      // Preserve unsaved additional-location edits across the same global
      // repaint cycle that affects the fixed deployment lanes.
      if (customLocations !== null && card.querySelector('[data-machine-custom-index]')) syncCustomLocationsFromDom();
      ensureStyles();
      const status = await loadStatus();
      if (customLocations === null) {
        const application = currentState().application || {};
        customLocations = Array.isArray(application.machine_custom_paths) ? application.machine_custom_paths.map((row) => ({ role: text(row?.role) || 'shared', label: text(row?.label), path: text(row?.path) })) : [];
      }
      let shell = card.querySelector('[data-machine-mod-mapping]');
      if (!shell) {
        shell = document.createElement('div');
        shell.dataset.machineModMapping = '1';
        shell.className = 'machine-mod-map-shell';
        card.appendChild(shell);
      }
      // Capture any unsaved edits before the rebuild so they survive it.
      const preserved = {};
      for (const role of ['player', 'server']) {
        for (const [lane] of lanes) {
          const key = dirtyKey(role, lane);
          if (!dirty.has(key)) continue;
          const input = document.querySelector(`#machine-map-${role}-${lane}`);
          if (input) preserved[key] = input.value;
        }
      }
      shell.innerHTML = `<header><div><strong>Installation paths</strong><p>Profile storage is the library. These three mapped lanes are the live destinations used when a profile is deployed to the player or server installation.</p></div></header><div class="machine-mod-map-grid">${roleMarkup('player', status.player || {})}${roleMarkup('server', status.server || {})}</div>${customLocationsMarkup()}`;
      for (const [key, value] of Object.entries(preserved)) {
        const [role, lane] = key.split(':');
        const input = document.querySelector(`#machine-map-${role}-${lane}`);
        if (input && !input.disabled) input.value = value;
      }
    } catch (error) {
      console.warn('Could not render machine mod mapping', error);
    } finally {
      rendering = false;
    }
  }

  function mappingFor(role) {
    const result = {};
    for (const [lane] of lanes) result[lane] = text(document.querySelector(`#machine-map-${role}-${lane}`)?.value);
    return result;
  }

  function note(role, message, isError = false) {
    const node = document.querySelector(`[data-machine-map-note="${role}"]`);
    if (!node) return;
    node.textContent = message;
    node.dataset.tone = isError ? 'error' : 'success';
  }

  async function save(role) {
    try {
      const result = await api.invoke('application.machine_paths.mod_paths.save', { role, mod_paths: mappingFor(role) });
      if (result?.state && typeof result.state === 'object') {
        window.__DWSYNC_STATE__ = result.state;
        window.dispatchEvent(new CustomEvent('dragonwilds:state-updated', { detail: result.state }));
      }
      for (const [lane] of lanes) dirty.delete(dirtyKey(role, lane));
      statusCache = null;
      await loadStatus(true);
      note(role, 'Mapped installation paths saved. Future profile deployment uses these destinations.');
      await render();
    } catch (error) {
      note(role, text(error?.message || error || 'Could not save mapped paths.'), true);
    }
  }

  function syncCustomLocationsFromDom() {
    customLocations = [...document.querySelectorAll('[data-machine-custom-index]')].map((row) => ({
      role: text(row.querySelector('select')?.value) || 'shared',
      label: text(row.querySelector('[data-machine-custom-label]')?.value),
      path: text(row.querySelector('[data-machine-custom-path]')?.value),
    }));
  }

  async function saveCustomLocations() {
    const note = document.querySelector('[data-machine-custom-note]');
    try {
      syncCustomLocationsFromDom();
      if (customLocations.some((row) => !row.label || !row.path)) throw new Error('Every additional location needs both a name and a folder.');
      const result = await api.invoke('application.update', { machine_custom_paths: customLocations });
      if (result?.state && typeof result.state === 'object') {
        window.__DWSYNC_STATE__ = result.state;
        window.dispatchEvent(new CustomEvent('dragonwilds:state-updated', { detail: result.state }));
      }
      if (note) { note.textContent = 'Additional locations saved.'; note.dataset.tone = 'success'; }
    } catch (error) {
      if (note) { note.textContent = text(error?.message || error || 'Could not save additional locations.'); note.dataset.tone = 'error'; }
    }
  }

  document.addEventListener('click', async (event) => {
    const addCustom = event.target.closest('[data-machine-custom-add]');
    if (addCustom) { syncCustomLocationsFromDom(); customLocations.push({ role: 'shared', label: '', path: '' }); await render(); return; }
    const removeCustom = event.target.closest('[data-machine-custom-remove]');
    if (removeCustom) { syncCustomLocationsFromDom(); customLocations.splice(Number(removeCustom.dataset.machineCustomRemove), 1); await render(); return; }
    const browseCustom = event.target.closest('[data-machine-custom-browse]');
    if (browseCustom) {
      syncCustomLocationsFromDom();
      const index = Number(browseCustom.dataset.machineCustomBrowse);
      const picked = await api.pickDirectory('Choose additional managed location', customLocations[index]?.path || '');
      if (picked && customLocations[index]) customLocations[index].path = picked;
      await render(); return;
    }
    if (event.target.closest('[data-machine-custom-save]')) { await saveCustomLocations(); return; }
    const browse = event.target.closest('[data-machine-map-browse]');
    if (browse) {
      const [role, lane] = text(browse.dataset.machineMapBrowse).split(':');
      const input = document.querySelector(`#machine-map-${role}-${lane}`);
      if (!input) return;
      const picked = await api.pickDirectory(`Choose ${role === 'server' ? 'Server' : 'Player'} ${lane} mod destination`, text(input.value));
      if (picked) { input.value = picked; dirty.add(dirtyKey(role, lane)); }
      return;
    }
    const defaults = event.target.closest('[data-machine-map-defaults]');
    if (defaults) {
      const role = text(defaults.dataset.machineMapDefaults);
      for (const [lane] of lanes) {
        const input = document.querySelector(`#machine-map-${role}-${lane}`);
        if (input) { input.value = text(input.dataset.default); dirty.add(dirtyKey(role, lane)); }
      }
      note(role, 'Detected defaults loaded. Save to make them explicit.');
      return;
    }
    const saveButton = event.target.closest('[data-machine-map-save]');
    if (saveButton) await save(text(saveButton.dataset.machineMapSave));
  }, true);

  // Typing OR pasting (Ctrl+V, middle-click paste, drag-drop) into a mapping
  // field all fire 'input'. Mark the field dirty on the first such event so a
  // rebuild triggered before Save is clicked preserves it instead of
  // silently reverting to the last-known/detected value.
  document.addEventListener('input', (event) => {
    const row = event.target.closest?.('[data-machine-mod-lane]');
    if (!row) return;
    const role = row.closest('[data-machine-map-role]')?.dataset.machineMapRole;
    const lane = row.dataset.machineModLane;
    if (role && lane) dirty.add(dirtyKey(role, lane));
  }, true);

  const observer = new MutationObserver(() => void render());
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('dragonwilds:state-updated', () => { statusCache = null; void render(); });
  window.addEventListener('DOMContentLoaded', () => void render(), { once: true });
  void render();
})();
