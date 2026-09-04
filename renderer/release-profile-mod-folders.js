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

  let rewritePending = false;
  let rescanBusy = false;
  const selection = (window.__DWSYNC_PROFILE_SELECTION__ ||= { local: '', server: '' });

  const text = (value) => String(value ?? '').trim();
  const state = () => (window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object') ? window.__DWSYNC_STATE__ : {};
  const privateWorlds = (root) => Array.isArray(root?.client?.private_worlds) ? root.client.private_worlds : (root?.client?.singleplayer ? [root.client.singleplayer] : []);
  const serverWorlds = (root) => Array.isArray(root?.server_profiles) ? root.server_profiles : [];
  const visibleWorldName = () => text(document.querySelector('.detail-hero h1')?.textContent || document.querySelector('.phase5-explorer-world strong')?.textContent);

  function remember(kind, id) {
    const normalized = text(id);
    if (!normalized) return;
    selection[kind] = normalized;
    window.dispatchEvent(new CustomEvent('dragonwilds:profile-selection-changed', { detail: { kind, id: normalized } }));
  }

  function profileFor(kind) {
    const root = state();
    const rows = kind === 'server' ? serverWorlds(root) : privateWorlds(root);
    const detachedId = text(kind === 'server' ? detachedContext.selectedServerWorldId : detachedContext.selectedWorldId);
    if (detachedId) {
      const found = rows.find((row) => text(row?.id) === detachedId);
      if (found) { remember(kind, detachedId); return found; }
    }

    const rememberedId = text(selection[kind]);
    if (rememberedId) {
      const found = rows.find((row) => text(row?.id) === rememberedId);
      if (found) return found;
    }

    const explorer = document.querySelector(`[data-phase5-explorer-kind="${kind}"]`);
    const explorerId = text(explorer?.dataset?.phase5ExplorerId);
    if (explorerId) {
      const found = rows.find((row) => text(row?.id) === explorerId);
      if (found) { remember(kind, explorerId); return found; }
    }

    const title = visibleWorldName();
    if (title) {
      const named = rows.filter((row) => text(row?.name || row?.nickname) === title);
      if (named.length === 1) { remember(kind, named[0].id); return named[0]; }
    }

    const activeId = text(kind === 'server'
      ? root?.server?.active_world_id
      : (root?.client?.active_private_world_id || root?.client?.live_world_id));
    const fallback = rows.find((row) => text(row?.id) === activeId) || rows[0] || null;
    if (fallback?.id) remember(kind, fallback.id);
    return fallback;
  }

  async function modsPath(kind, profile) {
    // Authoritative: ask the backend for this profile's actual mod root
    // rather than reconstructing it here. The backend also self-heals any
    // legacy layout (ensure_profile_mod_roots) as part of resolving it.
    const response = await bridge.invoke('application.profile.mods_root', { kind, id: profile?.id });
    const authoritative = text(response?.mods_root);
    if (authoritative) return { path: authoritative, kind: text(response?.resolved_kind) || kind };
    // Defensive fallback only: an explicit mods_root/mods_path the backend
    // already attached to the profile object itself (never a renderer guess).
    const explicit = text(profile?.mods_root || profile?.mods_path);
    if (explicit) return { path: explicit, kind };
    throw new Error('Could not resolve this World profile\'s Mods folder.');
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
    if (!added && !changed && !removed) return 'Refresh complete · no profile mod changes detected.';
    return `Refresh complete · ${added} added · ${changed} changed · ${removed} removed.`;
  }

  async function authoritativeRescan(kind, profileId) {
    if (!profileId || rescanBusy) return null;
    rescanBusy = true;
    updateNote(kind, 'Refreshing from the selected profile mod folder…');
    try {
      const resolved = await modsPath(kind, { id: profileId });
      const actualKind = resolved.kind === 'server' ? 'server' : 'local';
      const response = await bridge.invoke(
        actualKind === 'server' ? 'server.world.inventory' : 'singleplayer.inventory',
        actualKind === 'server' ? { id: profileId, rescan: true } : { profile_id: profileId, rescan: true },
      );
      if (response?.state && typeof response.state === 'object') {
        window.__DWSYNC_STATE__ = response.state;
        window.dispatchEvent(new CustomEvent('dragonwilds:state-updated', { detail: response.state }));
      }
      const rows = Array.isArray(response?.units || response?.mods || response?.inventory)
        ? (response.units || response.mods || response.inventory)
        : [];
      window.dispatchEvent(new CustomEvent('dragonwilds:mod-inventory-refreshed', {
        detail: {
          id: profileId,
          kind: actualKind,
          rows,
          reconciliation: response?.cache?.reconciliation || response?.reconciliation || {},
          authoritative: true,
        },
      }));
      updateNote(kind, reconciliationText(response), 'success');
      return response;
    } catch (error) {
      updateNote(kind, text(error?.message || error || 'Could not refresh the selected profile Mods folder.'), 'error');
      throw error;
    } finally {
      rescanBusy = false;
    }
  }

  async function openProfileMods(kind, button) {
    const profile = profileFor(kind);
    if (!profile?.id) {
      updateNote(kind, 'No World profile is selected.');
      return;
    }
    remember(kind, profile.id);
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Opening…';
    try {
      const target = await modsPath(kind, profile);
      const opened = await bridge.openPath(target.path);
      if (!opened) throw new Error(`Could not open ${target.path}`);
      updateNote(kind, `Profile folder open · ${target.path}`);
    } catch (error) {
      updateNote(kind, text(error?.message || error || 'Could not open the profile Mods folder.'), 'error');
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function bindProfileFolderButton(selector, kind) {
    const button = document.querySelector(selector);
    if (!button || button.dataset.profileFolderBound === '1') return;
    button.dataset.profileFolderBound = '1';
    button.title = 'Open this World profile’s authoritative mod folder in Windows Explorer';
    button.addEventListener('click', () => openProfileMods(kind, button));
  }

  function hardenRuntimeBaselineUi() {
    const labels = { baseline: 'PROTECTED RECOVERY BASELINE', official: 'PROTECTED RECOVERY BASELINE' };
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
    const runeExperimental = document.querySelector('#update-client-runeschema-experimental');
    if (runeExperimental) {
      const strong = runeExperimental.querySelector('strong');
      const small = runeExperimental.querySelector('small');
      if (strong && /built-in\s+0\.6\.3\s+baseline/i.test(strong.textContent || '')) strong.textContent = 'Newest experimental build';
      if (small) small.textContent = 'Optional test channel; the protected packaged baseline remains available for recovery.';
    }
  }

  function refreshFolderHelpCopy() {
    document.querySelectorAll('p, span').forEach((node) => {
      const value = text(node.textContent);
      if (value.includes('Drop a ZIP on the matching UE4SS or RuneSchema target')) {
        node.textContent = 'Open the selected World profile’s Mods folder in Explorer, place UE4SS, RuneSchema, or PAK content in its normal folder structure, then Refresh. The profile folder is the management source of truth.';
      }
    });
  }

  function rewriteUi() {
    rewritePending = false;
    bindProfileFolderButton('#sp-open-mods-folder', 'local');
    bindProfileFolderButton('#server-open-mods-folder', 'server');
    hardenRuntimeBaselineUi();
    refreshFolderHelpCopy();
  }

  function scheduleRewrite() {
    if (rewritePending) return;
    rewritePending = true;
    requestAnimationFrame(rewriteUi);
  }

  document.addEventListener('click', (event) => {
    const refresh = event.target?.closest?.('#sp-refresh, #refresh-server-inventory');
    if (refresh && refresh.dataset.profileAuthorityBypass !== '1') {
      const kind = refresh.id === 'refresh-server-inventory' ? 'server' : 'local';
      const profile = profileFor(kind);
      if (profile?.id) {
        event.preventDefault();
        event.stopImmediatePropagation();
        remember(kind, profile.id);
        void authoritativeRescan(kind, text(profile.id));
      }
      return;
    }

    const target = event.target?.closest?.('[data-server-manage], [data-server-card][data-world-id], [data-private-manage], [data-private-launch], [data-private-coop], [data-world-id]');
    if (!target) return;
    const serverId = text(target.dataset.serverManage || (target.dataset.serverCard === '1' ? target.dataset.worldId : ''));
    if (serverId) remember('server', serverId);
    const localId = text(target.dataset.privateManage || target.dataset.privateLaunch || target.dataset.privateCoop || (target.dataset.serverCard === '0' ? target.dataset.worldId : ''));
    if (localId) remember('local', localId);
  }, true);

  const observer = new MutationObserver(scheduleRewrite);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('dragonwilds:state-updated', scheduleRewrite);
  window.addEventListener('DOMContentLoaded', scheduleRewrite, { once: true });
  scheduleRewrite();
})();
