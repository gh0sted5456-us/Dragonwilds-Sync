(() => {
  'use strict';
  const api = window.dragonwilds;
  if (!api?.invoke) return;
  const query = new URLSearchParams(location.search);
  let launch = {};
  try { launch = window.dragonwildsV3?.quickContext?.() || {}; } catch (_) {}
  const legacyQuick = query.get('quick') === '1' || query.get('minimal') === '1';
  const quickEnabled = launch.enabled === true || legacyQuick;
  const profileId = String(launch.profileId || query.get('worldId') || '');
  const fallbackKind = String(query.get('worldKind') || '');
  const mode = ['player','coop','server'].includes(String(launch.mode || ''))
    ? String(launch.mode)
    : (query.get('minimal') === '1' || fallbackKind === 'server' ? 'server' : (fallbackKind === 'private' ? 'coop' : 'player'));
  const autoStart = launch.autoStart === true || query.get('autoStart') === '1';
  let autoStartConsumed = false;
  let quickState = null;
  let consoleState = null;
  let consoleOpen = true;
  let consoleFilter = 'all';
  let consoleTarget = 'game';
  let activeOperation = '';
  let busy = false;
  let refreshInFlight = false;
  let refreshTimer = null;

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const statusClass = (value) => /active|running|current|success/i.test(String(value||'')) ? 'ok' : /partial|connecting|starting|updating/i.test(String(value||'')) ? 'warn' : /failed|error|stopped|disabled/i.test(String(value||'')) ? 'bad' : 'muted';
  const roleLabel = mode === 'server' ? 'Server' : (mode === 'coop' ? 'Co-Op' : 'Player');
  const scopeLabel = () => quickState?.profile_scope || (mode === 'server' ? 'Hosted Server' : 'World Profile');

  function toast(message, kind='info') {
    const node = document.createElement('div');
    node.className = `v3q-toast ${kind}`;
    node.textContent = String(message || '');
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 3400);
  }

  async function invoke(method, params={}) {
    busy = true; renderQuick();
    try { return await api.invoke(method, params); }
    finally { busy = false; }
  }

  async function refresh({consoleToo=consoleOpen}={}) {
    if (refreshInFlight) return;
    refreshInFlight = true;
    try {
      quickState = await api.invoke('quick.status', { profile_id: profileId, mode });
      if (consoleToo && quickState?.controls?.console) {
        try { consoleState = await api.invoke('quick.console.get', { profile_id: quickState.profile_id, mode, limit: 220 }); }
        catch (_) { consoleState = null; }
      }
      renderQuick();
      if (autoStart && !autoStartConsumed && !quickState?.active) {
        autoStartConsumed = true;
        await action('start');
      }
    } catch (error) {
      quickState = { profile_id: profileId, mode, world_name: 'Quick Launch', error: error?.message || String(error), controls:{} };
      renderQuick();
    } finally { refreshInFlight = false; }
  }

  function destinationRows() {
    const rows = [];
    const official = quickState?.network?.official || {};
    if (quickState?.profile_kind !== 'linked') {
      rows.push({name:'Dragonwilds Sync Network', state: quickState?.network?.public_directory_enabled ? (official.last_error_code ? 'Failed' : (official.last_success_at ? 'Active' : 'Connecting')) : 'Disabled', detail: official.last_error_code || (official.last_success_at ? 'Heartbeat delivered' : 'Automatic registration / heartbeat')});
    }
    for (const row of quickState?.network?.broadcast_destinations || []) {
      rows.push({name: row.name || 'Directory', state: row.enabled === false ? 'Disabled' : 'Configured', detail: row.endpoint || row.publish_policy || ''});
    }
    return rows;
  }

  function metric(label, value, cls='') {
    return `<div class="v3q-metric"><span>${esc(label)}</span><strong class="${cls}">${esc(value ?? '—')}</strong></div>`;
  }

  function quickConsole() {
    if (!consoleOpen) return '';
    const events = consoleState?.events || consoleState?.entries || consoleState?.history || [];
    const allRows = Array.isArray(events) ? events.slice(-220) : [];
    const rows = consoleFilter==='all' ? allRows : allRows.filter((row)=>String(row.source||'').toLowerCase()===consoleFilter);
    const filters=[['all','ALL'],['game','GAME'],['ue4ss','UE4SS'],['runeschema','RUNESCHEMA'],['server','SERVER'],['sync','SYNC']];
    return `<section class="v3q-panel v3q-console-panel">
      <div class="v3q-panel-head"><div><b>Runtime Console</b><small>One profile-scoped stream · source colors, filters, and guarded commands</small></div><button class="v3q-btn ghost" data-v3q-clear-console>Clear View</button></div>
      <nav class="v3q-console-filters" aria-label="Console source filters">${filters.map(([key,label])=>`<button class="v3q-btn ${consoleFilter===key?'primary':'ghost'}" data-v3q-console-filter="${key}">${label} <span>${key==='all'?allRows.length:allRows.filter((row)=>String(row.source||'').toLowerCase()===key).length}</span></button>`).join('')}</nav>
      <div class="v3q-console" data-v3q-console>${rows.length ? rows.map((row)=>{
        const ts = row.ts || row.time || row.created_at || '';
        const message = row.message || row.ack || row.command || row.line || JSON.stringify(row);
        const source=String(row.source||'system').toLowerCase().replace(/[^a-z0-9_-]/g,'-');
        return `<div class="source-${esc(source)}"><time>${esc(ts ? new Date(Number(ts)*1000 || ts).toLocaleTimeString?.() || ts : '')}</time><b>${esc(source.toUpperCase())}</b><span>${esc(message)}</span></div>`;
      }).join('') : '<div class="empty"><span>No console events for this filter yet.</span></div>'}</div>
      <form class="v3q-command" data-v3q-command-form><select name="target" aria-label="Command target"><option value="game" ${consoleTarget==='game'?'selected':''}>GAME / RSDWToolkit</option><option value="ue4ss" ${consoleTarget==='ue4ss'?'selected':''}>UE4SS / Unreal</option></select><input name="command" autocomplete="off" placeholder="Enter a command for the selected runtime…" ${quickState?.active?'':'disabled'}/><button class="v3q-btn primary" type="submit" ${quickState?.active?'':'disabled'}>Run</button></form>
    </section>`;
  }

  function launchPlan() {
    const steps=Array.isArray(quickState?.launch_sequence)?quickState.launch_sequence:[];
    if(!steps.length)return '';
    const launching=['play','host','start','restart','update_restart'].includes(activeOperation);
    return `<section class="v3q-panel v3q-launch-plan ${launching?'running':''}"><div class="v3q-panel-head"><div><b>${esc(scopeLabel())} launch path</b><small>${launching?'Running these guarded stages in order…':'Quick uses the same authoritative profile pipeline as Full.'}</small></div></div><ol>${steps.map((step,index)=>`<li><i>${index+1}</i><span>${esc(step)}</span></li>`).join('')}</ol></section>`;
  }

  function broadcastBox() {
    if (!quickState?.controls?.broadcast_message) return '';
    return `<section class="v3q-panel">
      <div class="v3q-panel-head"><div><b>Broadcast Message</b><small>Uses the same World announcement backend as Full and WebGUI</small></div></div>
      <form class="v3q-broadcast" data-v3q-broadcast-form><input name="message" maxlength="1000" placeholder="Message players…"/><button class="v3q-btn" type="submit">Broadcast</button></form>
    </section>`;
  }

  function renderQuick() {
    if (!quickEnabled) return;
    const root = document.getElementById('app');
    if (!root) return;
    document.body.classList.add('v3-quick-body');
    const runtimeState = quickState?.runtime?.state || (quickState?.active ? 'Running' : 'Stopped');
    const networkState = destinationRows();
    const publicEnabled = !!quickState?.network?.public_directory_enabled;
    const players = Array.isArray(quickState?.players) ? quickState.players : [];
    const error = quickState?.error;
    const markup = `<main class="v3q-shell" data-v3-quick-root>
      <header class="v3q-header">
        <div class="v3q-brand"><span class="v3q-mark">DW</span><div><small>DRAGONWILDS SYNC QUICK · ${esc(scopeLabel().toUpperCase())} MANAGEMENT</small><h1>${esc(quickState?.world_name || 'Loading World…')}</h1></div></div>
        <div class="v3q-header-actions"><button class="v3q-btn ghost" data-v3q-refresh ${busy?'disabled':''}>Refresh</button><button class="v3q-btn" data-v3q-full>Open Full Dragonwilds Sync</button></div>
      </header>
      ${error ? `<div class="v3q-error">${esc(error)}</div>` : ''}
      <section class="v3q-status-grid">
        ${metric('Mode', roleLabel)}
        ${metric(mode==='server'?'Server Status':(mode==='coop'?'Host State':'Game'), runtimeState, statusClass(runtimeState))}
        ${metric('CL / Build', quickState?.cl || 'Unknown')}
        ${metric('Mods', `${quickState?.mods?.count ?? 0}${quickState?.mods?.cached ? ' cached' : ''}`)}
        ${metric('Sync', quickState?.sync?.serving ? `Serving${quickState.sync.port ? ` · ${quickState.sync.port}` : ''}` : 'Not serving', statusClass(quickState?.sync?.serving?'active':'stopped'))}
        ${metric('Heartbeat', networkState[0]?.state || 'Local only', statusClass(networkState[0]?.state))}
      </section>
      <section class="v3q-toolbar">
        ${quickState?.controls?.play ? `<button class="v3q-btn primary big" data-v3q-action="start" ${busy||quickState?.active?'disabled':''}>${quickState?.active?'Dragonwilds Running':'Play'}</button>`:''}
        ${quickState?.controls?.host ? `<button class="v3q-btn primary big" data-v3q-action="start" ${busy||quickState?.active?'disabled':''}>${quickState?.active?'Co-Op Active':'Start Co-Op'}</button>`:''}
        ${quickState?.controls?.start ? `<button class="v3q-btn primary big" data-v3q-action="start" ${busy||quickState?.active?'disabled':''}>Start</button>`:''}
        ${quickState?.controls?.stop ? `<button class="v3q-btn danger" data-v3q-action="stop" ${busy||!quickState?.active?'disabled':''}>Stop</button>`:''}
        ${quickState?.controls?.restart ? `<button class="v3q-btn" data-v3q-action="restart" ${busy||!quickState?.active?'disabled':''}>Restart</button>`:''}
        ${quickState?.controls?.update_restart ? `<button class="v3q-btn" data-v3q-action="update_restart" ${busy?'disabled':''}>Update & Restart</button>`:''}
        <button class="v3q-btn ghost" data-v3q-mods>View Mods</button>
        ${quickState?.controls?.console?`<button class="v3q-btn ghost" data-v3q-console-toggle>${consoleOpen?'Hide Console':'Open Console'}</button>`:''}
      </section>
      <div class="v3q-columns">
        <section class="v3q-panel">
          <div class="v3q-panel-head"><div><b>World & Network</b><small>Presence and World publication are independent</small></div></div>
          <div class="v3q-world-meta"><span>Profile ID</span><code>${esc(quickState?.profile_id || profileId)}</code></div>
          <div class="v3q-world-meta"><span>Profile</span><b>${esc(quickState?.profile_kind || '—')}</b></div>
          ${quickState?.profile_kind !== 'linked' ? `<label class="v3q-toggle"><input type="checkbox" data-v3q-public ${publicEnabled?'checked':''}/><span><b>Broadcast this World publicly</b><small>Official World publication. Does not control anonymous application presence.</small></span></label>`:''}
          <div class="v3q-destinations">${networkState.length ? networkState.map((row)=>`<div><span class="dot ${statusClass(row.state)}"></span><b>${esc(row.name)}</b><em>${esc(row.state)}</em><small>${esc(row.detail)}</small></div>`).join('') : '<small>No public destinations configured.</small>'}</div>
        </section>
        ${mode === 'server' ? `<section class="v3q-panel"><div class="v3q-panel-head"><div><b>Players</b><small>${players.length} connected / observed</small></div></div><div class="v3q-players">${players.length ? players.map((p)=>`<span>${esc(p.name || p.player_name || p.id || 'Player')}</span>`).join('') : '<small>No players reported.</small>'}</div></section>` : `<section class="v3q-panel"><div class="v3q-panel-head"><div><b>${mode==='coop'?'Co-Op Host':scopeLabel()}</b><small>Same profile/runtime materialization used by Full</small></div></div><p class="v3q-copy">${esc(quickState?.description || (mode==='coop'?'Launch the local profile, then Quick can enable its Co-Op Sync host.':quickState?.profile_kind==='linked'?'Match files, transfer changes, verify parity, prepare DragonConnect, then play.':'Materialize this local profile and launch it without contacting a remote Sync host.'))}</p></section>`}
      </div>
      ${launchPlan()}
      ${broadcastBox()}
      ${quickConsole()}
      <footer class="v3q-footer"><span>${busy?'Working…':'Ready'}</span><span>Open Full promotes this same launcher process; it does not duplicate the backend or runtime.</span></footer>
    </main>`;
    if (root.__dwsQuickMarkup === markup) return;
    root.__dwsQuickMarkup = markup;
    root.innerHTML = markup;
    bindQuick();
  }

  async function action(name) {
    if (busy) return;
    activeOperation=name;renderQuick();
    try {
      if (name === 'start') await invoke('quick.start', { profile_id: quickState?.profile_id || profileId, mode });
      else if (name === 'stop') await invoke('quick.stop', { profile_id: quickState?.profile_id || profileId, mode });
      else if (name === 'restart') await invoke('quick.restart', { profile_id: quickState?.profile_id || profileId, mode });
      else if (name === 'update_restart') await invoke('quick.update_restart', { profile_id: quickState?.profile_id || profileId, mode });
      toast(`${roleLabel} ${name.replace('_',' ')} completed`, 'success');
    } catch (error) { toast(error?.message || String(error), 'error'); }
    activeOperation='';
    await refresh();
  }

  function bindQuick() {
    const root = document.querySelector('[data-v3-quick-root]');
    if (!root) return;
    root.querySelector('[data-v3q-refresh]')?.addEventListener('click', ()=>refresh());
    root.querySelector('[data-v3q-full]')?.addEventListener('click', ()=>api.openMainWindow?.());
    root.querySelector('[data-v3q-mods]')?.addEventListener('click', async()=>{
      const target = String(quickState?.mods?.path || '');
      if (target && api.openPath) {
        try { await api.openPath(target); return; } catch (_) {}
      }
      api.openMainWindow?.();
    });
    root.querySelector('[data-v3q-console-toggle]')?.addEventListener('click',async()=>{consoleOpen=!consoleOpen;if(consoleOpen)await refresh({consoleToo:true});else renderQuick();});
    root.querySelectorAll('[data-v3q-console-filter]').forEach((button)=>button.addEventListener('click',()=>{consoleFilter=button.dataset.v3qConsoleFilter||'all';renderQuick();}));
    root.querySelectorAll('[data-v3q-action]').forEach((button)=>button.addEventListener('click', ()=>action(button.dataset.v3qAction)));
    root.querySelector('[data-v3q-public]')?.addEventListener('change', async(event)=>{
      const enabled = !!event.currentTarget.checked;
      try {
        const kind = mode === 'server' ? 'dedicated' : 'local';
        await invoke('network.world.settings', { id: quickState?.profile_id || profileId, kind, public_directory_enabled: enabled });
        toast(enabled ? 'Public World broadcast enabled' : 'Public World broadcast disabled', 'success');
      } catch (error) { event.currentTarget.checked = !enabled; toast(error?.message || String(error), 'error'); }
      await refresh({consoleToo:false});
    });
    root.querySelector('[data-v3q-command-form]')?.addEventListener('submit', async(event)=>{
      event.preventDefault(); const input=event.currentTarget.elements.command; const command=String(input?.value||'').trim(); if(!command)return;consoleTarget=event.currentTarget.elements.target?.value||'game';
      try { await invoke('quick.console.execute',{profile_id:quickState?.profile_id||profileId,mode,command,target:consoleTarget}); input.value=''; toast('Command completed','success'); }
      catch(error){toast(error?.message||String(error),'error');}
      await refresh();
    });
    root.querySelector('[data-v3q-clear-console]')?.addEventListener('click',()=>{consoleState={history:[],events:[],entries:[]};renderQuick();});
    root.querySelector('[data-v3q-broadcast-form]')?.addEventListener('submit', async(event)=>{
      event.preventDefault(); const input=event.currentTarget.elements.message; const message=String(input?.value||'').trim(); if(!message)return;
      try { await invoke('quick.broadcast',{profile_id:quickState?.profile_id||profileId,mode,message}); input.value=''; toast('Broadcast sent','success'); }
      catch(error){toast(error?.message||String(error),'error');}
      await refresh({consoleToo:false});
    });
    const consoleNode=root.querySelector('[data-v3q-console]'); if(consoleNode) consoleNode.scrollTop=consoleNode.scrollHeight;
  }

  // ---------- Full application additive controls ----------
  let picker = null;
  function closePicker(){ picker?.remove(); picker=null; }
  function openShortcutPicker({id,name,server}) {
    closePicker();
    const modes = server ? ['server'] : ['player','coop'];
    picker=document.createElement('div'); picker.className='v3q-picker-backdrop';
    picker.innerHTML=`<div class="v3q-picker"><button class="v3q-picker-x" aria-label="Close">×</button><small>CREATE QUICK SHORTCUT</small><h3>${esc(name||'World')}</h3><p>Shortcuts use the stable profile ID. Renaming the World will not break them.</p>${modes.map((m)=>`<div class="v3q-picker-role"><b>${m==='server'?'Server':m==='coop'?'Co-Op':'Player'}</b><button data-v3q-shortcut="${m}:open">Open Quick</button><button data-v3q-shortcut="${m}:start">Open Quick + Start</button></div>`).join('')}</div>`;
    document.body.appendChild(picker); picker.querySelector('.v3q-picker-x')?.addEventListener('click',closePicker); picker.addEventListener('click',(e)=>{if(e.target===picker)closePicker();});
    picker.querySelectorAll('[data-v3q-shortcut]').forEach((button)=>button.addEventListener('click',async()=>{
      const [selected,behavior]=button.dataset.v3qShortcut.split(':');
      try { await window.dragonwildsV3?.createQuickShortcut?.({profileId:id,name,mode:selected,autoStart:behavior==='start'}); toast('Quick shortcut created','success'); closePicker(); }
      catch(error){toast(error?.message||String(error),'error');}
    }));
  }

  function enhanceShortcuts() {
    if (quickEnabled) return;
    document.querySelectorAll('[data-server-manage],[data-private-manage]').forEach((manage)=>{
      const parent=manage.parentElement; if(!parent || parent.querySelector('[data-v3q-create-shortcut]'))return;
      const server=manage.hasAttribute('data-server-manage'); const id=manage.getAttribute(server?'data-server-manage':'data-private-manage')||'';
      const card=manage.closest('[data-world-id],article'); const name=card?.querySelector('h3')?.textContent?.trim()||'Dragonwilds World';
      const button=document.createElement('button'); button.className='btn ghost compact-btn'; button.dataset.v3qCreateShortcut=id; button.textContent='Create Quick Shortcut';
      button.addEventListener('click',(event)=>{event.preventDefault();event.stopPropagation();openShortcutPicker({id,name,server});}); parent.appendChild(button);
    });
  }

  async function enhanceNetworkSettings() {
    if (quickEnabled) return;
    const content=[...document.querySelectorAll('.content')].find((node)=>/settings/i.test(node.querySelector('h1')?.textContent||''));
    if(!content || content.querySelector('[data-v3-network-settings]'))return;
    const header=content.querySelector('.page-header'); if(!header)return;
    const panel=document.createElement('section'); panel.className='v3q-full-network-card'; panel.dataset.v3NetworkSettings='1';
    panel.innerHTML='<div><small>DRAGONWILDS SYNC NETWORK</small><b>Network participation</b><span>Anonymous application presence is separate from each World\'s public broadcast setting.</span></div><label><input type="checkbox" disabled/><span>Participate in Dragonwilds Sync Network</span></label><em>Loading…</em>';
    header.insertAdjacentElement('afterend',panel);
    try {
      const status=await api.invoke('network.status',{}); const input=panel.querySelector('input'); input.disabled=false; input.checked=status.presence_enabled!==false;
      panel.querySelector('em').textContent=status.registered?'Installation registered':'Automatic registration will occur when the official service supports it';
      input.addEventListener('change',async()=>{input.disabled=true;try{await api.invoke('network.settings',{presence_enabled:input.checked});toast(input.checked?'Network participation enabled':'Network participation disabled','success');}catch(error){input.checked=!input.checked;toast(error?.message||String(error),'error');}finally{input.disabled=false;}});
    } catch(error){panel.querySelector('em').textContent=error?.message||String(error);}
  }

  if (quickEnabled) {
    const scheduleRefresh=()=>{if(refreshTimer)clearTimeout(refreshTimer);refreshTimer=setTimeout(async()=>{await refresh();scheduleRefresh();},document.hidden?30000:(quickState?.active?5000:10000));};
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();scheduleRefresh();});
    document.addEventListener('DOMContentLoaded',async()=>{await refresh();scheduleRefresh();},{once:true});
    window.addEventListener('beforeunload',()=>{if(refreshTimer)clearTimeout(refreshTimer);});
  } else {
    const observer=new MutationObserver(()=>{enhanceShortcuts();enhanceNetworkSettings();});
    observer.observe(document.documentElement,{subtree:true,childList:true});
    document.addEventListener('DOMContentLoaded',()=>{enhanceShortcuts();enhanceNetworkSettings();},{once:true});
  }
})();
