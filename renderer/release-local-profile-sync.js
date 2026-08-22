(() => {
  'use strict';
  const api = window.dragonwilds; if (!api?.invoke) return;
  const state = () => window.__DWSYNC_STATE__ || {}; let syncTimer = null;
  function inject() {
    if (document.querySelector('#profile-local-sync')) return;
    const page = document.querySelector('.settings-page.active,.settings-content,.settings-page'); if (!page || !/settings|application|profile/i.test(page.textContent || '')) return;
    const link = state()?.application?.profile_local_sync || {}; const host = document.createElement('section'); host.id = 'profile-local-sync'; host.className = 'settings-section profile-local-sync';
    host.innerHTML = `<div><div class="eyebrow">LOCAL CLOUD LINK</div><h2>Profile folder sync</h2><p>Save an atomic RSDWL profile into a folder managed by the installed OneDrive or Google Drive desktop client.</p></div><div class="profile-local-sync-grid"><label>Provider<select class="field" data-local-sync-provider><option value="onedrive">OneDrive</option><option value="google-drive">Google Drive</option></select></label><label>Linked folder<input class="field" data-local-sync-folder readonly placeholder="Choose a local synced folder"/></label><button class="btn ghost" data-local-sync-choose>Choose folder</button><label class="profile-local-sync-enabled"><input type="checkbox" data-local-sync-enabled/> Automatically refresh linked profile</label><button class="btn primary" data-local-sync-save>Save link</button><button class="btn ghost" data-local-sync-now>Sync now</button></div><small data-local-sync-status>${link.last_synced_at ? `Last synced ${new Date(link.last_synced_at).toLocaleString()}` : 'Not linked yet.'}</small>`;
    page.appendChild(host); const provider = host.querySelector('[data-local-sync-provider]'); const folder = host.querySelector('[data-local-sync-folder]'); const enabled = host.querySelector('[data-local-sync-enabled]'); const status = host.querySelector('[data-local-sync-status]');
    provider.value = link.provider || 'onedrive'; folder.value = link.folder || ''; enabled.checked = !!link.enabled;
    host.querySelector('[data-local-sync-choose]').onclick = async () => { const selected = await api.pickDirectory?.(); if (selected) folder.value = selected; };
    host.querySelector('[data-local-sync-save]').onclick = async () => { try { status.textContent = 'Saving link…'; const result = await api.invoke('profile.local_sync.configure',{provider:provider.value,folder:folder.value,enabled:enabled.checked}); window.__DWSYNC_STATE__ = result.state || state(); status.textContent = enabled.checked ? 'Linked. Profile changes will sync automatically.' : 'Link saved; automatic sync is disabled.'; } catch (error) { status.textContent = error.message || String(error); } };
    host.querySelector('[data-local-sync-now]').onclick = async () => { try { status.textContent = 'Writing atomic profile bundle…'; const result = await api.invoke('profile.local_sync.run',{}); window.__DWSYNC_STATE__ = result.state || state(); status.textContent = `Saved ${result.result?.path || 'linked profile'}`; } catch (error) { status.textContent = error.message || String(error); } };
  }
  function scheduleAutomaticSync() { const link = state()?.application?.profile_local_sync || {}; if (!link.enabled || !link.folder) return; clearTimeout(syncTimer); syncTimer = setTimeout(() => api.invoke('profile.local_sync.run',{}).catch(() => {}), 45000); }
  new MutationObserver(() => requestAnimationFrame(inject)).observe(document.documentElement,{childList:true,subtree:true});
  window.addEventListener('dragonwilds:state-updated',()=>{inject();scheduleAutomaticSync();}); requestAnimationFrame(inject);
})();
