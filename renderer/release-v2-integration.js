(() => {
  'use strict';

  const bridge = window.dragonwilds;
  let cachedState = null;
  let fetchedAt = 0;
  let scheduled = false;
  const permissionLabels = {
    view_overview:'View overview', view_map:'View live map', view_maintenance:'View maintenance', write_maintenance:'Edit maintenance',
    view_mods:'View mods', write_mods:'Edit mods', view_config:'View configuration', write_config:'Edit configuration',
    view_spawner:'View item repository', use_spawner:'Use item spawner', view_console:'View game console', use_console:'Use game console',
    view_audit:'View audit log', send_announcements:'Send announcements', start:'Start server', stop:'Stop server', restart:'Restart server', update:'Update server', refresh:'Refresh metadata'
  };

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  function iconMode() {
    try { const saved=localStorage.getItem('dragonwilds-sync-icon-mode'); return ['color','adaptive','black','white'].includes(saved)?saved:'color'; }
    catch (_) { return 'color'; }
  }
  function applyIconMode(){ document.documentElement.dataset.dwsIconMode=iconMode(); }

  async function state(force=false){
    if(window.__DWSYNC_STATE__){cachedState=window.__DWSYNC_STATE__;fetchedAt=Date.now();return cachedState;}
    if(!bridge?.invoke)return cachedState||{};
    if(!force&&cachedState&&Date.now()-fetchedAt<1800)return cachedState;
    try{cachedState=await bridge.invoke('state.get',{});fetchedAt=Date.now();}catch(_){}
    return cachedState||{};
  }
  async function invoke(method,params={}){const result=await bridge.invoke(method,params);cachedState=result?.application?result:await bridge.invoke('state.get',{});fetchedAt=Date.now();return result;}

  function retireStandaloneRemoteEntries(root=document){
    root.querySelector('#toggle-remote-server-feature')?.closest('.settings-row')?.classList.add('dws-v2-retired-remote-entry');
    root.querySelectorAll('aside a,aside button,nav a,nav button').forEach(node=>{if(node.closest('.webhost-tabs'))return;const label=String(node.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();if(label==='remote server'||label==='remote server login')node.classList.add('dws-v2-retired-remote-entry');});
  }

  function permissionSummary(permissions){return Object.entries(permissions||{}).filter(([,enabled])=>enabled).map(([key])=>permissionLabels[key]||key).slice(0,8);}

  function closeUserEditor(){document.querySelector('#dws-v2-user-editor')?.remove();}
  function confirmRemoteUserDeletion(username){return new Promise((resolve)=>{const overlay=document.createElement('section');overlay.className='dws-v2-user-editor';overlay.id='dws-v2-delete-confirm';overlay.innerHTML=`<div class="dws-v2-user-editor-card" style="width:min(520px,100%)"><div class="eyebrow">Remote Server authority</div><h2>Delete Remote User?</h2><p>Delete <strong>${esc(username)}</strong>? Existing sessions lose their grants. This does not alter the assigned World.</p><div class="dws-v2-editor-actions"><button class="btn ghost" data-answer="0">Cancel</button><button class="btn danger" data-answer="1">Delete Remote User</button></div></div>`;document.body.appendChild(overlay);const finish=value=>{overlay.remove();resolve(value)};overlay.querySelectorAll('[data-answer]').forEach(button=>button.onclick=()=>finish(button.dataset.answer==='1'));overlay.onclick=event=>{if(event.target===overlay)finish(false)};});}
  async function openUserEditor(user=null){
    const snapshot=await state(true),host=snapshot?.application?.world_directory_host||{},remote=host.remote_admin||{},profiles=snapshot?.server_profiles||[];
    const current=user?.permissions||remote.permissions||{};
    const overlay=document.createElement('section');overlay.className='dws-v2-user-editor';overlay.id='dws-v2-user-editor';
    overlay.innerHTML=`<div class="dws-v2-user-editor-card"><div class="eyebrow">Remote Server authority</div><h2>${user?'Edit':'Add'} Remote User</h2><p class="muted-small">Credentials are validated only by this target Dragonwilds Sync server. Password hashes and permission grants are never published in heartbeats.</p><div class="dws-v2-user-editor-grid"><label><small>Username</small><input class="field" id="dws-user-name" value="${esc(user?.username||'')}" ${user?'readonly':''}></label><label><small>${user?'New password (optional)':'Password'}</small><input class="field" id="dws-user-password" type="password" autocomplete="new-password" placeholder="At least 10 characters"></label><label class="full"><small>Hosted World</small><select class="select" id="dws-user-world" ${user?'disabled':''}>${profiles.map(profile=>`<option value="${esc(profile.id)}" ${String(profile.id)===String(user?.world_id)?'selected':''}>${esc(profile.name||profile.id)}</option>`).join('')}</select></label></div><div class="dws-v2-permission-grid">${Object.entries(permissionLabels).map(([key,label])=>`<label><input type="checkbox" data-dws-user-permission="${esc(key)}" ${current[key]?'checked':''}><span><strong>${esc(label)}</strong><small>${key.startsWith('write_')||['use_spawner','use_console','send_announcements','start','stop','restart','update'].includes(key)?'Mutation / operation authority':'Read authority'}</small></span></label>`).join('')}</div><div id="dws-user-error" class="muted-small"></div><div class="dws-v2-editor-actions"><button class="btn ghost" id="dws-user-cancel">Cancel</button><button class="btn primary" id="dws-user-save">Save Remote User</button></div></div>`;
    document.body.appendChild(overlay);overlay.querySelector('#dws-user-cancel').onclick=closeUserEditor;overlay.onclick=e=>{if(e.target===overlay)closeUserEditor();};
    overlay.querySelector('#dws-user-save').onclick=async()=>{const username=overlay.querySelector('#dws-user-name').value.trim(),password=overlay.querySelector('#dws-user-password').value,world_id=overlay.querySelector('#dws-user-world').value||user?.world_id||'',permissions={};overlay.querySelectorAll('[data-dws-user-permission]').forEach(input=>permissions[input.dataset.dwsUserPermission]=!!input.checked);const error=overlay.querySelector('#dws-user-error');try{await invoke(user?'application.world_directory_host.user.update':'application.world_directory_host.user.create',{username,password,world_id,permissions});closeUserEditor();schedule();}catch(exc){error.textContent=exc.message||String(exc);}};
  }

  async function renderRemotePanel(root,snapshot){
    const tab=root.querySelector('[data-webhost-tab="remote"].active');const nav=root.querySelector('.webhost-tabs');if(!nav)return;
    const container=nav.parentElement;
    container.querySelectorAll(':scope > .settings-section').forEach(section=>section.classList.toggle('dws-v2-remote-hidden',!!tab));
    let panel=container.querySelector('#dws-v2-remote-panel');
    if(!tab){panel?.remove();return;}
    const host=snapshot?.application?.world_directory_host||{},status=snapshot?.application?.world_directory_host_status||{},remote=host.remote_admin||{},users=remote.users||[],requests=(remote.permission_requests||[]).filter(row=>row.status==='pending'),profiles=snapshot?.server_profiles||[];
    const localBase=String(status.local_url||'').replace(/\/$/,'');
    const profileName=id=>profiles.find(row=>String(row.id)===String(id))?.name||id||'No World';
    if(!panel){panel=document.createElement('section');panel.id='dws-v2-remote-panel';panel.className='dws-v2-remote-panel';nav.insertAdjacentElement('afterend',panel);}
    const stamp=JSON.stringify([users.map(u=>[u.username,u.world_id,u.enabled,u.permissions]),requests,profiles.map(p=>[p.id,p.name]),localBase,status.serving]);if(panel.dataset.stamp===stamp)return;panel.dataset.stamp=stamp;
    panel.innerHTML=`<div class="dws-v2-remote-summary"><div><div class="eyebrow">Sync · target-owned authority</div><h2>Remote Server Manager</h2><p>Remote users, World assignments, and explicit permissions stay within Sync. These administrative credentials never participate in player connection, heartbeat discovery, or Dragonwilds World Password validation.</p></div><div class="header-actions"><button class="btn ghost" id="dws-v2-remote-preview" ${localBase?'':'disabled'}>${localBase?'Load Login Preview':'Listener Offline'}</button><button class="btn primary" id="dws-v2-add-user">+ Add Remote User</button></div></div><section class="settings-section dws-v2-remote-preview" id="dws-v2-remote-preview-stage" hidden><div class="panel-header"><div><h2>Remote Login Preview</h2><span class="panel-subtitle">Loads only when requested and uses the same responsive page remote users receive.</span></div></div><div class="webhost-preview-frame"><webview id="dws-v2-remote-webview" partition="persist:webhost-preview" webpreferences="contextIsolation=yes,nodeIntegration=no,sandbox=yes,devTools=no"></webview></div></section><section class="settings-section"><div class="panel-header"><div><h2>Users & Permissions</h2><span class="panel-subtitle">PBKDF2-hashed credentials · one hosted World per user · explicit grants</span></div><span class="status-pill ${users.length?'online':'unknown'}">${users.length} USERS</span></div><div class="dws-v2-user-list">${users.length?users.map(user=>{const perms=permissionSummary(user.permissions);return `<article class="dws-v2-user"><div><strong>${esc(user.username||'User')}</strong><small>${esc(profileName(user.world_id))} · ${user.enabled===false?'Disabled':'Enabled'} · ${Object.values(user.permissions||{}).filter(Boolean).length} grants</small><div class="dws-v2-user-perms">${perms.map(label=>`<span>${esc(label)}</span>`).join('')}${Object.values(user.permissions||{}).filter(Boolean).length>perms.length?'<span>…</span>':''}</div></div><div class="header-actions"><button class="btn ghost compact-btn" data-dws-edit-user="${esc(user.username||'')}">Edit</button><button class="btn danger compact-btn" data-dws-delete-user="${esc(user.username||'')}">Delete</button></div></article>`}).join(''):'<div class="empty-state compact-empty">No Remote Users yet. The World owner can still use the Server Admin Password recovery path.</div>'}</div></section><section class="settings-section"><div class="panel-header"><div><h2>Permission Requests</h2><span class="panel-subtitle">Remote sessions cannot grant themselves additional authority.</span></div><span class="status-pill ${requests.length?'unknown':'online'}">${requests.length} PENDING</span></div><div class="dws-v2-permission-requests">${requests.length?requests.map(request=>`<div class="dws-v2-permission-request"><div><strong>${esc(request.username||'User')} · ${esc(permissionLabels[request.permission]||request.permission||'permission')}</strong><small>${request.requested_at?new Date(Number(request.requested_at)*1000).toLocaleString():''}</small></div><div class="header-actions"><button class="btn primary compact-btn" data-dws-request="${esc(request.id||'')}" data-approve="1">Approve</button><button class="btn ghost compact-btn" data-dws-request="${esc(request.id||'')}" data-approve="0">Deny</button></div></div>`).join(''):'<div class="empty-state compact-empty">No pending permission requests.</div>'}</div></section>`;
    panel.querySelector('#dws-v2-add-user').onclick=()=>openUserEditor();panel.querySelector('#dws-v2-remote-preview').onclick=()=>{const stage=panel.querySelector('#dws-v2-remote-preview-stage'),view=panel.querySelector('#dws-v2-remote-webview');stage.hidden=false;if(view&&!view.src)view.src=`${localBase}/admin/login`;stage.scrollIntoView({behavior:'smooth',block:'start'});};panel.querySelectorAll('[data-dws-edit-user]').forEach(button=>button.onclick=()=>{const user=users.find(row=>row.username===button.dataset.dwsEditUser);if(user)openUserEditor(user);});panel.querySelectorAll('[data-dws-delete-user]').forEach(button=>button.onclick=async()=>{if(!await confirmRemoteUserDeletion(button.dataset.dwsDeleteUser))return;await invoke('application.world_directory_host.user.delete',{username:button.dataset.dwsDeleteUser});schedule();});panel.querySelectorAll('[data-dws-request]').forEach(button=>button.onclick=async()=>{await invoke('application.world_directory_host.permission.resolve',{id:button.dataset.dwsRequest,approve:button.dataset.approve==='1'});schedule();});
  }

  async function applyWebHostContract(root=document){
    const snapshot=await state(),application=snapshot?.application||{},advanced=application.advanced||{},host=application.world_directory_host||{},remote=host.remote_admin||{},webHostActivated=!!advanced.webhost_enabled,remoteEnabled=!!remote.enabled;
    const declared=root.querySelector('[data-vnext-world-tab="declared"]');if(declared){declared.hidden=!webHostActivated;declared.style.display=webHostActivated?'':'none';}
    const remoteTab=root.querySelector('[data-webhost-tab="remote"]');if(remoteTab){remoteTab.hidden=false;remoteTab.style.removeProperty('display');remoteTab.textContent='Server Management';remoteTab.title=remoteEnabled?'Remote Server Manager users, permissions, and requests':'Set up Remote Server Manager users and permissions';}
    const toggle=root.querySelector('#toggle-webhost-remote-admin'),row=toggle?.closest('.settings-row');if(row){const title=row.querySelector('.settings-copy strong'),copy=row.querySelector('.settings-copy span');if(title)title.textContent='Remote Server';if(copy)copy.textContent='Enable target-owned remote login. Server Management remains available here for setup and status.';}
    root.querySelectorAll('[data-webhost-tab="manifest"]').forEach(button=>button.textContent='Manifest & Heartbeats');
    // Old authority sections are duplicates. The dedicated Remote Server tab is
    // now the only desktop place that exposes users and grants.
    root.querySelectorAll('.webhost-authority').forEach(section=>section.classList.add('dws-v2-retired-remote-entry'));
    await renderRemotePanel(root,snapshot);
  }

  function smoothIconNodes(root=document){root.querySelectorAll('.platform-logo,.world-platform-badge img,.world-community-badge img,.world-audience-badge img').forEach(img=>{img.dataset.iconVariants='color black white';img.draggable=false;if(img.dataset.iconFallbackBound)return;img.dataset.iconFallbackBound='1';const shell=img.closest('.platform-logo-shell');const markFailed=()=>shell?.classList.add('icon-missing');img.addEventListener('error',markFailed,{once:true});if(img.complete&&img.naturalWidth===0)markFailed();});}
  async function enhance(){applyIconMode();retireStandaloneRemoteEntries();smoothIconNodes();await applyWebHostContract();}
  function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;void enhance();});}

  window.addEventListener('dragonwilds:icon-mode',event=>{const mode=String(event.detail?.mode||'');if(!['color','adaptive','black','white'].includes(mode))return;try{localStorage.setItem('dragonwilds-sync-icon-mode',mode);}catch(_){}applyIconMode();});
  window.addEventListener('dragonwilds:state-updated',(event)=>{cachedState=event.detail||window.__DWSYNC_STATE__||cachedState;fetchedAt=Date.now();schedule();});
  applyIconMode();if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
})();
