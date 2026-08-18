(() => {
  'use strict';

  const bridge = window.dragonwilds;
  let cachedState = null;
  let fetchedAt = 0;
  let scheduled = false;

  function iconMode() {
    try {
      const saved = localStorage.getItem('dragonwilds-sync-icon-mode');
      return ['color','adaptive','black','white'].includes(saved) ? saved : 'color';
    } catch (_) { return 'color'; }
  }

  function applyIconMode() {
    document.documentElement.dataset.dwsIconMode = iconMode();
  }

  async function state(force = false) {
    if (!bridge?.invoke) return cachedState || {};
    if (!force && cachedState && Date.now() - fetchedAt < 1800) return cachedState;
    try {
      cachedState = await bridge.invoke('state.get', {});
      fetchedAt = Date.now();
    } catch (_) {}
    return cachedState || {};
  }

  function retireStandaloneRemoteEntries(root = document) {
    // Advanced's second Remote Management switch is retired. The authoritative
    // switch is inside WebHost → Website & Networking.
    const legacyToggle = root.querySelector('#toggle-remote-server-feature');
    legacyToggle?.closest('.settings-row')?.classList.add('dws-v2-retired-remote-entry');

    // The old top-level Remote Server nav item may survive in older renderer
    // snapshots. Keep its route callable for compatibility, but hide the entry.
    root.querySelectorAll('aside a, aside button, nav a, nav button').forEach((node) => {
      if (node.closest('.webhost-tabs')) return;
      const label = String(node.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
      if (label === 'remote server' || label === 'remote server login') node.classList.add('dws-v2-retired-remote-entry');
    });
  }

  async function applyWebHostContract(root = document) {
    const snapshot = await state();
    const application = snapshot?.application || {};
    const advanced = application.advanced || {};
    const host = application.world_directory_host || {};
    const remote = host.remote_admin || {};
    const webHostActivated = !!advanced.webhost_enabled;
    const remoteEnabled = !!remote.enabled;

    // Declared is a host operator view. A normal client that merely consumes a
    // directory does not get a local Declared tab.
    const declared = root.querySelector('[data-vnext-world-tab="declared"]');
    if (declared) {
      declared.hidden = !webHostActivated;
      declared.style.display = webHostActivated ? '' : 'none';
    }

    // Remote Server is a WebHost sub-tab, and only exists while enabled.
    const remoteTab = root.querySelector('[data-webhost-tab="remote"]');
    if (remoteTab) {
      remoteTab.hidden = !remoteEnabled;
      remoteTab.style.display = remoteEnabled ? '' : 'none';
      remoteTab.textContent = 'Remote Server';
      remoteTab.title = 'Remote users, passwords, permissions and requests';
    }

    const toggle = root.querySelector('#toggle-webhost-remote-admin');
    const row = toggle?.closest('.settings-row');
    if (row) {
      const title = row.querySelector('.settings-copy strong');
      const copy = row.querySelector('.settings-copy span');
      if (title) title.textContent = 'Remote Server';
      if (copy) copy.textContent = 'Enable the target-owned Remote Server login and its user/permission authority. Public WebHost pages show Server Management only while this is enabled.';
    }

    // Clarify that the Manifest tab is the outbound/inbound directory router,
    // not another authentication surface.
    root.querySelectorAll('[data-webhost-tab="manifest"]').forEach((button) => {
      button.textContent = 'Manifest & Heartbeats';
    });
  }

  function smoothIconNodes(root = document) {
    root.querySelectorAll('.platform-logo,.world-platform-badge img,.world-community-badge img,.world-audience-badge img').forEach((img) => {
      img.dataset.iconVariants = 'color black white';
      img.draggable = false;
    });
  }

  async function enhance() {
    applyIconMode();
    retireStandaloneRemoteEntries();
    smoothIconNodes();
    await applyWebHostContract();
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      void enhance();
    });
  }

  window.addEventListener('dragonwilds:icon-mode', (event) => {
    const mode = String(event.detail?.mode || '');
    if (!['color','adaptive','black','white'].includes(mode)) return;
    try { localStorage.setItem('dragonwilds-sync-icon-mode', mode); } catch (_) {}
    applyIconMode();
  });

  applyIconMode();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule, {once:true});
  else schedule();
  new MutationObserver(schedule).observe(document.documentElement, {childList:true, subtree:true});
  setInterval(() => { fetchedAt = 0; schedule(); }, 5000);
})();
