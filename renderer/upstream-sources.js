(() => {
  'use strict';

  const api = window.dragonwilds;
  const OFFICIAL_URL = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/docs/upstream-sources.json';
  const RC_URL = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/codex/webgui-catalog-console-overhaul/docs/upstream-sources.json';
  const URL_KEY = 'dragonwilds-sync-upstream-registry-url';
  const CACHE_KEY = 'dragonwilds-sync-upstream-registry-cache-v1';
  const REQUIRED = ['rsdwtools', 'rsdw-icons', 'rsdw-item-manifest', 'rsdw-toolkit', 'dragonconnect', 'runeschema', 'ue4ss'];
  let registry = null;
  let sourceUrl = '';
  let loading = false;

  const fallback = {
    schema: 'DragonwildsSync.UpstreamSources.v1',
    updated_at: '',
    sources: {
      rsdwtools: { display_name:'RSDWTools', enabled:true, type:'github-branch', repository:'RSDWArchive/RSDWTools', branch:'main', runtime_component:false, description:'GitHub-backed icons, item manifest and reference data. Not the UE4SS Toolkit runtime.' },
      'rsdw-icons': { display_name:'RSDW Icons', enabled:true, type:'github-path', repository:'RSDWArchive/RSDWTools', branch:'main', path:'website/shared/icons', parent:'rsdwtools' },
      'rsdw-item-manifest': { display_name:'RSDW Item Manifest', enabled:true, type:'github-path', repository:'RSDWArchive/RSDWTools', branch:'main', path:'data/items/json/RSDragonwilds', parent:'rsdwtools' },
      'rsdw-toolkit': { display_name:'RSDW Dev Kit', enabled:true, type:'github-release', repository:'RSDWArchive/RSDWDevKit', release_url:'https://github.com/RSDWArchive/RSDWDevKit/releases', runtime_component:true, runtime_roles:['server','host'], icon:'assets/navigation/rsdw-l.webp', legacy_physical_names:['RSDWTools'], description:'Server/host-only UE4SS runtime tooling. Updated from the RSDWDevKit release channel and never sent to clients.' },
      dragonconnect: { display_name:'DragonLink-Connect', enabled:true, type:'bundled-resource', bundled_fallback:'resources/DragonLink-Connect-baseline.zip', runtime_component:true, runtime_roles:['server','host','client'], legacy_physical_names:['DragonConnectHelper','PersistentDirectConnectIP'] },
      runeschema: { display_name:'RuneSchema', enabled:true, type:'direct-zip', repository:'gh0sted5456-us/Dragonwilds-Sync', branch:'main', download_url:'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/resources/RuneSchema-core-latest.zip' },
      ue4ss: { display_name:'UE4SS', enabled:true, type:'github-release', repository:'UE4SS-RE/RE-UE4SS', release_url:'https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest' },
      rsdwmodel: { display_name:'RSDWModel', enabled:true, type:'github-branch', repository:'RSDWArchive/RSDWModel', branch:'main' }
    }
  };

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const configuredUrl = () => { try { return String(localStorage.getItem(URL_KEY) || '').trim(); } catch (_) { return ''; } };
  const cacheRegistry = (value, url) => { try { localStorage.setItem(CACHE_KEY, JSON.stringify({ registry:value, url, cached_at:Date.now() })); } catch (_) {} };
  const readCache = () => { try { const value=JSON.parse(localStorage.getItem(CACHE_KEY)||'null'); return value?.registry ? value : null; } catch (_) { return null; } };

  function validate(value) {
    if (!value || value.schema !== 'DragonwildsSync.UpstreamSources.v1' || !value.sources || typeof value.sources !== 'object') throw new Error('Unsupported upstream-source manifest.');
    for (const id of REQUIRED) if (!value.sources[id] || value.sources[id].enabled === false) throw new Error(`Required source is missing or disabled: ${id}`);
    const text = JSON.stringify(value).toLowerCase();
    if (/"(command|postinstall|post_install|script|powershell|shell|exec)"\s*:/.test(text)) throw new Error('Upstream manifest contains a prohibited executable instruction.');
    for (const item of Object.values(value.sources)) {
      if (!item || typeof item !== 'object') continue;
      for (const key of ['download_url','release_url']) {
        const url=String(item[key]||'').trim();
        if (url && !/^https:\/\//i.test(url)) throw new Error(`${key} must use HTTPS.`);
      }
    }
    return value;
  }

  async function fetchJson(url) {
    const response = await fetch(url, { cache:'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return validate(await response.json());
  }

  async function loadRegistry(force = false) {
    if (registry && !force) return registry;
    const custom = configuredUrl();
    const urls = [...new Set([custom, OFFICIAL_URL, RC_URL].filter(Boolean))];
    let lastError = null;
    for (const url of urls) {
      try {
        const value = await fetchJson(url);
        registry = value; sourceUrl = url; cacheRegistry(value, url); return value;
      } catch (error) { lastError = error; }
    }
    const cached = readCache();
    if (cached) {
      try { registry=validate(cached.registry); sourceUrl=`Cached · ${cached.url||'last known good'}`; return registry; } catch (_) {}
    }
    registry = validate(fallback); sourceUrl = `Bundled fallback${lastError ? ` · ${lastError.message}` : ''}`; return registry;
  }

  const src = (id) => registry?.sources?.[id] || fallback.sources[id] || {};
  const sourceDetail = (id) => {
    const item=src(id); const bits=[];
    if(item.repository) bits.push(item.repository);
    if(item.branch) bits.push(item.branch);
    if(item.path) bits.push(item.path);
    if(item.type) bits.push(item.type);
    return bits.join(' · ');
  };
  const setStatus = (host, text, kind='') => { const node=host?.querySelector('[data-upstream-status]'); if(node){node.textContent=text;node.dataset.kind=kind;} };

  async function configureRsdwSources() {
    const tools=src('rsdwtools'); const model=src('rsdwmodel');
    await api.invoke('application.update', { rsdw_cache: {
      repo:String(tools.repository||'RSDWArchive/RSDWTools'), branch:String(tools.branch||'main'),
      model_repo:String(model.repository||'RSDWArchive/RSDWModel'), model_branch:String(model.branch||'main')
    }});
  }

  async function refreshRsdw(host, label='RSDW content') {
    setStatus(host, `Refreshing ${label}…`);
    await configureRsdwSources();
    const result = await api.invoke('application.rsdw.refresh', { force:true });
    setStatus(host, `${label} refreshed${result?.changed === false ? ' · already current' : ''}.`, 'ok');
    return result;
  }

  async function repairDragonConnect(host) {
    setStatus(host, 'Repairing DragonLink-Connect…');
    const result = await api.invoke('application.dragonconnect.repair', {});
    const row=result?.dragonconnect||{};
    setStatus(host, `DragonLink-Connect ${row.current===false?'repaired':'verified'} · ${row.available_version||row.installed_version||'bundled baseline'}.`, 'ok');
    return result;
  }

  async function updateRuneSchema(host) {
    const item=src('runeschema'); const url=String(item.download_url||item.release_url||'').trim();
    if(!url) throw new Error('RuneSchema has no downloadable source in the current registry; use the bundled/local core.');
    setStatus(host,'Updating RuneSchema…');
    const result=await api.invoke('server.install.runeschema_update',{releases_url:url});
    setStatus(host,'RuneSchema updated.','ok'); return result;
  }

  async function updateUe4ss(host) {
    const item=src('ue4ss'); const url=String(item.release_url||item.download_url||'').trim();
    if(!url) throw new Error('UE4SS has no update source in the current registry.');
    setStatus(host,'Updating UE4SS…');
    const result=await api.invoke('server.install.ue4ss_update',{releases_url:url});
    setStatus(host,'UE4SS updated.','ok'); return result;
  }

  async function updateRsdwDevKit(host) {
    const item=src('rsdw-toolkit'); const url=String(item.release_url||item.download_url||'').trim();
    if(!url) throw new Error('RSDW Dev Kit has no downloadable GitHub release source.');
    setStatus(host,'Updating the server RSDW Dev Kit…');
    const result=await api.invoke('server.install.rsdwdevkit_update',{releases_url:url});
    setStatus(host,`RSDW Dev Kit updated${result?.result?.release_tag?` · ${result.result.release_tag}`:''}.`,'ok');
    return result;
  }

  function row(id, action, label) {
    const item=src(id);
    const icon=String(item.icon||'').trim();
    return `<div class="settings-row upstream-source-row">${icon?`<img class="upstream-source-icon" src="${esc(icon)}" alt=""/>`:''}<div class="settings-copy"><strong>${esc(item.display_name||id)}</strong><span>${esc(item.description||sourceDetail(id))}</span><small>${esc(sourceDetail(id))}</small></div><button class="btn ghost compact-btn" data-upstream-action="${esc(action)}">${esc(label)}</button></div>`;
  }

  async function renderPanel(page) {
    if (!page || page.querySelector('#upstream-source-registry')) return;
    await loadRegistry(false);
    const base=[...page.querySelectorAll('.settings-section')].find((section)=>/Base Runtime Cores/i.test(section.textContent||''));
    if(!base)return;
    const section=document.createElement('section'); section.id='upstream-source-registry'; section.className='settings-section';
    section.innerHTML=`<style>#upstream-source-registry .upstream-source-row small{display:block;color:var(--muted);margin-top:4px;overflow-wrap:anywhere}#upstream-source-registry [data-upstream-status][data-kind="ok"]{color:#70d6a0}#upstream-source-registry [data-upstream-status][data-kind="error"]{color:#ef8b83}</style><div class="panel-header"><div><h2 style="margin:0">Content & Dependency Sources</h2><div class="panel-subtitle">One validated registry distinguishes RSDWTools data, RSDW Toolkit / DevKit runtime tooling, DragonLink-Connect, RuneSchema and UE4SS. Source URLs can move through an approved commit without teaching the launcher a second ownership model.</div></div><button class="btn primary compact-btn" data-upstream-action="all">Update / Repair All</button></div><div class="settings-row"><div class="settings-copy"><strong>Upstream Registry</strong><span>Official URL is baked only as the bootstrap pointer. A validated last-known-good copy is cached for outages.</span></div><div style="min-width:min(680px,60vw)"><input class="field" data-upstream-url value="${esc(configuredUrl()||OFFICIAL_URL)}"/><div class="header-actions" style="margin-top:7px"><button class="btn ghost compact-btn" data-upstream-action="refresh-registry">Refresh Sources</button><button class="btn ghost compact-btn" data-upstream-action="save-registry">Use This Registry</button><button class="btn ghost compact-btn" data-upstream-action="reset-registry">Reset Official</button></div><small>Loaded: ${esc(sourceUrl||'fallback')}</small></div></div>${row('rsdwtools','rsdw','Refresh RSDWTools Data')}${row('rsdw-icons','icons','Refresh Icons')}${row('rsdw-item-manifest','items','Refresh Item Manifest')}${row('rsdw-toolkit','toolkit','Update Server Dev Kit')}${row('dragonconnect','dragonconnect','Repair DragonLink-Connect')}${row('runeschema','runeschema','Update RuneSchema')}${row('ue4ss','ue4ss','Update UE4SS')}<div class="identity-box"><strong>RSDWTools ≠ RSDW Toolkit</strong><p>RSDWTools is the GitHub data source for icons/item metadata. RSDW Toolkit / DevKit is the server/host UE4SS runtime tooling mod from RSDWArchive/RSDWDevKit. DragonLink-Connect is hidden baseline infrastructure for both the host and joining client; former DragonConnectHelper and PersistentDirectConnectIP folders are accepted only as migration input and retired during repair.</p></div><div class="identity-box"><strong>Safe update boundary</strong><p>The registry may provide HTTPS repositories, paths and release/archive URLs only. Dragonwilds Sync does not accept shell commands, PowerShell, post-install scripts or arbitrary executable instructions from the remote manifest.</p></div><div class="panel-subtitle" data-upstream-status>Ready.</div>`;
    base.insertAdjacentElement('beforebegin',section);

    section.addEventListener('click',async(event)=>{
      const button=event.target.closest('[data-upstream-action]'); if(!button||loading)return;
      loading=true; const action=button.dataset.upstreamAction; button.disabled=true;
      try{
        if(action==='refresh-registry'){registry=null;await loadRegistry(true);setStatus(section,`Sources refreshed from ${sourceUrl}.`,'ok');section.remove();renderPanel(page);return;}
        if(action==='save-registry'){const value=section.querySelector('[data-upstream-url]')?.value.trim()||OFFICIAL_URL;if(!/^https:\/\//i.test(value))throw new Error('Registry URL must use HTTPS.');localStorage.setItem(URL_KEY,value);registry=null;await loadRegistry(true);setStatus(section,`Registry changed and validated: ${sourceUrl}`,'ok');section.remove();renderPanel(page);return;}
        if(action==='reset-registry'){localStorage.removeItem(URL_KEY);registry=null;await loadRegistry(true);section.remove();renderPanel(page);return;}
        if(action==='rsdw'||action==='icons'||action==='items')await refreshRsdw(section,action==='icons'?'RSDW icons':action==='items'?'RSDW item manifest':'RSDWTools data/content');
        if(action==='toolkit')await updateRsdwDevKit(section);
        if(action==='dragonconnect')await repairDragonConnect(section);
        if(action==='runeschema')await updateRuneSchema(section);
        if(action==='ue4ss')await updateUe4ss(section);
        if(action==='all'){
          await refreshRsdw(section,'RSDWTools data, icons and item manifest');
          try{await repairDragonConnect(section);}catch(error){setStatus(section,`Data refresh completed; DragonLink-Connect needs attention: ${error.message}`,'error');}
          for(const fn of [updateRsdwDevKit,updateRuneSchema,updateUe4ss]){try{await fn(section);}catch(error){setStatus(section,`Content refresh completed; runtime update needs attention: ${error.message}`,'error');}}
        }
      }catch(error){setStatus(section,error.message||String(error),'error');}
      finally{loading=false;button.disabled=false;}
    });

    const ue4ss=page.querySelector('#server-ue4ss-source-url'); if(ue4ss)ue4ss.value=String(src('ue4ss').release_url||src('ue4ss').download_url||ue4ss.value||'');
  }

  function enhance() {
    const page=[...document.querySelectorAll('.settings-section')].find((section)=>/Base Runtime Cores/i.test(section.textContent||''))?.parentElement;
    if(page)renderPanel(page).catch(()=>{});
  }
  let pending=false; const schedule=()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;enhance();});};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
})();
