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
  let autoStart = launch.autoStart === true || query.get('autoStart') === '1';
  const autoStartStorageKey = `dwsync.quick.autostart.${profileId || 'default'}.${mode}`;
  if (!autoStart) autoStart = localStorage.getItem(autoStartStorageKey) === '1';
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
  let verifiedPlayReady = false;
  let quickFollowTail = true;
  let quickSection = 'overview';
  let quickSpawner = {loaded:false,loading:false,items:[],players:[],query:'',page:0,selectedPath:'',selectedName:'',playerId:'',count:1,error:''};
  let quickSaves = {loaded:false,loading:false,data:null,error:''};
  let quickSavePlayer = '';
  let quickConsoleScrollTop = 0;
  const defaultConsoleColors={game:'#79b8ff',ue4ss:'#f38b8b',runeschema:'#65d8cf',chat:'#caa7ff',server:'#f1bf62',sync:'#72d39c'};
  let quickConsoleColors={...defaultConsoleColors};
  try{quickConsoleColors={...quickConsoleColors,...JSON.parse(localStorage.getItem('dwsync.console.colors')||'{}')};}catch(_){}
  const applyConsoleColors=()=>Object.entries(quickConsoleColors).forEach(([key,value])=>document.documentElement.style.setProperty(`--dws-console-${key}`,value));
  applyConsoleColors();
  const chooseConsoleColor=(key,label)=>{
    if(!defaultConsoleColors[key])return;
    const picker=document.createElement('input');
    picker.type='color';picker.value=quickConsoleColors[key]||defaultConsoleColors[key];picker.className='v3q-native-color-picker';
    picker.setAttribute('aria-label',`Choose ${label} console color`);document.body.appendChild(picker);
    const save=()=>{quickConsoleColors[key]=picker.value;localStorage.setItem('dwsync.console.colors',JSON.stringify(quickConsoleColors));applyConsoleColors();};
    const cleanup=()=>setTimeout(()=>picker.remove(),0);
    picker.addEventListener('input',save);picker.addEventListener('change',()=>{save();cleanup();},{once:true});picker.addEventListener('blur',cleanup,{once:true});
    try{if(typeof picker.showPicker==='function')picker.showPicker();else picker.click();}catch(_){picker.click();}
  };

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const dataImage = (value, fallback) => {
    const source=String(value||'').trim();
    if(/^data:image\/(?:png|jpe?g|webp|gif);base64,[A-Za-z0-9+/=\s]+$/i.test(source))return source;
    if(source.length>96&&/^[A-Za-z0-9+/=\s]+$/.test(source))return `data:image/png;base64,${source.replace(/\s+/g,'')}`;
    return fallback;
  };
  const statusClass = (value) => /active|running|current|success/i.test(String(value||'')) ? 'ok' : /partial|connecting|starting|updating/i.test(String(value||'')) ? 'warn' : /failed|error|stopped|disabled/i.test(String(value||'')) ? 'bad' : 'muted';
  const localFileUrl = (value) => {const source=String(value||'').trim();if(!source)return '';if(/^(data:|assets\/|https?:|file:)/i.test(source))return source;const normalized=source.replace(/\\/g,'/').replace(/#/g,'%23');return normalized.startsWith('/')?`file://${normalized}`:`file:///${normalized}`;};
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

  const formatBytes = (value) => {
    const bytes = Math.max(0, Number(value || 0));
    if (bytes < 1024) return `${Math.round(bytes)} B`;
    const units = ['KB','MB','GB','TB'];
    let amount = bytes / 1024, index = 0;
    while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
    return `${amount >= 100 ? amount.toFixed(0) : amount >= 10 ? amount.toFixed(1) : amount.toFixed(2)} ${units[index]}`;
  };

  function telemetryGraph(label, values, formatter, ceiling, tone, subtitle='') {
    const samples = values.map(Number).filter(Number.isFinite).slice(-90);
    const current = samples.length ? samples[samples.length - 1] : 0;
    const max = Math.max(Number(ceiling || 0), ...samples, 1);
    const width = 300, height = 76;
    const points = (samples.length ? samples : [0]).map((value, index, rows) => {
      const x = rows.length === 1 ? width : index * width / (rows.length - 1);
      const y = height - Math.min(height, Math.max(0, value / max * height));
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const area = `0,${height} ${points} ${width},${height}`;
    return `<article class="v3q-telemetry-card tone-${tone}">
      <div><span>${esc(label)}</span><strong>${esc(formatter(current))}</strong></div>
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true"><line x1="0" y1="${height*.5}" x2="${width}" y2="${height*.5}"/><polygon points="${area}"/><polyline points="${points}"/></svg>
      <small>${esc(subtitle || `${samples.length} live sample${samples.length===1?'':'s'}`)}</small>
    </article>`;
  }

  function serverTelemetry() {
    if (mode !== 'server') return '';
    const telemetry = quickState?.telemetry || {};
    const nestedRuntime = quickState?.runtime?.runtime || quickState?.runtime || {};
    const history = Array.isArray(telemetry.history) ? telemetry.history : (Array.isArray(nestedRuntime.metric_history) ? nestedRuntime.metric_history : []);
    const current = telemetry.metrics || nestedRuntime.metrics || history[history.length - 1] || {};
    const series = (key) => history.length ? history.map((row)=>Number(row?.[key] || 0)) : [Number(current?.[key] || 0)];
    const ping = Number(telemetry.ping_ms);
    const pingValues = [Number.isFinite(ping) ? ping : 0];
    const pingTone = !Number.isFinite(ping) ? 'muted' : ping <= 60 ? 'green' : ping <= 120 ? 'gold' : 'red';
    return `<section class="v3q-panel v3q-telemetry"><div class="v3q-panel-head"><div><b>Live Server Telemetry</b><small>Real host and RSDragonwilds process samples · refreshes while this window is open</small></div><span class="v3q-live-chip ${quickState?.active?'ok':'muted'}"><i></i>${quickState?.active?'LIVE':'IDLE'}</span></div>
      <div class="v3q-telemetry-grid">
        ${telemetryGraph('Server CPU',series('process_cpu_percent'),(v)=>`${v.toFixed(1)}%`,100,'gold','RSDragonwilds process load')}
        ${telemetryGraph('Server Memory',series('process_ram_bytes'),(v)=>formatBytes(v),0,'purple','RSDragonwilds working set')}
        ${telemetryGraph('System RAM',series('ram_percent'),(v)=>`${v.toFixed(1)}%`,100,'blue',current.ram_total_bytes ? `${formatBytes(current.ram_used_bytes)} of ${formatBytes(current.ram_total_bytes)}` : 'Host memory pressure')}
        ${telemetryGraph('Internet Down',series('net_down_bps'),(v)=>`${formatBytes(v)}/s`,0,'cyan','Live adapter traffic')}
        ${telemetryGraph('Internet Up',series('net_up_bps'),(v)=>`${formatBytes(v)}/s`,0,'orange','Live adapter traffic')}
        ${telemetryGraph('RSDragonwilds Ping',pingValues,(v)=>Number.isFinite(ping)?`${Math.round(v)} ms`:'—',Math.max(200,ping||0),pingTone,telemetry.ping_source || 'No measured latency yet')}
      </div>
    </section>`;
  }

  function quickConsole() {
    if (!consoleOpen) return '';
    const events = consoleState?.events || consoleState?.entries || consoleState?.history || [];
    const allRows = Array.isArray(events) ? events.slice(-220) : [];
    const rows = consoleFilter==='all' ? allRows : allRows.filter((row)=>String(row.source||'').toLowerCase()===consoleFilter);
    const filters=[['all','ALL'],['game','GAME'],['ue4ss','UE4SS'],['runeschema','RUNESCHEMA'],['chat','CHAT'],['server','SERVER'],['sync','SYNC']];
    return `<section class="v3q-panel v3q-console-panel">
      <div class="v3q-panel-head"><div><b>Runtime Console</b><small>One profile-scoped stream · source colors, filters, and guarded commands</small></div><div class="v3q-console-scroll"><button class="v3q-btn ghost" data-v3q-console-top>↑ Top</button><button class="v3q-btn ${quickFollowTail?'primary':'ghost'}" data-v3q-console-follow>${quickFollowTail?'● Live':'○ Paused'}</button><button class="v3q-btn ghost" data-v3q-console-bottom>↓ Bottom</button><button class="v3q-btn ghost" data-v3q-clear-console>Clear View</button></div></div>
      <nav class="v3q-console-filters" aria-label="Console source filters">${filters.map(([key,label])=>`<button class="v3q-btn ${consoleFilter===key?'primary':'ghost'}" data-v3q-console-filter="${key}" ${key!=='all'?`data-v3q-console-color-key="${key}" style="--console-source-color:${esc(quickConsoleColors[key]||defaultConsoleColors[key])}" title="Left-click to filter · right-click to choose ${label} color"`:''}>${label} <span>${key==='all'?allRows.length:allRows.filter((row)=>String(row.source||'').toLowerCase()===key).length}</span></button>`).join('')}</nav>
      <div class="v3q-console" data-v3q-console>${rows.length ? rows.map((row)=>{
        const ts = row.ts || row.time || row.created_at || '';
        const message = row.message || row.ack || row.command || row.line || JSON.stringify(row);
        const source=String(row.source||'system').toLowerCase().replace(/[^a-z0-9_-]/g,'-');
        return `<div class="source-${esc(source)}"><time>${esc(ts ? new Date(Number(ts)*1000 || ts).toLocaleTimeString?.() || ts : '')}</time><b>${esc(source.toUpperCase())}</b><span>${esc(message)}</span></div>`;
      }).join('') : '<div class="empty"><span>No console events for this filter yet.</span></div>'}</div>
      <form class="v3q-command" data-v3q-command-form><select name="target" aria-label="Command target"><option value="game" ${consoleTarget==='game'?'selected':''}>GAME / RSDWToolkit</option><option value="ue4ss" ${consoleTarget==='ue4ss'?'selected':''}>UE4SS / Unreal</option><option value="runeschema" ${consoleTarget==='runeschema'?'selected':''}>RuneSchema</option></select><input name="command" autocomplete="off" placeholder="Enter a command for the selected runtime…" ${quickState?.active?'':'disabled'}/><button class="v3q-btn primary" type="submit" ${quickState?.active?'':'disabled'}>Run</button></form>
    </section>`;
  }

  function launchPlan() {
    const steps=Array.isArray(quickState?.launch_sequence)?quickState.launch_sequence:[];
    if(!steps.length)return '';
    const launching=['play','host','start','restart','update_restart'].includes(activeOperation);
    if(mode === 'server' && !launching) return '';
    return `<section class="v3q-panel v3q-launch-plan ${launching?'running':''}"><div class="v3q-panel-head"><div><b>${esc(scopeLabel())} launch path</b><small>${launching?'Running these guarded stages in order…':'Quick uses the same authoritative profile pipeline as Full.'}</small></div></div><ol>${steps.map((step,index)=>`<li><i>${index+1}</i><span>${esc(step)}</span></li>`).join('')}</ol></section>`;
  }

  function broadcastBox() {
    if (!quickState?.controls?.broadcast_message) return '';
    return `<section class="v3q-panel">
      <div class="v3q-panel-head"><div><b>Broadcast Message</b><small>Uses the same World announcement backend as Full and WebGUI</small></div></div>
      <form class="v3q-broadcast" data-v3q-broadcast-form><input name="message" maxlength="1000" placeholder="Message players…"/><button class="v3q-btn" type="submit">Broadcast</button></form>
    </section>`;
  }

  async function loadQuickSpawner({force=false}={}) {
    if(mode!=='server'||quickSpawner.loading)return;
    quickSpawner={...quickSpawner,loading:true,error:''};renderQuick();
    try {
      const id=quickState?.profile_id||profileId;
      const [catalog,roster]=await Promise.all([
        api.invoke('server.spawner.catalog',{id,kind:'item',query:quickSpawner.query||'',limit:2000,refresh:force}),
        api.invoke('server.players.get',{id}),
      ]);
      const players=roster?.players?.players||roster?.players||[];
      quickSpawner={...quickSpawner,loaded:true,loading:false,items:Array.isArray(catalog?.items)?catalog.items:[],players:Array.isArray(players)?players.filter((row)=>row?.connected!==false):[],bridge:catalog?.bridge||{},runtime:catalog?.runtime||{},localPlayerAvailable:!!catalog?.local_player_available,error:''};
      if(!quickSpawner.playerId&&quickSpawner.players.length)quickSpawner.playerId=String(quickSpawner.players[0].id||quickSpawner.players[0].tracker_id||'');
    } catch(error) { quickSpawner={...quickSpawner,loaded:true,loading:false,error:error?.message||String(error)}; }
    renderQuick();
  }

  function quickDragonLink() {
    const status=quickState?.dragonlink||{};
    const config=status.config?.dragonlink||{};
    const component=status.components?.dragonlink||{};
    const proximity=status.components?.proximity_loot||{};
    const editable=mode==='server'&&status.editable!==false;
    const installed=!!component.installed;
    const current=component.current===true;
    const moduleCard=(key,title,dll,description,serverOnly=false)=>`<article class="v3q-dragonlink-module ${config[key]?'enabled':'disabled'}"><div><span>${esc(dll)}</span><strong>${esc(title)}</strong><small>${esc(description)}</small></div><span class="v3q-live-chip ${config[key]?'ok':'muted'}"><i></i>${config[key]?'ENABLED':'OFF'}</span>${serverOnly?'<em>SERVER ONLY</em>':''}</article>`;
    if(!editable){
      const offered=status.advertised_connect===true;
      return `<section class="v3q-panel v3q-dragonlink"><div class="v3q-panel-head"><div><b>DragonLink Connect</b><small>One-shot Direct Connect handoff for this World profile</small></div><span class="v3q-live-chip ${offered?'ok':'muted'}"><i></i>${offered?'HOST ENABLED':'MANUAL ENTRY'}</span></div><div class="v3q-dragonlink-client"><strong>${offered?'Automatic handoff is available':'This host requires manual Direct Connect entry'}</strong><p>${offered?'After verified Sync, DragonLink writes the saved address and password once when the game Direct Connect panel opens. It then remains idle.':'The verified connection receipt provides copy buttons for World name, address, and password.'}</p><code>${esc(status.connect_mode||'manual')}</code></div></section>`;
    }
    const locked=!!quickState?.active;
    const toggle=(key,title,detail)=>`<label class="v3q-toggle"><input type="checkbox" data-v3q-dragonlink-setting="${key}" ${config[key]?'checked':''} ${locked?'disabled':''}/><span><b>${esc(title)}</b><small>${esc(detail)}</small></span></label>`;
    const number=(key,title,value,min,max,step)=>`<label class="v3q-dragonlink-number"><span>${esc(title)}</span><input type="number" data-v3q-dragonlink-number="${key}" value="${esc(value)}" min="${min}" max="${max}" step="${step}"/></label>`;
    const captured=(consoleState?.events||consoleState?.entries||consoleState?.history||[]).filter((row)=>String(row.source||'').toLowerCase()==='chat').slice(-60).map((row)=>({at:row.ts||row.time,sender:row.sender||row.player_name||'Player',message:row.message||row.line||''}));
    const admin=Array.isArray(quickState?.chat)?quickState.chat:[];const chatRows=[...admin,...captured].sort((a,b)=>Number(a.at||0)-Number(b.at||0)).slice(-100);
    const chatFeed=chatRows.length?chatRows.map((row)=>`<article class="${row.automated?'automated':''}"><b>${esc(row.sender||'Server')}</b><span>${esc(row.message||'')}</span><time>${row.at?esc(new Date(Number(row.at)*1000).toLocaleTimeString()):''}</time></article>`).join(''):'<div class="empty"><span>No chat messages yet.</span></div>';
    const dragonLinkPanel=`<section class="v3q-panel v3q-dragonlink"><div class="v3q-panel-head"><div><b>DragonLink Application Bridge</b><small>Required Chat + Connect foundations${config.stacks_weights?' · optional Stacks & Weights enabled':''}</small></div><div class="v3q-item-status"><span class="v3q-live-chip ${installed?'ok':'bad'}"><i></i>${installed?(current?'INSTALLED · CURRENT':'INSTALLED · REPAIR AVAILABLE'):'NOT INSTALLED'}</span><button class="v3q-btn primary" data-v3q-dragonlink-save>Save &amp; Apply</button></div></div>${status.error?`<div class="v3q-error">${esc(status.error)}</div>`:''}<div class="v3q-dragonlink-modules">${config.stacks_weights?moduleCard('stacks_weights','Stacks & Weights','DragonLink-StacksWeights.dll','Combined stack authority and weight presentation module.'):''}${moduleCard('connect','Connect','DragonLink-Connect.dll','Writes Direct Connect fields once when the game panel opens.')}${moduleCard('chat','Chat','DragonLink-Chat.dll','Hydrates the application chat stream.',true)}</div><div class="v3q-dragonlink-settings">${toggle('enabled','Enable DragonLink','Master switch for the application bridge.')}${config.stacks_weights?toggle('push_stacks_weights_to_clients','Push Stacks & Weights to clients','Include the combined DLL in this World’s client Sync manifest.'):''}${toggle('connect','Direct Connect handoff','Offer one-time address/password autofill to verified clients.')}${toggle('chat','Chat bridge','Capture game chat into the DragonLink chat box.')}${toggle('capture_player_messages','Capture player messages','Forward player chat into the DragonLink chat box.')}${toggle('allow_application_announcements','Application announcements','Permit explicit automated announcements through the bridge.')}</div><section class="v3q-dragonlink-chat"><header><div><strong>Server Chat</strong><small>Player and admin chat stays here. Automated announcements also appear in Runtime Console.</small></div></header><div class="v3q-chat-feed">${chatFeed}</div><form data-v3q-chat-form><input name="message" maxlength="1000" placeholder="Type as Server Admin…"/><button class="v3q-btn primary">Send Chat</button></form><form data-v3q-broadcast-form><input name="message" maxlength="1000" placeholder="Create an automated server announcement…"/><button class="v3q-btn ghost">Announce</button></form></section><div class="v3q-dragonlink-foot"><code>${esc(component.path||'UE4SS/Mods/DragonLink')}</code><span>${locked?'Feature DLL toggles apply after stop.':'Changes apply on the next server start.'}</span></div></section>`;
    const proximityPanel=`<section class="v3q-panel v3q-dragonlink"><div class="v3q-panel-head"><div><b>Proximity Loot</b><small>Independent UE4SS mod · server retained by default · ProximityLoot.ini hot reload</small></div><span class="v3q-live-chip ${proximity.installed?'ok':'bad'}"><i></i>${proximity.installed?(proximity.current?'INSTALLED · CURRENT':'REPAIR AVAILABLE'):'NOT INSTALLED'}</span></div><div class="v3q-dragonlink-modules">${moduleCard('proximity_loot','Proximity Loot','DragonLink-ProximityLoot/dlls/main.dll','Standalone player-distance and loot-magnet control.')}</div><div class="v3q-dragonlink-settings">${toggle('proximity_loot','Enable Proximity Loot','Enable this standalone mod on the next server start.')}${toggle('push_proximity_loot_to_clients','Push Proximity Loot to clients','Include the standalone folder and config in this World’s client Sync manifest.')}</div><div class="v3q-proximity-settings"><strong>Live tuning</strong><small>Values hot-reload from ProximityLoot.ini without touching DragonLink.</small><div>${number('proximity_threshold','Crowded enter distance',config.proximity_threshold??1200,0,100000,.1)}${number('proximity_exit_threshold','Crowded exit distance',config.proximity_exit_threshold??1350,0,100000,.1)}${number('enhanced_magnet_range','Magnet range',config.enhanced_magnet_range??800,0,100000,.1)}${number('proximity_state_delay_seconds','State delay (seconds)',config.proximity_state_delay_seconds??10,0,120,.1)}${number('proximity_refresh_seconds','Refresh interval (seconds)',config.proximity_refresh_seconds??.35,.1,5,.05)}</div></div><div class="v3q-dragonlink-foot"><code>${esc(proximity.path||'UE4SS/Mods/DragonLink-ProximityLoot')}</code><span>${locked?'Distances hot-reload; enable and distribution apply after stop.':'Enable and client distribution apply on the next server start.'}</span></div></section>`;
    return `${dragonLinkPanel}${config.proximity_loot?proximityPanel:''}`;
  }

  async function loadQuickSaves() {
    if(quickSaves.loading)return;
    quickSaves={...quickSaves,loading:true,error:''};renderQuick();
    try {
      const data=await api.invoke('save.management.list',{profile_id:quickState?.profile_id||profileId,mode});
      quickSaves={loaded:true,loading:false,data,error:''};
    } catch(error) { quickSaves={...quickSaves,loaded:true,loading:false,data:null,error:error?.message||String(error)}; }
    renderQuick();
  }

  function quickSaveManager() {
    const data=quickSaves.data||{};
    const worlds=Array.isArray(data.world_backups)?data.world_backups:[];
    const playerGroups=Array.isArray(data.player_backup_groups)?data.player_backup_groups:[];
    const when=(value)=>value?new Date(Number(value)*1000).toLocaleString():'Unknown date';
    return `<section class="v3q-panel v3q-save-manager">
      <div class="v3q-panel-head"><div><b>World &amp; Player Save Manager</b><small>Backup-first rollback · ${esc(data.runtime_guard||'safe stopped-state writes')}</small></div><div class="v3q-item-status"><span class="v3q-live-chip warn"><i></i>VERIFIED SWAPS</span><button class="v3q-btn ghost" data-v3q-saves-refresh ${quickSaves.loading?'disabled':''}>Refresh</button><button class="v3q-btn ghost" data-v3q-world-import>Import / Swap ZIP</button><button class="v3q-btn primary" data-v3q-world-backup ${quickSaves.loading?'disabled':''}>Create World Backup</button></div></div>
      ${quickSaves.error?`<div class="v3q-error">${esc(quickSaves.error)}</div>`:''}
      ${quickSaves.loading&&!quickSaves.loaded?'<div class="empty"><span>Reading managed save revisions…</span></div>':`<div class="v3q-save-columns">
        <div><h3>World revisions</h3><p>Right-click a revision to rename, delete, or send a verified copy to the Desktop. Restore remains backup-first.</p><div class="v3q-save-list">${worlds.length?worlds.map((row)=>`<article data-v3q-save-entry="world" data-v3q-save-id="${esc(row.id||row.name||'')}" title="Right-click for save actions"><div><strong>${esc(row.name||row.id)}</strong><small>${esc(when(row.mtime))} · ${esc(formatBytes(row.size||0))}</small></div><button class="v3q-btn danger" data-v3q-world-restore="${esc(row.id||row.name||'')}">${mode==='server'&&quickState?.active?'Hot Swap':'Restore'}</button></article>`).join(''):'<div class="empty"><span>No World backups yet.</span></div>'}</div></div>
        <div><h3>${mode==='server'?'Retained players':'Player saves'}</h3><p>Select a Player Name to see every retained backup. Each revision has rollback, Desktop export, and—on servers—next-connect delivery.</p><div class="v3q-save-list v3q-player-list">${playerGroups.length?playerGroups.map((group)=>{const revisions=Array.isArray(group.revisions)?group.revisions:[];const latest=revisions[0]||{};return `<button class="v3q-player-row" data-v3q-player-group="${esc(group.id||'')}" title="Open ${esc(group.name||'Player')} backup history"><span class="v3q-player-avatar">${esc(String(group.name||'P').slice(0,1).toUpperCase())}</span><span><strong>${esc(group.name||'Player')}</strong><small>${revisions.length} saved revision${revisions.length===1?'':'s'} · latest ${esc(when(latest.mtime))}</small></span><b>Open ›</b></button>`;}).join(''):'<div class="empty"><span>No player save revisions retained yet.</span></div>'}</div></div>
      </div>`}
    </section>`;
  }

  function openQuickPlayerHistory(groupId) {
    const groups=Array.isArray(quickSaves.data?.player_backup_groups)?quickSaves.data.player_backup_groups:[];
    const group=groups.find((row)=>String(row.id||'')===String(groupId||''));
    if(!group)return;
    const revisions=Array.isArray(group.revisions)?group.revisions:[];
    document.querySelector('[data-v3q-player-history]')?.remove();
    const overlay=document.createElement('div');overlay.className='v3q-save-overlay';overlay.dataset.v3qPlayerHistory='1';
    overlay.innerHTML=`<section class="v3q-save-dialog"><header><div><small>PLAYER SAVE HISTORY</small><h2>${esc(group.name||'Player')}</h2><p>${revisions.length} profile-bound backup${revisions.length===1?'':'s'}</p></div><button class="v3q-btn ghost" data-v3q-history-close>Close</button></header><div class="v3q-save-list">${revisions.map((row)=>`<article data-v3q-save-entry="player" data-v3q-save-id="${esc(row.id||row.name||'')}" title="Right-click for save actions"><div><strong>${esc(row.name||row.id)}</strong><small>${esc(new Date(Number(row.mtime||0)*1000).toLocaleString())} · ${esc(formatBytes(row.size||0))}</small></div><div class="v3q-item-status"><button class="v3q-btn ghost" data-v3q-save-desktop="player:${esc(row.id||row.name||'')}">Desktop</button>${mode==='server'?`<button class="v3q-btn primary" data-v3q-player-queue="${esc(row.id||row.name||'')}">Send on Next Connect</button>`:`<button class="v3q-btn danger" data-v3q-player-restore="${esc(row.id||row.name||'')}" data-v3q-player-target="${esc(row.target_name||'')}" data-v3q-player-source="${esc(row.source||'')}">Roll Back</button>`}</div></article>`).join('')||'<div class="empty"><span>No backups retained.</span></div>'}</div><footer>Right-click any revision to rename, delete, or send it to the Desktop.</footer></section>`;
    document.body.appendChild(overlay);bindSaveActions(overlay);overlay.querySelector('[data-v3q-history-close]')?.addEventListener('click',()=>overlay.remove());overlay.addEventListener('click',(event)=>{if(event.target===overlay)overlay.remove();});
  }

  function quickItemSpawner() {
    const items=Array.isArray(quickSpawner.items)?quickSpawner.items:[];
    const pageSize=30;
    const pageCount=Math.max(1,Math.ceil(items.length/pageSize));
    const page=Math.max(0,Math.min(Number(quickSpawner.page||0),pageCount-1));
    const visibleItems=items.slice(page*pageSize,(page+1)*pageSize);
    const pageIndexes=[...new Set([0,1,page-2,page-1,page,page+1,page+2,pageCount-2,pageCount-1])].filter((index)=>index>=0&&index<pageCount).sort((a,b)=>a-b);
    const players=Array.isArray(quickSpawner.players)?quickSpawner.players:[];
    const bridgeReady=!!quickSpawner.bridge?.available;
    const runtimeReady=!!quickSpawner.runtime?.running&&quickSpawner.runtime?.active!==false;
    const canGive=!!quickSpawner.selectedPath&&!!quickSpawner.playerId&&bridgeReady&&runtimeReady&&quickState?.active;
    const selected=items.find((item)=>String(item.runtime_path||'')===String(quickSpawner.selectedPath||''))||null;
    const selectedIcon=selected?localFileUrl(selected.icon_path||selected.icon_url||''):'';
    return `<section class="v3q-panel v3q-item-service">
      <div class="v3q-panel-head"><div><b>Summon Items for Players</b><small>Uses the bounded RSDW item service; no arbitrary command or full editor is loaded</small></div><div class="v3q-item-status"><span class="v3q-live-chip ${runtimeReady?'ok':'muted'}"><i></i>${runtimeReady?'WORLD LIVE':'WORLD STOPPED'}</span><span class="v3q-live-chip ${bridgeReady?'ok':'bad'}"><i></i>${bridgeReady?'BRIDGE READY':'BRIDGE OFFLINE'}</span></div></div>
      <form class="v3q-item-search" data-v3q-item-search><input name="query" value="${esc(quickSpawner.query)}" placeholder="Search item name, ID, category, or mod…"/><button class="v3q-btn primary" type="submit" ${quickSpawner.loading?'disabled':''}>${quickSpawner.loading?'Loading…':'Search'}</button><button class="v3q-btn ghost" type="button" data-v3q-items-refresh ${quickSpawner.loading?'disabled':''}>Refresh Catalog</button></form>
      ${quickSpawner.error?`<div class="v3q-error">${esc(quickSpawner.error)}</div>`:''}
      <div class="v3q-item-layout"><div><div class="v3q-item-grid">${quickSpawner.loading&&!quickSpawner.loaded?'<div class="empty"><span>Loading the server item repository…</span></div>':items.length?visibleItems.map((item)=>{const path=String(item.runtime_path||'');const icon=localFileUrl(item.icon_path||item.icon_url||'');return `<button class="v3q-item ${quickSpawner.selectedPath===path?'selected':''}" data-v3q-item-path="${esc(path)}" data-v3q-item-name="${esc(item.display_name||item.name||'Item')}" title="${esc(path)}">${icon?`<img src="${esc(icon)}" alt="" loading="lazy"/>`:'<span>◇</span>'}<strong>${esc(item.display_name||item.name||'Unknown Item')}</strong><small>${esc(item.category||item.mod_name||'Item')}</small></button>`;}).join(''):'<div class="empty"><span>No matching items were found.</span></div>'}</div>${items.length?`<nav class="v3q-item-pagination" aria-label="Item catalog pages"><button class="v3q-btn ghost" data-v3q-item-page="${page-1}" ${page<=0?'disabled':''}>← Previous</button><div>${pageIndexes.map((index)=>`<button class="v3q-btn ${index===page?'primary':'ghost'}" data-v3q-item-page="${index}">${index+1}</button>`).join('')}</div><button class="v3q-btn ghost" data-v3q-item-page="${page+1}" ${page>=pageCount-1?'disabled':''}>Next →</button><span>${visibleItems.length} of ${items.length} · page ${page+1} / ${pageCount}</span></nav>`:''}</div>
        <aside class="v3q-item-give"><small>SELECTED ITEM</small>${selectedIcon?`<img class="v3q-selected-item-icon" src="${esc(selectedIcon)}" alt=""/>`:''}<strong data-v3q-selected-item>${esc(selected?.display_name||selected?.name||'Choose an item')}</strong>${selected?`<p class="v3q-item-description">${esc(selected.description||'No item description is published in the current RSDW catalog.')}</p><dl class="v3q-item-facts"><div><dt>Category</dt><dd>${esc(selected.category||'Item')}</dd></div><div><dt>Internal name</dt><dd>${esc(selected.internal_name||selected.item_name||'—')}</dd></div><div><dt>Persistence ID</dt><dd>${esc(selected.persistence_id||selected.item_data||'—')}</dd></div><div><dt>Maximum stack</dt><dd>${esc(selected.max_stack||1)}</dd></div><div><dt>Equipment</dt><dd>${esc(selected.equipment||'Not equipped')}</dd></div><div><dt>Source / mod</dt><dd>${esc(selected.source_mod||selected.source||'RSDW baseline')}</dd></div></dl>`:''}<code>${esc(quickSpawner.selectedPath||'No item selected')}</code><label><span>Player</span><select data-v3q-item-player ${players.length?'':'disabled'}>${players.map((player)=>{const id=String(player.id||player.tracker_id||'');return `<option value="${esc(id)}" ${quickSpawner.playerId===id?'selected':''}>${esc(player.name||player.player_name||'Player')}</option>`;}).join('')}</select></label><label><span>Quantity</span><input data-v3q-item-count type="number" min="1" max="9999" value="${Math.max(1,Number(quickSpawner.count||1))}"/></label><button class="v3q-btn primary big" data-v3q-give-item ${canGive?'':'disabled'}>Give Item</button><p>${players.length?`${players.length} connected player${players.length===1?'':'s'} available.`:'No connected players are currently available.'}</p></aside></div>
    </section>`;
  }

  function renderQuick() {
    if (!quickEnabled) return;
    const root = document.getElementById('app');
    if (!root) return;
    document.body.classList.add('v3-quick-body');
    const runtimeState = quickState?.runtime?.runtime?.state || quickState?.runtime?.state || (quickState?.active ? 'Running' : 'Stopped');
    const networkState = destinationRows();
    const publicEnabled = !!quickState?.network?.public_directory_enabled;
    const players = Array.isArray(quickState?.players) ? quickState.players : [];
    const error = quickState?.error;
    const profileIcon=dataImage(quickState?.presentation?.icon_b64,'assets/application-icon.webp');
    const profileBanner=dataImage(quickState?.presentation?.banner_b64,'assets/singleplayer-banner.webp');
    const markup = `<main class="v3q-shell" data-v3-quick-root>
      <header class="v3q-header">
        <img class="v3q-profile-banner" src="${esc(profileBanner)}" alt="" />
        <div class="v3q-brand"><span class="v3q-mark"><img src="${esc(profileIcon)}" alt="" /></span><div><small>DRAGONWILDS SYNC QUICK · ${esc(scopeLabel().toUpperCase())}</small><h1>${esc(quickState?.world_name || 'Loading World…')}</h1><span class="v3q-profile-caption">${esc(roleLabel)} control center · ${esc(quickState?.profile_kind || 'Loading profile')}</span></div></div>
        <span class="v3q-live-chip ${statusClass(runtimeState)}"><i></i>${esc(runtimeState)}</span>
        <div class="v3q-header-actions"><label class="v3q-autostart"><input type="checkbox" data-v3q-autostart ${autoStart?'checked':''}/><span><b>Start + Sync on open</b><small>${autoStart?'Automatic':'Manual button'}</small></span></label><button class="v3q-btn ghost" data-v3q-refresh ${busy?'disabled':''}>Refresh</button><button class="v3q-btn" data-v3q-full>Open Full Dragonwilds Sync</button></div>
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
      <section class="v3q-toolbar" aria-label="Quick actions">
        <div class="v3q-primary-actions">
          ${quickState?.controls?.play ? `<button class="v3q-btn primary big" data-v3q-action="${verifiedPlayReady?'play':'start'}" ${busy||quickState?.active?'disabled':''}><span>${verifiedPlayReady?'▶':'◆'}</span>${quickState?.active?'Dragonwilds Running':verifiedPlayReady?'Play Dragonwilds':'Sync & Verify'}</button>`:''}
          ${quickState?.controls?.host ? `<button class="v3q-btn primary big" data-v3q-action="start" ${busy||quickState?.active?'disabled':''}><span>▶</span>${quickState?.active?'Co-Op Active':'Start Co-Op'}</button>`:''}
          ${quickState?.controls?.start ? `<button class="v3q-btn primary big" data-v3q-action="start" ${busy||quickState?.active?'disabled':''}><span>▶</span>${quickState?.active?'Server Running':'Start Server'}</button>`:''}
          ${quickState?.controls?.stop ? `<button class="v3q-btn danger" data-v3q-action="stop" ${busy||!quickState?.active?'disabled':''}>■ Stop</button>`:''}
          ${quickState?.controls?.restart ? `<button class="v3q-btn" data-v3q-action="restart" ${busy||!quickState?.active?'disabled':''}>↻ Restart</button>`:''}
          ${quickState?.controls?.update_restart ? `<button class="v3q-btn" data-v3q-action="update_restart" ${busy?'disabled':''}>⇧ Update & Restart</button>`:''}
        </div>
        <div class="v3q-secondary-actions"><button class="v3q-btn ghost" data-v3q-mods>View Mods</button>${quickState?.controls?.console?`<button class="v3q-btn ghost" data-v3q-console-toggle>${consoleOpen?'Hide Console':'Open Console'}</button>`:''}</div>
      </section>
      <nav class="v3q-section-tabs" aria-label="Quick Launch tools"><button class="v3q-btn ${quickSection==='overview'?'primary':'ghost'}" data-v3q-section="overview">Overview &amp; Console</button><button class="v3q-btn ${quickSection==='dragonlink'?'primary':'ghost'}" data-v3q-section="dragonlink">DragonLink</button>${mode==='server'?`<button class="v3q-btn ${quickSection==='items'?'primary':'ghost'}" data-v3q-section="items">Summon Items</button>`:''}<button class="v3q-btn ${quickSection==='saves'?'primary':'ghost'}" data-v3q-section="saves">Save Manager</button></nav>
      ${quickSection==='dragonlink'?quickDragonLink():quickSection==='saves'?quickSaveManager():mode==='server'&&quickSection==='items'?quickItemSpawner():`<div class="v3q-quick-overview"><div class="v3q-columns">
        <section class="v3q-panel">
          <div class="v3q-panel-head"><div><b>World & Network</b><small>Presence and World publication are independent</small></div></div>
          <div class="v3q-world-meta"><span>Profile ID</span><code>${esc(quickState?.profile_id || profileId)}</code></div>
          <div class="v3q-world-meta"><span>Profile</span><b>${esc(quickState?.profile_kind || '—')}</b></div>
          ${quickState?.profile_kind !== 'linked' ? `<label class="v3q-toggle"><input type="checkbox" data-v3q-public ${publicEnabled?'checked':''}/><span><b>Broadcast this World publicly</b><small>Official World publication. Does not control anonymous application presence.</small></span></label>`:''}
          <div class="v3q-destinations">${networkState.length ? networkState.map((row)=>`<div><span class="dot ${statusClass(row.state)}"></span><b>${esc(row.name)}</b><em>${esc(row.state)}</em><small>${esc(row.detail)}</small></div>`).join('') : '<small>No public destinations configured.</small>'}</div>
        </section>
        ${mode === 'server' ? `<section class="v3q-panel"><div class="v3q-panel-head"><div><b>Players</b><small>${players.length} connected / observed</small></div></div><div class="v3q-players">${players.length ? players.map((p)=>`<span>${esc(p.name || p.player_name || p.id || 'Player')}</span>`).join('') : '<small>No players reported.</small>'}</div></section>` : `<section class="v3q-panel"><div class="v3q-panel-head"><div><b>${mode==='coop'?'Co-Op Host':scopeLabel()}</b><small>Same profile/runtime materialization used by Full</small></div></div><p class="v3q-copy">${esc(quickState?.description || (mode==='coop'?'Launch the local profile, then Quick can enable its Co-Op Sync host.':quickState?.profile_kind==='linked'?'Match files, transfer changes, verify parity, prepare DragonLink-Connect, then play.':'Materialize this local profile and launch it without contacting a remote Sync host.'))}</p></section>`}
      </div>
      ${launchPlan()}
      ${serverTelemetry()}
      ${broadcastBox()}
      ${quickConsole()}</div>`}
      <footer class="v3q-footer"><span>${busy?'Working…':'Ready'}</span><span>Open Full promotes this same launcher process; it does not duplicate the backend or runtime.</span></footer>
    </main>`;
    if (root.__dwsQuickMarkup === markup) return;
    const priorScroll=window.scrollY;
    const priorItemScroll=root.querySelector('.v3q-item-grid')?.scrollTop||0;
    const priorConsoleScroll=root.querySelector('[data-v3q-console]')?.scrollTop??quickConsoleScrollTop;
    const focused=document.activeElement;
    const focusedName=focused?.getAttribute?.('name')||'';
    const focusedValue=focusedName&&'value' in focused?focused.value:null;
    root.__dwsQuickMarkup = markup;
    root.innerHTML = markup;
    root.querySelector('.v3q-mark img')?.addEventListener('error',(event)=>{event.currentTarget.src='assets/application-icon.webp';});
    root.querySelector('.v3q-profile-banner')?.addEventListener('error',(event)=>{event.currentTarget.src='assets/singleplayer-banner.webp';});
    bindQuick();
    requestAnimationFrame(()=>{window.scrollTo({top:priorScroll,left:0,behavior:'instant'});const grid=root.querySelector('.v3q-item-grid');if(grid)grid.scrollTop=priorItemScroll;const consoleNode=root.querySelector('[data-v3q-console]');if(consoleNode){if(quickFollowTail)consoleNode.scrollTop=consoleNode.scrollHeight;else consoleNode.scrollTop=priorConsoleScroll;}if(focusedName){const next=root.querySelector(`[name="${CSS.escape(focusedName)}"]`);if(next&&focusedValue!==null){next.value=focusedValue;next.focus({preventScroll:true});}}});
  }

  async function action(name) {
    if (busy) return;
    activeOperation=name;renderQuick();
    try {
      if (name === 'start') {
        const prepared=await invoke('quick.start', { profile_id: quickState?.profile_id || profileId, mode });
        verifiedPlayReady=!!prepared?.awaiting_play;
      }
      else if (name === 'play') { await invoke('quick.play', { profile_id: quickState?.profile_id || profileId, mode }); verifiedPlayReady=false; }
      else if (name === 'stop') await invoke('quick.stop', { profile_id: quickState?.profile_id || profileId, mode });
      else if (name === 'restart') await invoke('quick.restart', { profile_id: quickState?.profile_id || profileId, mode });
      else if (name === 'update_restart') await invoke('quick.update_restart', { profile_id: quickState?.profile_id || profileId, mode });
      toast(`${roleLabel} ${name.replace('_',' ')} completed`, 'success');
    } catch (error) { toast(error?.message || String(error), 'error'); }
    activeOperation='';
    await refresh();
  }

  function bindSaveActions(scope) {
    const runEntryAction=async(kind,entryId,action)=>{
      let newName='';
      if(action==='rename'){newName=prompt('Rename this save revision:',String(entryId||'').split('/').pop())||'';if(!newName)return;}
      if(action==='delete'&&!confirm(`Delete ${String(entryId||'').split('/').pop()}?\n\nThis removes only this retained revision.`))return;
      try{const result=await invoke('save.management.entry.action',{profile_id:quickState?.profile_id||profileId,mode,kind,entry_id:entryId,action,new_name:newName});toast(action==='desktop'?`Saved to Desktop · ${result.path}`:`Save revision ${action}d`,'success');quickSaves.loaded=false;await loadQuickSaves();if(scope.closest?.('[data-v3q-player-history]'))scope.remove();}
      catch(error){toast(error?.message||String(error),'error');}
    };
    scope.querySelectorAll('[data-v3q-save-entry]').forEach((row)=>row.addEventListener('contextmenu',(event)=>{event.preventDefault();document.querySelector('[data-v3q-save-menu]')?.remove();const menu=document.createElement('div');menu.className='v3q-save-menu';menu.dataset.v3qSaveMenu='1';menu.style.left=`${event.clientX}px`;menu.style.top=`${event.clientY}px`;menu.innerHTML='<button data-action="rename">Rename</button><button data-action="desktop">Send to Desktop</button><button class="danger" data-action="delete">Delete</button>';document.body.appendChild(menu);const close=()=>menu.remove();menu.querySelectorAll('[data-action]').forEach((button)=>button.addEventListener('click',()=>{const action=button.dataset.action;close();void runEntryAction(row.dataset.v3qSaveEntry||'',row.dataset.v3qSaveId||'',action);}));setTimeout(()=>document.addEventListener('pointerdown',close,{once:true}),0);}));
    scope.querySelectorAll('[data-v3q-save-desktop]').forEach((button)=>button.addEventListener('click',()=>{const [kind,...parts]=String(button.dataset.v3qSaveDesktop||'').split(':');void runEntryAction(kind,parts.join(':'),'desktop');}));
    scope.querySelectorAll('[data-v3q-player-queue]').forEach((button)=>button.addEventListener('click',async()=>{if(!confirm('Queue this backup for the authenticated player?\n\nTheir launcher will receive and store it in the World profile on the next connection.'))return;try{await invoke('save.management.player.queue',{profile_id:quickState?.profile_id||profileId,mode,revision_id:button.dataset.v3qPlayerQueue||''});toast('Player delivery queued','The selected backup is now the next-connect delivery.','success');}catch(error){toast(error?.message||String(error),'error');}}));
    scope.querySelectorAll('[data-v3q-player-restore]').forEach((button)=>button.addEventListener('click',async()=>{const revision=button.dataset.v3qPlayerRestore;if(!confirm(`Roll back this player save to ${revision}?\n\nThe current revision remains recoverable.`))return;try{await invoke('save.management.player.restore',{profile_id:quickState?.profile_id||profileId,mode,revision_id:revision,target_name:button.dataset.v3qPlayerTarget||'',source:button.dataset.v3qPlayerSource||''});toast(mode==='server'?'Player recovery revision selected':'Player save restored','success');quickSaves.loaded=false;await loadQuickSaves();}catch(error){toast(error?.message||String(error),'error');}}));
  }

  function bindQuick() {
    const root = document.querySelector('[data-v3-quick-root]');
    if (!root) return;
    root.querySelector('[data-v3q-refresh]')?.addEventListener('click', ()=>refresh());
    root.querySelector('[data-v3q-autostart]')?.addEventListener('change',(event)=>{autoStart=!!event.currentTarget.checked;localStorage.setItem(autoStartStorageKey,autoStart?'1':'0');event.currentTarget.closest('label')?.querySelector('small')?.replaceChildren(autoStart?'Automatic':'Manual button');if(autoStart&&!quickState?.active){autoStartConsumed=false;void refresh();}});
    root.querySelector('[data-v3q-full]')?.addEventListener('click', ()=>api.openMainWindow?.());
    root.querySelector('[data-v3q-mods]')?.addEventListener('click', async()=>{
      const target = String(quickState?.mods?.path || '');
      if (target && api.openPath) {
        try { await api.openPath(target); return; } catch (_) {}
      }
      api.openMainWindow?.();
    });
    root.querySelector('[data-v3q-console-toggle]')?.addEventListener('click',async()=>{consoleOpen=!consoleOpen;if(consoleOpen)await refresh({consoleToo:true});else renderQuick();});
    root.querySelectorAll('[data-v3q-section]').forEach((button)=>button.addEventListener('click',()=>{quickSection=button.dataset.v3qSection||'overview';renderQuick();if(quickSection==='items'&&!quickSpawner.loaded)void loadQuickSpawner();if(quickSection==='saves'&&!quickSaves.loaded)void loadQuickSaves();}));
    root.querySelectorAll('[data-v3q-player-group]').forEach((button)=>button.addEventListener('click',()=>openQuickPlayerHistory(button.dataset.v3qPlayerGroup||'')));
    bindSaveActions(root);
    root.querySelector('[data-v3q-saves-refresh]')?.addEventListener('click',()=>void loadQuickSaves());
    root.querySelector('[data-v3q-world-backup]')?.addEventListener('click',async()=>{if(!confirm('Create a verified World save recovery point now? Running servers briefly stop and restart so the save cannot be captured mid-write.'))return;try{await invoke('save.management.world.backup',{profile_id:quickState?.profile_id||profileId,mode});toast('World backup created','success');quickSaves.loaded=false;await loadQuickSaves();}catch(error){toast(error?.message||String(error),'error');}});
    root.querySelector('[data-v3q-world-import]')?.addEventListener('click',async()=>{const path=await api.pickFile?.('zip');if(!path||!confirm('Import and swap to this World save ZIP?\n\nThe current World is backed up first. A running server will stop and restart.'))return;try{await invoke('save.management.world.import',{profile_id:quickState?.profile_id||profileId,mode,path});toast('World save imported and swapped','success');quickSaves.loaded=false;await loadQuickSaves();}catch(error){toast(error?.message||String(error),'error');}});
    root.querySelectorAll('[data-v3q-world-restore]').forEach((button)=>button.addEventListener('click',async()=>{const revision=button.dataset.v3qWorldRestore;if(!confirm(`Restore ${revision}?\n\nThe current save is backed up first. A running server will stop, swap the save, and restart.`))return;try{await invoke('save.management.world.restore',{profile_id:quickState?.profile_id||profileId,mode,revision_id:revision});toast('World save restored','success');quickSaves.loaded=false;await loadQuickSaves();}catch(error){toast(error?.message||String(error),'error');}}));
    root.querySelector('[data-v3q-item-search]')?.addEventListener('submit',(event)=>{event.preventDefault();quickSpawner.query=String(event.currentTarget.elements.query?.value||'').trim();quickSpawner.page=0;void loadQuickSpawner();});
    root.querySelector('[data-v3q-items-refresh]')?.addEventListener('click',()=>{quickSpawner.page=0;void loadQuickSpawner({force:true});});
    root.querySelectorAll('[data-v3q-item-page]').forEach((button)=>button.addEventListener('click',()=>{quickSpawner.page=Math.max(0,Number(button.dataset.v3qItemPage||0));renderQuick();document.querySelector('.v3q-item-service')?.scrollIntoView({block:'start'});}));
    root.querySelectorAll('[data-v3q-item-path]').forEach((button)=>button.addEventListener('click',()=>{quickSpawner.selectedPath=button.dataset.v3qItemPath||'';quickSpawner.selectedName=button.dataset.v3qItemName||'Item';renderQuick();}));
    root.querySelector('[data-v3q-item-player]')?.addEventListener('change',(event)=>{quickSpawner.playerId=event.currentTarget.value||'';});
    root.querySelector('[data-v3q-item-count]')?.addEventListener('change',(event)=>{quickSpawner.count=Math.max(1,Math.min(9999,Number(event.currentTarget.value||1)));event.currentTarget.value=String(quickSpawner.count);});
    root.querySelector('[data-v3q-give-item]')?.addEventListener('click',async()=>{const button=root.querySelector('[data-v3q-give-item]');if(!quickSpawner.selectedPath||!quickSpawner.playerId||button?.disabled)return;button.disabled=true;try{const result=await api.invoke('server.spawner.spawn',{id:quickState?.profile_id||profileId,kind:'item',runtime_path:quickSpawner.selectedPath,count:Math.max(1,Math.min(9999,Number(quickSpawner.count||1))),target:{kind:'player',player_id:quickSpawner.playerId},confirmed:true});toast(result?.ack||`${quickSpawner.selectedName} given to player`,'success');}catch(error){toast(error?.message||String(error),'error');}finally{button.disabled=false;}});
    root.querySelector('[data-v3q-dragonlink-save]')?.addEventListener('click',async()=>{const config={};root.querySelectorAll('[data-v3q-dragonlink-setting]').forEach((input)=>{config[input.dataset.v3qDragonlinkSetting]=!!input.checked;});root.querySelectorAll('[data-v3q-dragonlink-number]').forEach((input)=>{config[input.dataset.v3qDragonlinkNumber]=Number(input.value);});try{await invoke('quick.dragonlink.update',{profile_id:quickState?.profile_id||profileId,mode,config:{dragonlink:config}});toast('DragonLink settings saved',quickState?.active?'Proximity Loot tuning hot-reloaded.':'Native modules will use this profile configuration on the next start.','success');await refresh({consoleToo:false});}catch(error){toast(error?.message||String(error),'error');}});
    root.querySelector('[data-v3q-chat-form]')?.addEventListener('submit',async(event)=>{event.preventDefault();const input=event.currentTarget.elements.message;const message=String(input?.value||'').trim();if(!message)return;try{await invoke('quick.chat.send',{profile_id:quickState?.profile_id||profileId,mode,message});input.value='';toast('Admin chat sent','Delivered through the active Sync profile without adding a console entry.','success');await refresh({consoleToo:true});}catch(error){toast(error?.message||String(error),'error');}});
    root.querySelectorAll('[data-v3q-console-filter]').forEach((button)=>button.addEventListener('click',()=>{consoleFilter=button.dataset.v3qConsoleFilter||'all';renderQuick();}));
    root.querySelectorAll('[data-v3q-console-color-key]').forEach((button)=>button.addEventListener('contextmenu',(event)=>{event.preventDefault();chooseConsoleColor(button.dataset.v3qConsoleColorKey,String(button.textContent||'source').replace(/\d+\s*$/,'').trim());}));
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
    root.querySelector('[data-v3q-console-top]')?.addEventListener('click',()=>{quickFollowTail=false;const node=root.querySelector('[data-v3q-console]');if(node)node.scrollTop=0;renderQuick();});
    root.querySelector('[data-v3q-console-bottom]')?.addEventListener('click',()=>{quickFollowTail=true;renderQuick();});
    root.querySelector('[data-v3q-console-follow]')?.addEventListener('click',()=>{quickFollowTail=!quickFollowTail;renderQuick();});
    root.querySelector('[data-v3q-broadcast-form]')?.addEventListener('submit', async(event)=>{
      event.preventDefault(); const input=event.currentTarget.elements.message; const message=String(input?.value||'').trim(); if(!message)return;
      try { await invoke('quick.broadcast',{profile_id:quickState?.profile_id||profileId,mode,message}); input.value=''; toast('Broadcast sent','success'); }
      catch(error){toast(error?.message||String(error),'error');}
      await refresh({consoleToo:false});
    });
    const consoleNode=root.querySelector('[data-v3q-console]'); if(consoleNode){if(quickFollowTail)consoleNode.scrollTop=consoleNode.scrollHeight;else consoleNode.scrollTop=quickConsoleScrollTop;consoleNode.addEventListener('scroll',()=>{quickConsoleScrollTop=consoleNode.scrollTop;if(quickFollowTail&&consoleNode.scrollHeight-consoleNode.scrollTop-consoleNode.clientHeight>90)quickFollowTail=false;},{passive:true});}
  }

  // ---------- Full application additive controls ----------
  let picker = null;
  function closePicker(){ picker?.remove(); picker=null; }
  function openShortcutPicker({id,name,server}) {
    closePicker();
    const modes = server ? ['server'] : ['player','coop'];
    picker=document.createElement('div'); picker.className='v3q-picker-backdrop';
    picker.innerHTML=`<div class="v3q-picker"><button class="v3q-picker-x" aria-label="Close">×</button><small>CREATE QUICK SHORTCUT</small><h3>${esc(name||'World')}</h3><p>Shortcuts use the stable profile ID. Renaming the World will not break them. Headless Server targets the standalone Headless EXE beside this application.</p>${modes.map((m)=>`<div class="v3q-picker-role"><b>${m==='server'?'Server':m==='coop'?'Co-Op':'Player'}</b><button data-v3q-shortcut="${m}:open">Open Quick</button><button data-v3q-shortcut="${m}:start">Open Quick + Start</button>${m==='server'?`<button data-v3q-shortcut="${m}:headless">Headless Start</button>`:''}</div>`).join('')}</div>`;
    document.body.appendChild(picker); picker.querySelector('.v3q-picker-x')?.addEventListener('click',closePicker); picker.addEventListener('click',(e)=>{if(e.target===picker)closePicker();});
    picker.querySelectorAll('[data-v3q-shortcut]').forEach((button)=>button.addEventListener('click',async()=>{
      const [selected,behavior]=button.dataset.v3qShortcut.split(':');
      try {
        const createShortcut=window.dragonwildsV3?.createQuickShortcut;
        if(typeof createShortcut!=='function')throw new Error('The desktop shortcut bridge is unavailable. Restart Dragonwilds Sync and try again.');
        button.disabled=true;
        button.textContent='Creating…';
        const result=await createShortcut({profileId:id,name,mode:selected,runtime:behavior==='headless'?'headless':'gui',autoStart:behavior==='start'});
        if(!result?.ok||!result?.path)throw new Error('Windows did not confirm the desktop shortcut path.');
        toast(`Quick shortcut created · ${result.path}`,'success');
        closePicker();
      }
      catch(error){toast(error?.message||String(error),'error');}
      finally{if(button.isConnected){button.disabled=false;button.textContent=behavior==='open'?'Open Quick':behavior==='start'?'Open Quick + Start':'Headless Start';}}
    }));
  }

  function enhanceShortcuts() {
    if (quickEnabled) return;
    document.querySelectorAll('[data-server-manage],[data-private-manage]').forEach((manage)=>{
      const parent=manage.parentElement; if(!parent || parent.querySelector('[data-v3q-create-shortcut]'))return;
      const server=manage.hasAttribute('data-server-manage'); const id=manage.getAttribute(server?'data-server-manage':'data-private-manage')||'';
      const card=manage.closest('[data-world-id],article'); const name=card?.querySelector('h3')?.textContent?.trim()||'Dragonwilds World';
      const button=document.createElement('button'); button.className='btn ghost compact-btn'; button.dataset.v3qCreateShortcut=id; button.textContent='Send to Desktop';
      button.addEventListener('click',async(event)=>{event.preventDefault();event.stopPropagation();try{const send=window.__DWSYNC_SEND_PROFILE_TO_DESKTOP__;if(typeof send!=='function')throw new Error('Desktop shortcut picker is not ready.');const image=card?.querySelector('.world-icon img,img.world-icon');const source=String(image?.currentSrc||image?.src||'');await send({worldId:id,name,worldKind:server?'server':'private',iconData:source.startsWith('data:')?source:''});}catch(error){toast(error?.message||String(error),'error');}}); parent.appendChild(button);
    });
  }

  async function enhanceNetworkSettings() {
    if (quickEnabled) return;
    const content=[...document.querySelectorAll('.content')].find((node)=>/settings/i.test(node.querySelector('h1')?.textContent||''));
    if(!content)return;
    const networkActive=!!content.querySelector('[data-application-settings-tab="network"].active');
    if(!networkActive){content.querySelector('[data-v3-network-settings]')?.remove();return;}
    if(content.querySelector('[data-v3-network-settings]'))return;
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
