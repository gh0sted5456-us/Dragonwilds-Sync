(() => {
  'use strict';

  const bridge = window.dragonwilds;
  if (!bridge?.invoke) return;

  const query = new URLSearchParams(window.location.search);
  const detachedMode = query.get('detached') === '1';
  const phase5Embedded = query.get('phase5Internal') === '1';

  if (phase5Embedded) document.body.classList.add('phase5-embedded');
  if (detachedMode) return;

  const modalRoot = document.getElementById('modal-root');
  const taskbar = document.getElementById('internal-taskbar');
  if (!modalRoot || !taskbar) return;

  const text = (value) => String(value ?? '').trim();
  const escapeHtml = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const encodeContext = (value) => {
    const raw = JSON.stringify(value || {});
    return btoa(unescape(encodeURIComponent(raw))).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
  };
  const safeKey = (value) => text(value).replace(/[^A-Za-z0-9_.:-]+/g, '-').slice(0, 160) || 'window';
  const HIDDEN_MOD_NAMES = new Set([
    'dragoncore', 'dragonconnect', 'persistentdirectconnectip', 'rsdwtools', 'rsdwdevkit',
    'runeschema', 'mods.txt', 'enabled.txt', 'shared', 'bpml_genericfunctions', 'bpmodloadermod',
    'cheatmanagerenablermod', 'consolecommandsmod', 'consoleenablermod', 'keybinds',
  ]);

  let zIndex = 900;
  let sequence = 0;
  let rememberedSelection = { local: '', server: '' };
  let lastModContext = null;

  const geometryKey = (key) => `dragonwilds-sync-phase5-window:${safeKey(key)}`;

  function readGeometry(key) {
    try {
      const value = JSON.parse(localStorage.getItem(geometryKey(key)) || '{}');
      return value && typeof value === 'object' ? value : {};
    } catch (_) { return {}; }
  }

  function saveGeometry(win) {
    if (!win?.dataset.phase5Key || win.classList.contains('maximized')) return;
    const rect = win.getBoundingClientRect();
    const layer = modalRoot.getBoundingClientRect();
    const payload = {
      left: Math.max(0, Math.round(rect.left - layer.left)),
      top: Math.max(0, Math.round(rect.top - layer.top)),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    };
    try { localStorage.setItem(geometryKey(win.dataset.phase5Key), JSON.stringify(payload)); } catch (_) {}
  }

  function windowTitle(win) {
    return text(win?.querySelector('.modal-header h2')?.textContent || win?.dataset.phase5Title || 'Dragonwilds Sync');
  }

  function focusWindow(win) {
    if (!win || win.classList.contains('minimized')) return;
    modalRoot.querySelectorAll('.desktop-window').forEach((node) => node.classList.remove('focused'));
    win.classList.add('focused');
    win.style.zIndex = String(++zIndex);
    const id = win.dataset.windowId || '';
    taskbar.querySelectorAll('.internal-task-button').forEach((button) => {
      button.classList.toggle('active', button.dataset.windowId === id);
    });
  }

  function ensureTaskbarButton(win) {
    const id = win.dataset.windowId || '';
    if (!id || taskbar.querySelector(`[data-window-id="${CSS.escape(id)}"]`)) return;
    const button = document.createElement('button');
    button.className = 'internal-task-button phase5-task-button active';
    button.dataset.windowId = id;
    button.title = windowTitle(win);
    button.innerHTML = `<span class="taskbar-item-icon">▣</span><span class="taskbar-item-label">${escapeHtml(windowTitle(win))}</span>`;
    button.addEventListener('click', () => {
      win.classList.remove('minimized');
      focusWindow(win);
      button.classList.add('active');
    });
    button.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      const menu = document.createElement('div');
      menu.className = 'context-menu phase5-task-menu';
      menu.style.left = `${Math.min(event.clientX, innerWidth - 180)}px`;
      menu.style.top = `${Math.min(event.clientY, innerHeight - 100)}px`;
      menu.innerHTML = '<button data-phase5-task="restore">Restore</button><button data-phase5-task="close">Close</button>';
      document.body.appendChild(menu);
      menu.addEventListener('click', (click) => {
        const action = click.target?.dataset?.phase5Task;
        if (action === 'restore') { win.classList.remove('minimized'); focusWindow(win); }
        if (action === 'close') closeWindow(win);
        menu.remove();
      });
      const dismiss = (click) => { if (!menu.contains(click.target)) { menu.remove(); document.removeEventListener('mousedown', dismiss); } };
      setTimeout(() => document.addEventListener('mousedown', dismiss), 0);
    });
    taskbar.appendChild(button);
  }

  function closeWindow(win) {
    if (!win) return;
    saveGeometry(win);
    const id = win.dataset.windowId || '';
    win.remove();
    taskbar.querySelector(`[data-window-id="${CSS.escape(id)}"]`)?.remove();
  }

  function restoreRect(win) {
    const restore = win._phase5RestoreRect;
    if (!restore) return;
    win.style.left = `${restore.left}px`;
    win.style.top = `${restore.top}px`;
    win.style.width = `${restore.width}px`;
    win.style.height = `${restore.height}px`;
    win._phase5RestoreRect = null;
  }

  function toggleMaximize(win) {
    if (!win) return;
    if (win.classList.contains('maximized')) {
      win.classList.remove('maximized');
      restoreRect(win);
    } else {
      const rect = win.getBoundingClientRect();
      const layer = modalRoot.getBoundingClientRect();
      win._phase5RestoreRect = {
        left: rect.left - layer.left, top: rect.top - layer.top,
        width: rect.width, height: rect.height,
      };
      win.classList.add('maximized');
    }
    focusWindow(win);
  }

  function bindWindowGeometry(win) {
    const header = win.querySelector('.modal-header');
    if (!header) return;
    header.addEventListener('dblclick', (event) => {
      if (event.target.closest('.desktop-window-controls,button,input,select,a')) return;
      toggleMaximize(win);
    });
    header.addEventListener('pointerdown', (event) => {
      if (event.button !== 0 || win.classList.contains('maximized') || event.target.closest('.desktop-window-controls,button,input,select,a')) return;
      const start = win.getBoundingClientRect();
      const layer = modalRoot.getBoundingClientRect();
      const offsetX = event.clientX - start.left;
      const offsetY = event.clientY - start.top;
      const move = (pointer) => {
        const left = Math.max(0, Math.min(layer.width - 160, pointer.clientX - layer.left - offsetX));
        const top = Math.max(0, Math.min(layer.height - 44, pointer.clientY - layer.top - offsetY));
        win.style.left = `${Math.round(left)}px`;
        win.style.top = `${Math.round(top)}px`;
      };
      const up = () => {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
        saveGeometry(win);
      };
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up, { once: true });
      focusWindow(win);
      event.preventDefault();
    });
    win.addEventListener('pointerdown', () => focusWindow(win));
    const observer = new ResizeObserver(() => {
      clearTimeout(win._phase5ResizeTimer);
      win._phase5ResizeTimer = setTimeout(() => saveGeometry(win), 120);
    });
    observer.observe(win);
    win._phase5ResizeObserver = observer;
  }

  function createWindow({ key, title, subtitle = '', width = 1180, height = 800, body = '', className = '' }) {
    const normalizedKey = safeKey(key);
    const existing = modalRoot.querySelector(`.phase5-window[data-phase5-key="${CSS.escape(normalizedKey)}"]`);
    if (existing) {
      existing.classList.remove('minimized');
      focusWindow(existing);
      return existing;
    }

    const layer = modalRoot.getBoundingClientRect();
    const stored = readGeometry(normalizedKey);
    const actualWidth = Math.min(Math.max(620, Number(stored.width || width)), Math.max(620, layer.width - 20));
    const actualHeight = Math.min(Math.max(420, Number(stored.height || height)), Math.max(420, layer.height - 20));
    const stagger = (sequence++ % 8) * 24;
    const left = Math.max(6, Math.min(Number(stored.left ?? (34 + stagger)), Math.max(6, layer.width - actualWidth - 6)));
    const top = Math.max(6, Math.min(Number(stored.top ?? (28 + stagger)), Math.max(6, layer.height - actualHeight - 6)));

    const win = document.createElement('section');
    win.className = `desktop-window phase5-window focused ${className}`.trim();
    win.dataset.desktopReady = '1';
    win.dataset.phase5Key = normalizedKey;
    win.dataset.phase5Title = title;
    win.dataset.windowId = `phase5-${safeKey(normalizedKey)}-${Date.now().toString(36)}`;
    win.style.left = `${left}px`;
    win.style.top = `${top}px`;
    win.style.width = `${actualWidth}px`;
    win.style.height = `${actualHeight}px`;
    win.style.zIndex = String(++zIndex);
    win.innerHTML = `<div class="modal phase5-modal"><div class="modal-header phase5-window-header"><div class="phase5-title-copy"><img src="assets/application-icon.png" alt=""/><div><div class="eyebrow">Dragonwilds Sync</div><h2>${escapeHtml(title)}</h2>${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ''}</div></div><div class="desktop-window-controls" aria-label="Window controls"><button class="desktop-window-control" data-phase5-window="minimize" title="Minimize">—</button><button class="desktop-window-control" data-phase5-window="maximize" title="Maximize / Restore">□</button><button class="desktop-window-control close" data-phase5-window="close" title="Close">×</button></div></div><div class="modal-body phase5-window-body">${body}</div></div>`;
    modalRoot.appendChild(win);
    win.querySelector('[data-phase5-window="minimize"]')?.addEventListener('click', () => {
      win.classList.add('minimized');
      ensureTaskbarButton(win);
      taskbar.querySelector(`[data-window-id="${CSS.escape(win.dataset.windowId)}"]`)?.classList.remove('active');
    });
    win.querySelector('[data-phase5-window="maximize"]')?.addEventListener('click', () => toggleMaximize(win));
    win.querySelector('[data-phase5-window="close"]')?.addEventListener('click', () => closeWindow(win));
    bindWindowGeometry(win);
    ensureTaskbarButton(win);
    focusWindow(win);
    return win;
  }

  function routeContextFromDom(route, state) {
    if (route === 'server-detail') {
      const active = document.querySelector('[data-server-tab].active')?.dataset.serverTab || 'overview';
      return { selectedServerWorldId: resolveSelection('server', state), serverTab: active };
    }
    if (route === 'world-detail') {
      const active = document.querySelector('[data-private-tab].active')?.dataset.privateTab || 'overview';
      return { selectedWorldId: resolveSelection('local', state), privateTab: active };
    }
    if (route === 'profile') {
      return { profileTab: document.querySelector('[data-profile-tab].active')?.dataset.profileTab || 'user' };
    }
    if (route === 'settings' || route === 'webhost') {
      return { settingsTab: document.querySelector('[data-settings-tab].active')?.dataset.settingsTab || 'application' };
    }
    return {};
  }

  function routeTitle(route, state) {
    if (route === 'server-detail') {
      const id = resolveSelection('server', state);
      const row = (state?.server_profiles || []).find((item) => text(item?.id) === id);
      return row?.name ? `World · ${row.name}` : 'Hosted World';
    }
    if (route === 'world-detail') {
      const id = resolveSelection('local', state);
      const rows = state?.client?.private_worlds || [];
      const row = rows.find((item) => text(item?.id) === id);
      return row?.name ? `World · ${row.name}` : 'Local World';
    }
    if (route === 'profile') return 'Profile';
    if (route === 'worlds') return 'Worlds';
    if (route === 'webhost') return 'Sync';
    if (route === 'settings') return 'Settings';
    return 'Dragonwilds Sync';
  }

  async function stateSnapshot() {
    if (window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object') return window.__DWSYNC_STATE__;
    return bridge.invoke('state.get', {});
  }

  function resolveSelection(kind, state) {
    if (kind === 'server') {
      return text(rememberedSelection.server || state?.server?.active_world_id || state?.server?.runtime?.active_profile_id || state?.server_profiles?.[0]?.id);
    }
    return text(rememberedSelection.local || state?.client?.active_private_world_id || state?.client?.live_world_id || state?.client?.private_worlds?.[0]?.id);
  }

  function openRouteWindow(route, context = {}, options = {}) {
    const ctx = encodeContext(context);
    const title = options.title || routeTitle(route, window.__DWSYNC_STATE__ || {});
    const keyPart = context.selectedServerWorldId || context.selectedWorldId || context.profileTab || context.settingsTab || '';
    const key = `route:${route}:${keyPart}`;
    const src = `index.html?detached=1&phase5Internal=1&route=${encodeURIComponent(route)}&ctx=${encodeURIComponent(ctx)}`;
    const win = createWindow({
      key, title, subtitle: options.subtitle || 'Application-owned workspace',
      width: options.width || 1260, height: options.height || 820,
      className: 'phase5-route-window',
      body: `<iframe class="phase5-route-frame" src="${escapeHtml(src)}" title="${escapeHtml(title)}"></iframe>`,
    });
    const frame = win.querySelector('.phase5-route-frame');
    frame?.addEventListener('load', () => {
      try { frame.contentDocument?.body?.classList.add('phase5-embedded'); } catch (_) {}
    });
    return win;
  }

  function rememberSelectionFromTarget(target) {
    const server = target.closest?.('[data-server-manage], [data-server-launch], [data-server-stop], [data-server-card][data-world-id]');
    if (server) {
      rememberedSelection.server = text(server.dataset.serverManage || server.dataset.serverLaunch || server.dataset.serverStop || server.dataset.worldId);
      return;
    }
    const local = target.closest?.('[data-private-manage], [data-private-launch], [data-private-coop], [data-world-id][data-server-card="0"]');
    if (local) rememberedSelection.local = text(local.dataset.privateManage || local.dataset.privateLaunch || local.dataset.privateCoop || local.dataset.worldId);
  }

  function categoryForUnit(unit) {
    const group = `${unit?.group || ''} ${unit?.type || ''} ${unit?.kind || ''}`.toLowerCase();
    if (group.includes('runeschema')) return 'RuneSchema';
    if (group.includes('pak')) return 'Pak';
    return 'UE4SS';
  }

  function unitKey(unit) {
    return text(unit?.key || unit?.unit_key || unit?.id || unit?.name);
  }

  function userManageable(unit) {
    const name = text(unit?.name || unitKey(unit)).toLowerCase();
    if (!name || HIDDEN_MOD_NAMES.has(name)) return false;
    if (unit?.user_manageable === false) return false;
    if (text(unit?.visibility) && text(unit.visibility) !== 'user-mod') return false;
    return true;
  }

  function formatBytes(value) {
    let size = Number(value || 0);
    if (!Number.isFinite(size) || size <= 0) return '0 B';
    const units = ['B', 'KiB', 'MiB', 'GiB'];
    let index = 0;
    while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
    return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
  }

  function explorerShell(kind, id, worldName, unitKeyFilter = '') {
    const title = unitKeyFilter ? 'DRAGONWILDS SYNC EXPLORER' : 'DRAGONWILDS SYNC EXPLORER';
    const win = createWindow({
      key: `explorer:${kind}:${id}:${unitKeyFilter || 'root'}`,
      title,
      subtitle: unitKeyFilter ? `${worldName} · Mod workspace` : `${worldName} · Profile logical mod root`,
      width: 1320,
      height: 840,
      className: 'phase5-explorer-window',
      body: `<section class="phase5-explorer" data-phase5-explorer-kind="${escapeHtml(kind)}" data-phase5-explorer-id="${escapeHtml(id)}" data-phase5-unit-filter="${escapeHtml(unitKeyFilter)}"><aside class="phase5-explorer-sidebar"><div class="phase5-explorer-brand"><img src="assets/application-icon.png" alt=""/><div><strong>DRAGONWILDS SYNC</strong><span>EXPLORER</span></div></div><div class="phase5-explorer-world"><small>WORLD PROFILE</small><strong>${escapeHtml(worldName)}</strong><span>${kind === 'server' ? 'Dedicated' : 'Local / Co-Op'}</span></div><nav class="phase5-explorer-categories" aria-label="Mod categories"><button class="active" data-phase5-category="All">All Mods</button><button data-phase5-category="UE4SS">UE4SS</button><button data-phase5-category="RuneSchema">RuneSchema</button><button data-phase5-category="Pak">Pak</button></nav><div class="phase5-explorer-policy"><strong>User-manageable only</strong><span>DragonCore, DragonConnect, RuneSchema framework, Toolkit/DevKit and generated controls stay hidden.</span></div></aside><main class="phase5-explorer-main"><div class="phase5-explorer-toolbar"><div><div class="eyebrow">Profile logical mod root</div><h3>${escapeHtml(unitKeyFilter || worldName)}</h3></div><label class="phase5-explorer-search"><span>⌕</span><input class="field" data-phase5-search placeholder="Search mods and files…"/></label><button class="btn ghost" data-phase5-refresh>Refresh</button></div><div class="phase5-explorer-workspace"><section class="phase5-explorer-list" data-phase5-unit-list><div class="phase5-explorer-loading"><div class="spinner"></div><strong>Loading managed mod index…</strong><span>Using the cached World inventory first.</span></div></section><section class="phase5-explorer-preview" data-phase5-preview><div class="empty-state"><strong>Select a mod</strong><span>Files load only when you open a mod.</span></div></section></div><footer class="phase5-explorer-footer"><span>Managed profile root · writes stay inside the selected mod</span><button class="btn primary" data-phase5-save-file disabled>Save File</button></footer></main></section>`,
    });
    loadExplorer(win, kind, id, unitKeyFilter).catch((error) => renderExplorerError(win, error));
    return win;
  }

  async function inventoryFor(kind, id, refresh = false) {
    if (kind === 'server') {
      const response = await bridge.invoke('server.world.inventory', { id, rescan: refresh });
      return response?.units || response?.mods || response?.inventory || [];
    }
    const response = await bridge.invoke('singleplayer.inventory', { profile_id: id, rescan: refresh });
    return response?.units || response?.mods || response?.inventory || [];
  }

  function unitRowMarkup(unit) {
    const category = categoryForUnit(unit);
    const key = unitKey(unit);
    const name = text(unit?.name || key || 'Mod');
    const count = Number(unit?.file_count || unit?.files || 0);
    const size = Number(unit?.size || unit?.size_bytes || 0);
    const role = text(unit?.runtime_role || unit?.role || 'BOTH').toUpperCase();
    const icon = category === 'RuneSchema' ? '◇' : (category === 'Pak' ? '▰' : '▦');
    return `<button class="phase5-unit-row" data-phase5-unit="${escapeHtml(key)}" data-phase5-category-name="${escapeHtml(category)}" data-phase5-unit-name="${escapeHtml(name)}"><span class="phase5-unit-icon ${category.toLowerCase()}">${icon}</span><span><strong>${escapeHtml(name)}</strong><small>${escapeHtml(category)}${role ? ` · ${escapeHtml(role)}` : ''}${count ? ` · ${count} file${count === 1 ? '' : 's'}` : ''}</small></span><b>${size ? formatBytes(size) : '›'}</b></button>`;
  }

  async function loadExplorer(win, kind, id, unitKeyFilter = '', refresh = false) {
    const host = win.querySelector('.phase5-explorer');
    if (!host) return;
    const state = await stateSnapshot();
    const rows = (await inventoryFor(kind, id, refresh)).filter(userManageable);
    const filterKey = text(unitKeyFilter);
    const units = filterKey ? rows.filter((unit) => unitKey(unit) === filterKey || text(unit?.name) === filterKey) : rows;
    host._phase5Units = units;
    host._phase5Category = filterKey ? categoryForUnit(units[0] || {}) : 'All';
    host._phase5Query = '';
    renderUnits(host);
    host.querySelector('[data-phase5-refresh]')?.addEventListener('click', () => loadExplorer(win, kind, id, unitKeyFilter, true));
    host.querySelector('[data-phase5-search]')?.addEventListener('input', (event) => { host._phase5Query = text(event.target.value).toLowerCase(); renderUnits(host); });
    host.querySelectorAll('[data-phase5-category]').forEach((button) => button.addEventListener('click', () => {
      host._phase5Category = button.dataset.phase5Category || 'All';
      host.querySelectorAll('[data-phase5-category]').forEach((node) => node.classList.toggle('active', node === button));
      renderUnits(host);
    }));
    if (filterKey && units[0]) setTimeout(() => host.querySelector('[data-phase5-unit]')?.click(), 0);
    if (!filterKey && !units.length) {
      host.querySelector('[data-phase5-unit-list]').innerHTML = '<div class="empty-state"><strong>No user-manageable mods in this profile.</strong><span>Hidden core/runtime components are intentionally not shown.</span></div>';
    }
    window.__DWSYNC_PHASE5_STATE__ = { ...(window.__DWSYNC_PHASE5_STATE__ || {}), lastExplorer: { kind, id, count: units.length, stateSeen: Boolean(state) } };
  }

  function renderUnits(host) {
    const category = host._phase5Category || 'All';
    const queryText = host._phase5Query || '';
    const rows = (host._phase5Units || []).filter((unit) => {
      if (category !== 'All' && categoryForUnit(unit) !== category) return false;
      if (!queryText) return true;
      return `${unit?.name || ''} ${unitKey(unit)} ${categoryForUnit(unit)}`.toLowerCase().includes(queryText);
    });
    const list = host.querySelector('[data-phase5-unit-list]');
    if (!list) return;
    list.innerHTML = rows.map(unitRowMarkup).join('') || '<div class="empty-state compact"><strong>No matching mods.</strong></div>';
    list.querySelectorAll('[data-phase5-unit]').forEach((button) => button.addEventListener('click', async () => {
      list.querySelectorAll('[data-phase5-unit]').forEach((node) => node.classList.toggle('selected', node === button));
      const unit = (host._phase5Units || []).find((row) => unitKey(row) === button.dataset.phase5Unit);
      if (unit) await loadUnitFiles(host, unit);
    }));
  }

  async function filesFor(kind, id, key) {
    if (kind === 'server') {
      const response = await bridge.invoke('server.world.config.list', { id });
      return (response?.configs || response?.files || []).filter((file) => text(file?.unit_key) === text(key));
    }
    const response = await bridge.invoke('singleplayer.mod.files', { key, profile_id: id, tree: true });
    return response?.files || [];
  }

  function folderName(path, fallback) {
    const normalized = text(path).replaceAll('\\', '/');
    const index = normalized.lastIndexOf('/');
    return index > 0 ? normalized.slice(0, index) : fallback;
  }

  function fileEditable(file) {
    if (file?.editable === false) return false;
    const path = text(file?.relative_path || file?.name).toLowerCase();
    return /\.(jsonc?|lua|ini|cfg|txt|md|toml|yaml|yml)$/i.test(path);
  }

  async function loadUnitFiles(host, unit) {
    const preview = host.querySelector('[data-phase5-preview]');
    const kind = host.dataset.phase5ExplorerKind;
    const id = host.dataset.phase5ExplorerId;
    const key = unitKey(unit);
    const name = text(unit?.name || key);
    preview.innerHTML = '<div class="phase5-explorer-loading"><div class="spinner"></div><strong>Loading mod files…</strong><span>Only this mod is being resolved.</span></div>';
    try {
      const files = await filesFor(kind, id, key);
      const groups = new Map();
      files.forEach((file) => {
        const group = folderName(file.relative_path || file.name, name);
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(file);
      });
      const tree = [...groups.entries()].map(([folder, entries]) => `<section class="phase5-file-group"><h4>/${escapeHtml(folder)}</h4>${entries.map((file) => `<button class="phase5-file-row ${fileEditable(file) ? '' : 'readonly'}" data-phase5-file="${escapeHtml(file.relative_path || file.name || '')}"><span>${fileEditable(file) ? '⌘' : '◇'}</span><span><strong>${escapeHtml(file.name || String(file.relative_path || '').split(/[\\/]/).pop() || 'File')}</strong><small>${escapeHtml(file.relative_path || file.name || '')}${file.size ? ` · ${formatBytes(file.size)}` : ''}</small></span><b>${fileEditable(file) ? 'EDIT' : 'VIEW'}</b></button>`).join('')}</section>`).join('');
      preview.innerHTML = `<div class="phase5-mod-heading"><div><div class="eyebrow">${escapeHtml(categoryForUnit(unit))}</div><h3>${escapeHtml(name)}</h3><p>${escapeHtml(text(unit?.runtime_role || unit?.role || 'BOTH').toUpperCase())} · profile-scoped</p></div><span>${files.length} file${files.length === 1 ? '' : 's'}</span></div><div class="phase5-file-tree">${tree || '<div class="empty-state compact"><strong>No browsable files were returned for this mod.</strong><span>Binary payloads remain managed by the profile even when no editor surface is available.</span></div>'}</div><div class="phase5-file-editor" data-phase5-file-editor><div class="empty-state compact"><strong>Select a file</strong></div></div>`;
      preview.querySelectorAll('[data-phase5-file]').forEach((button) => button.addEventListener('click', async () => {
        preview.querySelectorAll('[data-phase5-file]').forEach((node) => node.classList.toggle('selected', node === button));
        const file = files.find((row) => text(row?.relative_path || row?.name) === text(button.dataset.phase5File));
        if (file) await openExplorerFile(host, unit, file);
      }));
    } catch (error) {
      preview.innerHTML = `<div class="empty-state"><strong>Could not load this mod.</strong><span>${escapeHtml(error.message || String(error))}</span></div>`;
    }
  }

  async function openExplorerFile(host, unit, file) {
    const editorHost = host.querySelector('[data-phase5-file-editor]');
    const save = host.querySelector('[data-phase5-save-file]');
    if (!editorHost || !save) return;
    save.disabled = true;
    host._phase5OpenedFile = null;
    if (!fileEditable(file)) {
      editorHost.innerHTML = `<div class="phase5-binary-preview"><span>◇</span><h4>${escapeHtml(file.name || 'Binary file')}</h4><code>${escapeHtml(file.relative_path || '')}</code><p>Binary and oversized payloads are visible in the logical tree but are not edited in place.</p></div>`;
      return;
    }
    editorHost.innerHTML = '<div class="phase5-explorer-loading compact"><div class="spinner"></div><strong>Opening file…</strong></div>';
    const kind = host.dataset.phase5ExplorerKind;
    const id = host.dataset.phase5ExplorerId;
    const key = unitKey(unit);
    try {
      const opened = kind === 'server'
        ? await bridge.invoke('server.world.config.open', { id, relative_path: file.relative_path })
        : await bridge.invoke('singleplayer.mod.file.open', { key, profile_id: id, relative_path: file.relative_path });
      host._phase5OpenedFile = { kind, id, key, opened };
      editorHost.innerHTML = `<div class="phase5-editor-head"><div><strong>${escapeHtml(opened?.name || file.name || 'File')}</strong><small>${escapeHtml(opened?.relative_path || file.relative_path || '')}</small></div><span class="status-pill ${opened?.language === 'json' ? 'online' : 'unknown'}">${escapeHtml(String(opened?.language || 'text').toUpperCase())}</span></div>${opened?.parse_error ? `<div class="warning-box compact">Existing parse error: ${escapeHtml(opened.parse_error)}</div>` : ''}<textarea class="phase5-editor-textarea" spellcheck="false" data-phase5-editor-text>${escapeHtml(opened?.content || opened?.text || '')}</textarea>`;
      save.disabled = false;
      save.onclick = () => saveExplorerFile(host);
    } catch (error) {
      editorHost.innerHTML = `<div class="empty-state compact"><strong>File open failed.</strong><span>${escapeHtml(error.message || String(error))}</span></div>`;
    }
  }

  async function saveExplorerFile(host) {
    const current = host._phase5OpenedFile;
    const textarea = host.querySelector('[data-phase5-editor-text]');
    const button = host.querySelector('[data-phase5-save-file]');
    if (!current || !textarea || !button) return;
    const content = textarea.value;
    if (String(current.opened?.language || '').toLowerCase() === 'json') {
      try { JSON.parse(content); }
      catch (error) { return showInlineNotice(host, `Invalid JSON · ${error.message}`, 'error'); }
    }
    button.disabled = true;
    try {
      if (current.kind === 'server') {
        await bridge.invoke('server.world.config.save', { id: current.id, relative_path: current.opened.relative_path, content });
      } else {
        await bridge.invoke('singleplayer.mod.file.save', { key: current.key, profile_id: current.id, relative_path: current.opened.relative_path, content });
      }
      showInlineNotice(host, 'File saved atomically.', 'success');
    } catch (error) {
      showInlineNotice(host, `Save failed · ${error.message}`, 'error');
    } finally { button.disabled = false; }
  }

  function showInlineNotice(host, message, kind = '') {
    host.querySelector('.phase5-inline-notice')?.remove();
    const node = document.createElement('div');
    node.className = `phase5-inline-notice ${kind}`;
    node.textContent = message;
    host.querySelector('.phase5-explorer-toolbar')?.appendChild(node);
    setTimeout(() => node.remove(), 3000);
  }

  function renderExplorerError(win, error) {
    const host = win.querySelector('.phase5-explorer-main');
    if (!host) return;
    host.innerHTML = `<div class="empty-state"><strong>Explorer could not open this profile.</strong><span>${escapeHtml(error.message || String(error))}</span></div>`;
  }

  async function openProfileExplorer(kind, id, unitKeyFilter = '') {
    const state = await stateSnapshot();
    const rows = kind === 'server' ? (state?.server_profiles || []) : (state?.client?.private_worlds || []);
    const world = rows.find((row) => text(row?.id) === text(id));
    const worldName = text(world?.name || world?.identity?.world_name || id || 'World');
    return explorerShell(kind, id, worldName, unitKeyFilter);
  }

  async function handleDetachedButton(button) {
    const state = await stateSnapshot();
    let route = 'worlds';
    if (button.id === 'detach-profile') route = 'profile';
    else if (button.id === 'detach-settings') route = document.body.querySelector('.route-webhost') ? 'webhost' : 'settings';
    else if (button.id === 'detach-private-world') route = 'world-detail';
    else if (button.id === 'detach-server-world') route = 'server-detail';
    const context = routeContextFromDom(route, state);
    const title = routeTitle(route, state);
    openRouteWindow(route, context, { title });
  }

  document.addEventListener('pointerdown', (event) => rememberSelectionFromTarget(event.target), true);
  document.addEventListener('contextmenu', (event) => {
    rememberSelectionFromTarget(event.target);
    const row = event.target.closest?.('.mod-row, .config-file-row, [data-sp-tags], [data-mod-tags]');
    const single = row?.querySelector?.('[data-sp-tags]') || event.target.closest?.('[data-sp-tags]');
    const server = row?.querySelector?.('[data-mod-tags]') || event.target.closest?.('[data-mod-tags]');
    const key = text(single?.dataset?.spTags || server?.dataset?.modTags);
    if (key) lastModContext = { kind: single ? 'local' : 'server', key };
  }, true);

  document.addEventListener('click', async (event) => {
    const target = event.target.closest?.('button,[role="menuitem"]');
    if (!target) return;
    rememberSelectionFromTarget(target);

    if (['detach-profile', 'detach-worlds', 'detach-settings', 'detach-private-world', 'detach-server-world'].includes(target.id)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      await handleDetachedButton(target);
      return;
    }

    if (target.id === 'phase2-view-mods') {
      event.preventDefault();
      event.stopImmediatePropagation();
      const kind = document.querySelector('#detach-server-world') ? 'server' : 'local';
      const state = await stateSnapshot();
      const id = resolveSelection(kind, state);
      if (id) await openProfileExplorer(kind, id);
      return;
    }

    if (target.dataset.action === 'open' && lastModContext) {
      const context = lastModContext;
      lastModContext = null;
      event.preventDefault();
      event.stopImmediatePropagation();
      target.closest('.context-menu')?.remove();
      const state = await stateSnapshot();
      const id = resolveSelection(context.kind, state);
      if (id) await openProfileExplorer(context.kind, id, context.key);
      return;
    }
  }, true);

  window.__DWSYNC_INTERNAL_WINDOWS__ = Object.freeze({
    openRoute: (route, context, options) => openRouteWindow(route, context || {}, options || {}),
    openExplorer: (kind, id, unitKeyFilter = '') => openProfileExplorer(kind, id, unitKeyFilter),
    focus: (key) => {
      const win = modalRoot.querySelector(`.phase5-window[data-phase5-key="${CSS.escape(safeKey(key))}"]`);
      if (!win) return false;
      win.classList.remove('minimized');
      focusWindow(win);
      return true;
    },
  });
})();
