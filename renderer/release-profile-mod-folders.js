(() => {
  'use strict';

  const bridge = window.dragonwilds;
  if (!bridge?.invoke || !bridge?.openPath) return;

  const query = new URLSearchParams(window.location.search);
  let detachedContext = {};
  try {
    const encoded = String(query.get('ctx') || '').replaceAll('-', '+').replaceAll('_', '/');
    if (encoded) {
      const padded = encoded + '='.repeat((4 - (encoded.length % 4)) % 4);
      detachedContext = JSON.parse(decodeURIComponent(escape(atob(padded)))) || {};
    }
  } catch (_) { detachedContext = {}; }

  let storageCache = null;
  let openedProfile = null;
  let rewritePending = false;

  const text = (value) => String(value ?? '').trim();
  const safeProfileId = (value) => {
    const cleaned = text(value).replace(/[^A-Za-z0-9_.-]+/g, '_').replace(/^[._-]+|[._-]+$/g, '');
    return cleaned.slice(0, 80) || 'singleplayer';
  };
  const state = () => (window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object') ? window.__DWSYNC_STATE__ : {};
  const privateWorlds = (root) => Array.isArray(root?.client?.private_worlds) ? root.client.private_worlds : (root?.client?.singleplayer ? [root.client.singleplayer] : []);
  const serverWorlds = (root) => Array.isArray(root?.server_profiles) ? root.server_profiles : [];
  const visibleWorldName = () => text(document.querySelector('.detail-hero h1')?.textContent || document.querySelector('.phase5-explorer-world strong')?.textContent);

  function joinPath(root, ...parts) {
    const base = text(root);
    const separator = base.includes('\\') ? '\\' : '/';
    let result = base.replace(/[\\/]+$/, '');
    for (const part of parts) result += `${separator}${text(part).replace(/^[\\/]+|[\\/]+$/g, '')}`;
    return result;
  }

  async function storagePaths() {
    if (storageCache) return storageCache;
    storageCache = await bridge.invoke('application.storage.paths', {});
    return storageCache || {};
  }

  function profileFor(kind) {
    const root = state();
    const rows = kind === 'server' ? serverWorlds(root) : privateWorlds(root);
    const detachedId = text(kind === 'server' ? detachedContext.selectedServerWorldId : detachedContext.selectedWorldId);
    if (detachedId) {
      const found = rows.find((row) => text(row?.id) === detachedId);
      if (found) return found;
    }

    const explorer = document.querySelector(`[data-phase5-explorer-kind="${kind}"]`);
    const explorerId = text(explorer?.dataset?.phase5ExplorerId);
    if (explorerId) {
      const found = rows.find((row) => text(row?.id) === explorerId);
      if (found) return found;
    }

    const title = visibleWorldName();
    if (title) {
      const named = rows.filter((row) => text(row?.name || row?.nickname) === title);
      if (named.length === 1) return named[0];
    }

    const activeId = text(kind === 'server'
      ? root?.server?.active_world_id
      : (root?.client?.active_private_world_id || root?.client?.live_world_id));
    return rows.find((row) => text(row?.id) === activeId) || rows[0] || null;
  }

  async function modsPath(kind, profileId) {
    const paths = await storagePaths();
    const id = safeProfileId(profileId);
    if (kind === 'server') {
      const root = text(paths.server_profiles);
      if (!root) throw new Error('Server profile storage path is unavailable.');
      return joinPath(root, id, 'mods');
    }
    const root = text(paths.app_data);
    if (!root) throw new Error('Application data path is unavailable.');
    return joinPath(root, 'profiles', 'world', 'local', id, 'snapshot', 'mods');
  }

  function noteFor(kind) {
    return document.querySelector(`[data-profile-mod-folder-note="${kind}"]`);
  }

  function updateNote(kind, message, tone = '') {
    const note = noteFor(kind);
    if (!note) return;
    const detail = note.querySelector('p');
    if (detail) detail.textContent = message;
    note.dataset.tone = tone;
  }

  function reconciliationText(response) {
    const reconciliation = response?.cache?.reconciliation || response?.reconciliation || {};
    const added = Number(reconciliation.added_count || 0);
    const changed = Number(reconciliation.changed_count || 0);
    const removed = Number(reconciliation.removed_count || 0);
    if (!added && !changed && !removed) return 'Rescan complete · no profile mod changes detected.';
    return `Rescan complete · ${added} added · ${changed} changed · ${removed} removed.`;
  }

  async function authoritativeRescan(kind, profileId) {
    const visibleButton = document.querySelector(kind === 'server' ? '#refresh-server-inventory' : '#sp-refresh');
    if (visibleButton) {
      visibleButton.click();
      updateNote(kind, 'Rescanning the profile mod folders…');
      return;
    }

    const response = await bridge.invoke(
      kind === 'server' ? 'server.world.inventory' : 'singleplayer.inventory',
      kind === 'server' ? { id: profileId, rescan: true } : { profile_id: profileId, rescan: true },
    );
    updateNote(kind, reconciliationText(response), 'success');
  }

  async function openProfileMods(kind, button) {
    const profile = profileFor(kind);
    if (!profile?.id) {
      updateNote(kind, 'No World profile is selected.');
      return;
    }
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Opening…';
    try {
      const target = await modsPath(kind, profile.id);
      // A pre-open scan also refreshes the profile cache before Explorer is shown.
      try { await authoritativeRescan(kind, profile.id); } catch (_) {}
      const opened = await bridge.openPath(target);
      if (!opened) throw new Error(`Could not open ${target}`);
      openedProfile = { kind, id: text(profile.id), path: target, openedAt: Date.now() };
      updateNote(kind, `Profile folder open · ${target}`);
    } catch (error) {
      updateNote(kind, text(error?.message || error || 'Could not open the profile Mods folder.'), 'error');
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function replaceImportButton(selector, kind) {
    const old = document.querySelector(selector);
    if (!old || old.dataset.profileFolderReplaced === '1') return;
    const button = old.cloneNode(false);
    button.dataset.profileFolderReplaced = '1';
    button.id = kind === 'server' ? 'server-open-mods-folder' : 'sp-open-mods-folder';
    button.classList.remove('primary');
    button.classList.add('ghost');
    button.textContent = 'Open Mods Folder';
    button.title = 'Open this World profile’s mod folder in Windows Explorer';
    button.addEventListener('click', () => openProfileMods(kind, button));
    old.replaceWith(button);
  }

  function replaceDropZone(selector, kind) {
    const old = document.querySelector(selector);
    if (!old) return;
    const note = document.createElement('div');
    note.className = 'identity-box profile-mod-folder-note';
    note.dataset.profileModFolderNote = kind;
    note.innerHTML = '<strong>Folder-managed mods</strong><p>Open this World profile’s Mods folder, add/remove/replace files in Explorer, then use Rescan. Dragonwilds Sync identifies added, changed, and removed mods from the profile folder itself.</p>';
    old.replaceWith(note);
  }

  function hardenRuntimeBaselineUi() {
    const labels = {
      baseline: 'PROTECTED RECOVERY BASELINE',
      official: 'PROTECTED RECOVERY BASELINE',
    };
    for (const [id, label] of Object.entries(labels)) {
      document.querySelectorAll(`[data-runtime-build-row="${id}"]`).forEach((row) => {
        row.dataset.recoveryBaseline = '1';
        const lock = row.querySelector('.runtime-build-lock');
        if (lock) lock.title = 'Protected recovery baseline · cannot be renamed or deleted';
        const cell = row.children?.[2];
        if (cell && !cell.querySelector('.runtime-build-recovery')) {
          const badge = document.createElement('small');
          badge.className = 'runtime-build-recovery';
          badge.textContent = label;
          cell.appendChild(badge);
        }
      });
    }

    const ueBaseline = document.querySelector('#update-client-ue4ss-baseline');
    if (ueBaseline) {
      ueBaseline.title = 'Protected packaged UE4SS recovery baseline';
      const small = ueBaseline.querySelector('small');
      if (small && !/protected/i.test(small.textContent || '')) small.textContent += ' · Protected recovery copy.';
    }
    const runeBaseline = document.querySelector('#update-client-runeschema-baseline');
    if (runeBaseline) {
      runeBaseline.title = 'Protected packaged RuneSchema recovery baseline';
      const small = runeBaseline.querySelector('small');
      if (small && !/protected/i.test(small.textContent || '')) small.textContent += ' · Protected recovery copy.';
    }

    // Do not advertise a hard-coded experimental version as the baseline. The
    // status area above these cards already displays the version actually loaded.
    const runeExperimental = document.querySelector('#update-client-runeschema-experimental');
    if (runeExperimental) {
      const strong = runeExperimental.querySelector('strong');
      const small = runeExperimental.querySelector('small');
      if (strong && /built-in\s+0\.6\.3\s+baseline/i.test(strong.textContent || '')) strong.textContent = 'Newest experimental build';
      if (small) small.textContent = 'Optional test channel; the protected packaged baseline remains available for recovery.';
    }

    document.querySelectorAll('.runtime-center-grid > div').forEach((card) => {
      const name = text(card.querySelector('span')?.textContent).toLowerCase();
      if (!name.includes('ue4ss') && !name.includes('runeschema')) return;
      const status = card.querySelector('strong');
      const version = text(card.querySelector('small')?.textContent);
      if (status && version && !/not|unknown|unavailable/i.test(version)) status.textContent = 'LOADED';
    });
  }

  function refreshLegacyHelpCopy() {
    document.querySelectorAll('p, span').forEach((node) => {
      const value = text(node.textContent);
      if (value.includes('Drop a ZIP on the matching UE4SS or RuneSchema target')) {
        node.textContent = 'Open the selected World profile’s Mods folder in Explorer, place UE4SS, RuneSchema, or PAK content in its normal folder structure, then Rescan. The profile folder is the management source of truth.';
      }
    });
    document.querySelectorAll('.identity-box strong').forEach((strong) => {
      if (text(strong.textContent) === 'Manual + Nexus-linked inventory') {
        strong.textContent = 'Folder-managed + Nexus-linked inventory';
        const paragraph = strong.parentElement?.querySelector('p');
        if (paragraph) paragraph.textContent = 'Manual mods come from the World profile folder and are reconciled by Rescan. Nexus-linked metadata and update evidence can remain attached to discovered mods.';
      }
    });
  }

  function rewriteUi() {
    rewritePending = false;
    replaceImportButton('#sp-install-mod', 'local');
    replaceImportButton('#install-server-mod-zip', 'server');
    replaceDropZone('#sp-mod-dropzone', 'local');
    replaceDropZone('#server-mod-dropzone', 'server');
    hardenRuntimeBaselineUi();
    refreshLegacyHelpCopy();
  }

  function scheduleRewrite() {
    if (rewritePending) return;
    rewritePending = true;
    requestAnimationFrame(rewriteUi);
  }

  const observer = new MutationObserver(scheduleRewrite);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('dragonwilds:state-updated', scheduleRewrite);
  window.addEventListener('DOMContentLoaded', scheduleRewrite, { once: true });
  scheduleRewrite();

  window.addEventListener('focus', () => {
    const opened = openedProfile;
    if (!opened || Date.now() - opened.openedAt < 250) return;
    openedProfile = null;
    authoritativeRescan(opened.kind, opened.id).catch((error) => {
      updateNote(opened.kind, text(error?.message || error || 'Rescan failed.'), 'error');
    });
  });
})();
