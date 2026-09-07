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
  let machinePaths = null;
  let machinePathsPending = null;
  const selection = (window.__DWSYNC_PROFILE_SELECTION__ ||= { local: '', server: '' });

  const text = (value) => String(value ?? '').trim();
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
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
    hardenRuntimeBaselineUi();
    refreshFolderHelpCopy();
    document.querySelectorAll('.profile-storage-destinations').forEach((host)=>{
      if(host.querySelector('[data-profile-spare-panel]'))return;
      const panel=document.createElement('details');panel.dataset.profileSparePanel='1';
      panel.innerHTML='<summary>Protect a staged folder · spare backup</summary><p>Restore missing files before deployment. Existing or edited files are never overwritten. Saving again explicitly refreshes the spare copy.</p><label>Folder relative to profile staging<input class="input" data-profile-spare-path placeholder="Binaries/Win64/ue4ss"></label><div class="header-actions"><button type="button" class="btn primary" data-profile-spare-action="protect">Save spare backup</button><button type="button" class="btn ghost" data-profile-spare-action="list">Show protected folders</button><button type="button" class="btn ghost" data-profile-spare-action="unprotect">Stop protecting entered folder</button></div><p role="status" data-profile-spare-status></p>';
      host.append(panel);
    });
    void refreshRuntimeLocationChoices();
  }

  async function refreshRuntimeLocationChoices() {
    const definitions = [
      ['edit-private-ue4ss-root','player',true], ['edit-private-runeschema-root','player',true],
      ['se-server-ue4ss-root','server',false], ['se-server-runeschema-root','server',false],
      ['se-client-ue4ss-root','server',true], ['se-client-runeschema-root','server',true],
    ];
    if (!definitions.some(([id]) => document.getElementById(id))) return;
    try {
      if (!machinePaths) {
        machinePathsPending ||= bridge.invoke('application.machine_paths.get', {}).finally(()=>{machinePathsPending=null;});
        machinePaths = await machinePathsPending;
      }
      for (const [id, role, relative] of definitions) {
        const input = document.getElementById(id);
        if (!input) continue;
        const choices = machinePaths?.[role]?.runtime_locations || (relative ? [
          {label:'Win64',game_relative:'Binaries/Win64',eligible:true},
          {label:'RuneSchema',game_relative:'Binaries/Win64/ue4ss/Mods/RuneSchema',eligible:true},
        ] : []);
        let picker = input.parentElement.querySelector(`[data-profile-runtime-choice="${id}"]`);
        if (!picker) {
          picker = document.createElement('select');
          picker.className = 'select';
          picker.dataset.profileRuntimeChoice = id;
          picker.setAttribute('aria-label','Choose a saved location for '+id.replaceAll('-',' '));
          picker.title='Choose a saved location, or type directly in the path field. Save the profile to apply.';
          input.insertAdjacentElement('afterend',picker);
        }
        const signature = JSON.stringify([choices,relative]);
        if (picker.dataset.locationSignature === signature || picker === document.activeElement) continue;
        picker.dataset.locationSignature = signature;
        picker.innerHTML = '<option value="">Choose Win64 or a saved location…</option>' + choices.map((row)=>{
          const value = relative ? row.game_relative : row.path;
          return `<option value="${esc(value||'')}" ${row.eligible?'':'disabled'}>${esc(row.label)} — ${esc(row.eligible?value:row.reason)}</option>`;
        }).join('');
      }
    } catch (error) { console.warn('Saved profile locations unavailable',error); }
  }

  document.addEventListener('change',(event)=>{
    const picker=event.target.closest?.('[data-profile-runtime-choice]');
    if(!picker||!picker.value)return;
    const root=picker.closest('.modal')||document;
    const input=root.querySelector('#'+picker.dataset.profileRuntimeChoice);
    if(!input)return;
    input.value=picker.value;
    input.dataset.userEdited='1';
    input.dispatchEvent(new Event('input',{bubbles:true}));
    input.dispatchEvent(new Event('change',{bubbles:true}));
    picker.value='';
  },true);

  function scheduleRewrite() {
    if (rewritePending) return;
    rewritePending = true;
    requestAnimationFrame(rewriteUi);
  }

  document.addEventListener('click', (event) => {
    const spare=event.target?.closest?.('[data-profile-spare-action]');
    if(spare){
      event.preventDefault();event.stopImmediatePropagation();
      const host=spare.closest('.profile-storage-destinations');
      const identity=host.querySelector('[data-open-profile-mod-lane]');
      const note=host.querySelector('[data-profile-spare-status]');
      spare.disabled=true;note.textContent='Working…';
      bridge.invoke('application.profile.protection',{kind:identity.dataset.profileKind,id:identity.dataset.profileId,action:spare.dataset.profileSpareAction,path:host.querySelector('[data-profile-spare-path]').value.trim()}).then(result=>{
        note.textContent=(spare.dataset.profileSpareAction==='unprotect'?'Protection removed; spare copies retained. ':'')+(result.folders?.length?result.folders.map(row=>`${row.path} (${row.file_count} files)`).join(' · '):'No protected folders.');
      }).catch(error=>{note.textContent=error.message||String(error);}).finally(()=>{spare.disabled=false;});
      return;
    }
    const folder=event.target?.closest?.('[data-open-profile-mod-lane]');
    if(folder){
      event.preventDefault();event.stopImmediatePropagation();
      const host=folder.closest('.profile-storage-destinations');
      let note=host?.querySelector('[data-profile-storage-status]');
      if(!note&&host){note=document.createElement('p');note.dataset.profileStorageStatus='1';note.setAttribute('role','status');host.append(note);}
      folder.disabled=true;
      Promise.resolve().then(()=>bridge.invoke('application.profile.mods_root',{kind:folder.dataset.profileKind,id:folder.dataset.profileId})).then(()=>bridge.openProfileMods(folder.dataset.profileKind,folder.dataset.profileId,folder.dataset.openProfileModLane)).then((result)=>{
        if(!result?.ok)throw Error(result?.error||'Could not open this profile folder');
        if(note)note.textContent='Opened '+result.path+'. Add files here, then scan the profile.';
      }).catch((error)=>{if(note)note.textContent=text(error.message||error);}).finally(()=>{folder.disabled=false;});
      return;
    }
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
  window.addEventListener('dragonwilds:state-updated', () => {machinePaths=null;scheduleRewrite();});
  window.addEventListener('DOMContentLoaded', scheduleRewrite, { once: true });
  scheduleRewrite();
})();
