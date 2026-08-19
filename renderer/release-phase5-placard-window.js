(() => {
  'use strict';

  const api = window.dragonwilds;
  const modalRoot = document.getElementById('modal-root');
  const taskbar = document.getElementById('internal-taskbar');
  if (!api?.invoke || !modalRoot || !taskbar) return;

  const windows = new Map();
  const platforms = new Map();
  let zIndex = 10100;
  let platformLoad = null;

  const text = (value) => String(value ?? '').trim();
  const safeKey = (value) => text(value).replace(/[^A-Za-z0-9_.:-]+/g, '-').slice(0, 160) || 'world';
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const geometryKey = (id) => `dragonwilds-sync-phase5-placard:${safeKey(id)}`;

  function readGeometry(id) {
    try {
      const value = JSON.parse(localStorage.getItem(geometryKey(id)) || '{}');
      return value && typeof value === 'object' ? value : {};
    } catch (_) { return {}; }
  }

  function saveGeometry(win) {
    if (!win || win.classList.contains('maximized') || win.classList.contains('minimized')) return;
    const layer = modalRoot.getBoundingClientRect();
    const rect = win.getBoundingClientRect();
    const value = {
      left: Math.max(0, Math.round(rect.left - layer.left)),
      top: Math.max(0, Math.round(rect.top - layer.top)),
      width: Math.round(rect.width), height: Math.round(rect.height),
    };
    try { localStorage.setItem(geometryKey(win.dataset.phase5PlacardWindow), JSON.stringify(value)); } catch (_) {}
  }

  function titleFor(id, source) {
    return text(source?.querySelector('h2,h3')?.textContent) || text(source?.getAttribute('aria-label')?.split('·')?.[0]) || `World ${id}`;
  }

  function taskFor(win) {
    const id = win.dataset.phase5PlacardWindow;
    let button = taskbar.querySelector(`[data-phase5-placard-task="${CSS.escape(id)}"]`);
    if (button) return button;
    button = document.createElement('button');
    button.className = 'internal-task-button phase5-placard-task active';
    button.dataset.phase5PlacardTask = id;
    button.innerHTML = `<span>▣</span><span>${esc(win.dataset.phase5PlacardTitle || 'World Placard')}</span>`;
    button.title = win.dataset.phase5PlacardTitle || 'World Placard';
    button.addEventListener('click', () => {
      win.classList.remove('minimized');
      focusWindow(win);
    });
    taskbar.appendChild(button);
    return button;
  }

  function focusWindow(win) {
    if (!win) return;
    modalRoot.querySelectorAll('.phase5-placard-window').forEach((node) => node.classList.remove('focused'));
    taskbar.querySelectorAll('.phase5-placard-task').forEach((node) => node.classList.remove('active'));
    win.classList.remove('minimized');
    win.classList.add('focused');
    win.style.zIndex = String(++zIndex);
    taskFor(win).classList.add('active');
  }

  function closeWindow(win) {
    if (!win) return;
    const id = win.dataset.phase5PlacardWindow;
    saveGeometry(win);
    win._phase5ResizeObserver?.disconnect?.();
    taskbar.querySelector(`[data-phase5-placard-task="${CSS.escape(id)}"]`)?.remove();
    windows.delete(id);
    win.remove();
  }

  function minimizeWindow(win) {
    if (!win) return;
    saveGeometry(win);
    win.classList.add('minimized');
    taskFor(win).classList.remove('active');
  }

  function toggleMaximize(win) {
    if (!win) return;
    if (win.classList.contains('maximized')) {
      win.classList.remove('maximized');
      const restore = win._phase5RestoreRect;
      if (restore) {
        Object.assign(win.style, {
          left: `${restore.left}px`, top: `${restore.top}px`, width: `${restore.width}px`, height: `${restore.height}px`,
        });
      }
      win._phase5RestoreRect = null;
    } else {
      const layer = modalRoot.getBoundingClientRect();
      const rect = win.getBoundingClientRect();
      win._phase5RestoreRect = { left: rect.left - layer.left, top: rect.top - layer.top, width: rect.width, height: rect.height };
      win.classList.add('maximized');
    }
    focusWindow(win);
  }

  function bindGeometry(win) {
    const bar = win.querySelector('.phase5-placard-titlebar');
    bar?.addEventListener('dblclick', (event) => {
      if (event.target.closest('button')) return;
      event.preventDefault(); toggleMaximize(win);
    });
    bar?.addEventListener('pointerdown', (event) => {
      if (event.button !== 0 || win.classList.contains('maximized') || event.target.closest('button')) return;
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
    if ('ResizeObserver' in window) {
      const observer = new ResizeObserver(() => {
        clearTimeout(win._phase5SaveTimer);
        win._phase5SaveTimer = setTimeout(() => saveGeometry(win), 120);
      });
      observer.observe(win); win._phase5ResizeObserver = observer;
    }
  }

  function openPlacard(id, source = null) {
    id = text(id); if (!id) return null;
    const existing = windows.get(id) || modalRoot.querySelector(`[data-phase5-placard-window="${CSS.escape(id)}"]`);
    if (existing) { windows.set(id, existing); focusWindow(existing); return existing; }

    source = source || document.querySelector(`.v3p4-placard[data-world-id="${CSS.escape(id)}"]`);
    const title = titleFor(id, source);
    const server = source?.dataset?.serverCard === '1' ? '1' : '0';
    const layer = modalRoot.getBoundingClientRect();
    const stored = readGeometry(id);
    const width = Math.min(Math.max(520, Number(stored.width || 760)), Math.max(520, layer.width - 20));
    const height = Math.min(Math.max(420, Number(stored.height || 720)), Math.max(420, layer.height - 20));
    const left = Math.max(6, Math.min(Number(stored.left ?? 40), Math.max(6, layer.width - width - 6)));
    const top = Math.max(6, Math.min(Number(stored.top ?? 32), Math.max(6, layer.height - height - 6)));

    const win = document.createElement('section');
    win.className = 'phase5-placard-window focused';
    win.dataset.phase5PlacardWindow = id;
    win.dataset.phase5PlacardTitle = title;
    win.setAttribute('role', 'dialog');
    win.setAttribute('aria-label', `${title} placard window`);
    Object.assign(win.style, { left:`${left}px`, top:`${top}px`, width:`${width}px`, height:`${height}px`, zIndex:String(++zIndex) });
    win.innerHTML = `<div class="phase5-placard-titlebar"><strong>${esc(title)}</strong><div><button class="phase5-placard-window-control" data-phase5-placard-min title="Minimize" aria-label="Minimize">—</button><button class="phase5-placard-window-control" data-phase5-placard-max title="Maximize / Restore" aria-label="Maximize or restore">□</button><button class="phase5-placard-window-control close" data-phase5-placard-close title="Close" aria-label="Close">×</button></div></div><div class="phase5-placard-window-body"><article class="world-card" data-world-id="${esc(id)}" data-server-card="${server}"><div class="v3p4-window-summary"><div class="eyebrow">World Placard</div><h2>${esc(title)}</h2><p>Live World identity, joining details, compatibility and heartbeat status.</p></div></article></div>`;
    modalRoot.appendChild(win); windows.set(id, win); taskFor(win); bindGeometry(win);
    win.querySelector('[data-phase5-placard-min]')?.addEventListener('click', (event) => { event.stopPropagation(); minimizeWindow(win); });
    win.querySelector('[data-phase5-placard-max]')?.addEventListener('click', (event) => { event.stopPropagation(); toggleMaximize(win); });
    win.querySelector('[data-phase5-placard-close]')?.addEventListener('click', (event) => { event.stopPropagation(); closeWindow(win); });
    focusWindow(win);
    // The retained V3 Phase 4 MutationObserver owns decoration and heartbeat
    // refresh for this new card, so this window does not create a second card model.
    return win;
  }

  async function loadPlatforms() {
    if (platformLoad) return platformLoad;
    platformLoad = api.invoke('v3.phase4.platforms.registry', {}).then((registry) => {
      for (const row of Array.isArray(registry?.items) ? registry.items : []) {
        if (!row || row.enabled === false || !row.id) continue;
        platforms.set(String(row.id), row);
      }
      return registry;
    }).catch(() => null);
    return platformLoad;
  }

  function platformId(node) {
    const src = text(node.querySelector('img')?.getAttribute('src')).toLowerCase();
    const file = src.split('/').pop()?.replace(/\.svg(?:\?.*)?$/,'') || '';
    const aliases = { epicgames:'epic', nintendo:'nintendo-switch-2', steam:'steam', xbox:'xbox', playstation:'playstation', windows:'windows', linux:'linux' };
    return aliases[file] || '';
  }

  async function linkPlatforms(root = document) {
    await loadPlatforms();
    root.querySelectorAll?.('.v3p4-platform:not(.phase5-linked-platform)').forEach((node) => {
      const row = platforms.get(platformId(node));
      const url = text(row?.directSupportUrl || row?.fallbackInfoUrl);
      if (!row || !/^https:\/\//i.test(url)) return;
      node.classList.add('phase5-linked-platform');
      node.tabIndex = 0;
      node.setAttribute('role', 'link');
      node.title = `View RuneScape: Dragonwilds on ${row.displayName || row.id}`;
      const open = (event) => { event.preventDefault(); event.stopPropagation(); api.openInAppBrowser?.(url); };
      node.addEventListener('click', open);
      node.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') open(event); });
    });
  }

  function replaceLegacyOpenControls(root = document) {
    root.querySelectorAll?.('[data-v3p4-open-menu]').forEach((button) => {
      const id = text(button.dataset.v3p4OpenMenu);
      if (!id) return;
      delete button.dataset.v3p4OpenMenu;
      button.dataset.phase5OpenPlacard = id;
      button.textContent = 'Open Placard';
    });
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest?.('[data-phase5-open-placard]');
    if (!button) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const id = text(button.dataset.phase5OpenPlacard);
    document.querySelector('.world-context-menu')?.remove();
    openPlacard(id, document.querySelector(`[data-world-id="${CSS.escape(id)}"]`));
  }, true);

  // Capture before the retained V3 Phase 4 dblclick handler so the legacy fixed
  // overlay cannot be created alongside the application-owned window.
  document.addEventListener('dblclick', (event) => {
    const card = event.target.closest?.('.v3p4-placard[data-world-id]');
    if (!card || event.target.closest('button,a,input,select,textarea')) return;
    event.preventDefault(); event.stopImmediatePropagation(); openPlacard(card.dataset.worldId, card);
  }, true);

  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (!(node instanceof Element)) continue;
        replaceLegacyOpenControls(node); linkPlatforms(node);
      }
    }
    replaceLegacyOpenControls(document); linkPlatforms(document);
  });
  observer.observe(document.documentElement, { childList:true, subtree:true });
  replaceLegacyOpenControls(document); linkPlatforms(document);

  window.__DWSYNC_PHASE5_PLACARDS__ = Object.freeze({
    open: (id) => openPlacard(id),
    close: (id) => { const win = windows.get(text(id)); if (win) closeWindow(win); },
    focus: (id) => { const win = windows.get(text(id)); if (!win) return false; focusWindow(win); return true; },
  });
})();
