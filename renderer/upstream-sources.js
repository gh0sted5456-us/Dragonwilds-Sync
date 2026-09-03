(() => {
  'use strict';

  const api = window.dragonwilds;
  const OFFICIAL_URL = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/docs/upstream-sources.json';
  const RC_URL = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/codex/webgui-catalog-console-overhaul/docs/upstream-sources.json';
  const URL_KEY = 'dragonwilds-sync-upstream-registry-url';
  const CACHE_KEY = 'dragonwilds-sync-upstream-registry-cache-v1';
  const FETCH_TIMEOUT_MS = 3500;
  const REQUIRED = ['rsdwtools', 'rsdw-icons', 'rsdw-item-manifest', 'rsdw-toolkit', 'dragonconnect', 'runeschema', 'ue4ss'];
  let registry = null;
  let sourceUrl = '';
  let loading = false;
  let backgroundRefresh = null;

  const fallback = {
    schema: 'DragonwildsSync.UpstreamSources.v1',
    updated_at: '',
    sources: {
      rsdwtools: { display_name:'RSDWTools', enabled:true, type:'github-branch', repository:'RSDWArchive/RSDWTools', branch:'main', runtime_component:false, description:'GitHub-backed icons, item manifest and reference data. Not the UE4SS Toolkit runtime.' },
      'rsdw-icons': { display_name:'RSDW Icons', enabled:true, type:'github-path', repository:'RSDWArchive/RSDWTools', branch:'main', path:'website/shared/icons', parent:'rsdwtools' },
      'rsdw-item-manifest': { display_name:'RSDW Item Manifest', enabled:true, type:'github-path', repository:'RSDWArchive/RSDWTools', branch:'main', path:'data/items/json/RSDragonwilds', parent:'rsdwtools' },
      'rsdw-toolkit': { display_name:'RSDW Dev Kit', enabled:true, type:'github-release', repository:'RSDWArchive/RSDWDevKit', release_url:'https://github.com/RSDWArchive/RSDWDevKit/releases', runtime_component:true, runtime_roles:['server','host'], icon:'assets/navigation/rsdw-l.webp', legacy_physical_names:['RSDWTools'], description:'Server/host-only UE4SS runtime tooling. Updated from the RSDWDevKit release channel and never sent to clients.' },
      dragonconnect: { display_name:'DragonConnect', enabled:true, type:'bundled-lua-core', bundled_fallback:'resources/NativeRuntimeMods/DragonConnect', runtime_component:true, runtime_roles:['client'], description:'Launcher-owned Lua client Core for one-time Direct Connect address/password handoff.' },
      runeschema: { display_name:'RuneSchema', enabled:true, type:'github-release', repository:'UnskippableCutscene/RuneSchema', release_url:'https://github.com/UnskippableCutscene/RuneSchema/releases', bundled_fallback:'resources/RuneSchema-core-latest.zip', runtime_roles:['server','client'], description:'The packaged stable build is always retained. Official GitHub releases download into the local version library so they can be selected, repaired, or rolled back.' },
      ue4ss: { display_name:'UE4SS', enabled:true, type:'github-release', repository:'UE4SS-RE/RE-UE4SS', release_url:'https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest', bundled_fallback:'resources/DragonwildsServerRuntime/UE4SS-core-latest.zip', runtime_roles:['server','client'], description:'The packaged stable build is always retained. New upstream builds download into the local version library instead of replacing rollback history.' },
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

  function primeRegistryFromLocal() {
    if (registry) return registry;
    const cached = readCache();
    if (cached) {
      try {
        registry = validate(cached.registry);
        sourceUrl = `Cached · ${cached.url || 'last known good'}`;
        return registry;
      } catch (_) {}
    }
    registry = validate(fallback);
    sourceUrl = 'Bundled fallback';
    return registry;
  }

  async function fetchJson(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const response = await fetch(url, { cache:'no-store', signal:controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return validate(await response.json());
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error(`Timed out after ${FETCH_TIMEOUT_MS} ms`);
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async function loadRegistry(force = false) {
    if (!force) return primeRegistryFromLocal();
    const previous = registry;
    const previousSource = sourceUrl;
    const custom = configuredUrl();
    const urls = [...new Set([custom, OFFICIAL_URL, RC_URL].filter(Boolean))];
    let lastError = null;
    for (const url of urls) {
      try {
        const value = await fetchJson(url);
        registry = value;
        sourceUrl = url;
        cacheRegistry(value, url);
        return value;
      } catch (error) {
        lastError = error;
      }
    }
    if (previous) {
      registry = previous;
      sourceUrl = previousSource || 'Bundled fallback';
      return registry;
    }
    primeRegistryFromLocal();
    if (lastError && sourceUrl === 'Bundled fallback') sourceUrl = `Bundled fallback · ${lastError.message}`;
    return registry;
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
  const selectedVersion = (result) => {
    const id=String(result?.selected_id||'');
    return (result?.versions||[]).find((row)=>String(row?.id||'')===id)||null;
  };

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
    setStatus(host, 'Repairing DragonConnect…');
    const result = await api.invoke('application.dragonconnect.repair', {});
    const row=result?.dragonconnect||{};
    setStatus(host, `DragonConnect ${row.current===false?'repaired':'verified'} · ${row.available_version||row.installed_version||'bundled Lua core'}.`, 'ok');
    return result;
  }

  async function downloadRuneSchemaUpdate(host) {
    const item=src('runeschema'); const url=String(item.release_url||item.download_url||'https://github.com/UnskippableCutscene/RuneSchema/releases').trim();
    if(!url) throw new Error('RuneSchema has no downloadable GitHub release source.');
    setStatus(host,'Downloading RuneSchema update…');
    const result=await api.invoke('application.runeschema_repository.fetch_experimental',{source_url:url});
    const row=selectedVersion(result);
    setStatus(host,`RuneSchema ${row?.label||'update'} saved to the version library. The Stable Packaged Build was kept.`, 'ok');
    return result;
  }

  async function downloadUe4ssUpdate(host) {
    const item=src('ue4ss'); const url=String(item.release_url||item.download_url||'').trim();
    if(!url) throw new Error('UE4SS has no update source in the current registry.');
    setStatus(host,'Downloading UE4SS update…');
    const result=await api.invoke('application.ue4ss_repository.fetch_experimental',{source_url:url});
    const row=selectedVersion(result);
    setStatus(host,`UE4SS ${row?.label||'update'} saved to the version library. The Stable Packaged Build was kept.`, 'ok');
    return result;
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

  function refreshRegistryInBackground(page, section) {
    if (backgroundRefresh) return backgroundRefresh;
    const beforeRegistry = JSON.stringify(registry || {});
    const beforeSource = sourceUrl;
    backgroundRefresh = loadRegistry(true).then(() => {
      if (!page?.isConnected || !section?.isConnected) return;
      if (beforeRegistry !== JSON.stringify(registry || {}) || beforeSource !== sourceUrl) {
        section.remove();
        renderPanel(page, { skipBackground:true });
      }
    }).catch((error) => {
      if (section?.isConnected) setStatus(section, `Using local source registry · background refresh unavailable: ${error.message||error}`);
    }).finally(() => { backgroundRefresh = null; });
    return backgroundRefresh;
  }

  async function renderPanel(page, options = {}) {
    if (!page || page.querySelector('#upstream-source-registry')) return;
    // Never place GitHub/network work on Settings first paint. A validated cache
    // or the bundled registry is enough to render every control immediately.
    primeRegistryFromLocal();
    const base=[...page.querySelectorAll('.settings-section')].find((section)=>/Base Runtime Cores/i.test(section.textContent||''));
    if(!base)return;
    const section=document.createElement('section'); section.id='upstream-source-registry'; section.className='settings-section';
    section.innerHTML=`<style>#upstream-source-registry .upstream-source-row small{display:block;color:var(--muted);margin-top:4px;overflow-wrap:anywhere}#upstream-source-registry [data-upstream-status][data-kind="ok"]{color:#70d6a0}#upstream-source-registry [data-upstream-status][data-kind="error"]{color:#ef8b83}</style><div class="panel-header"><div><h2 style="margin:0">Content & Dependency Sources</h2><div class="panel-subtitle">Packaged UE4SS and RuneSchema builds are the permanent stable repair points. GitHub updates are downloaded into version libraries and kept until you explicitly remove them. RSDWTools data and the RSDW Dev Kit remain separate sources.</div></div><button class="btn primary compact-btn" data-upstream-action="all">Refresh / Download All</button></div><div class="settings-row"><div class="settings-copy"><strong>Upstream Registry</strong><span>Official URL is baked only as the bootstrap pointer. A validated last-known-good copy is cached for outages.</span></div><div style="min-width:min(680px,60vw)"><input class="field" data-upstream-url value="${esc(configuredUrl()||OFFICIAL_URL)}"/><div class="header-actions" style="margin-top:7px"><button class="btn ghost compact-btn" data-upstream-action="refresh-registry">Refresh Sources</button><button class="btn ghost compact-btn" data-upstream-action="save-registry">Use This Registry</button><button class="btn ghost compact-btn" data-upstream-action="reset-registry">Reset Official</button></div><small>Loaded: ${esc(sourceUrl||'Bundled fallback')}</small></div></div>${row('rsdwtools','rsdw','Refresh RSDWTools Data')}${row('rsdw-icons','icons','Refresh Icons')}${row('rsdw-item-manifest','items','Refresh Item Manifest')}${row('rsdw-toolkit','toolkit','Update Server Dev Kit')}${row('dragonconnect','dragonconnect','Repair DragonConnect')}${row('runeschema','runeschema','Download RuneSchema Update')}${row('ue4ss','ue4ss','Download UE4SS Update')}<div class="identity-box"><strong>Stable first, updates retained</strong><p>UE4SS and RuneSchema always keep the packaged Stable Build. Downloading an update adds another version to the application library; it does not erase the stable package or older downloaded builds. Choose the version you want from the runtime version controls when you are ready to apply or repair it.</p></div><div class="identity-box"><strong>RSDWTools ≠ RSDW Dev Kit</strong><p>RSDWTools is the GitHub data source for icons/item metadata. RSDW Dev Kit is the server/host UE4SS runtime tooling mod from RSDWArchive/RSDWDevKit. DragonConnect is hidden launcher-owned Lua client Core for Direct Connect handoff.</p></div><div class="identity-box"><strong>Safe update boundary</strong><p>The registry may provide HTTPS repositories, paths and release/archive URLs only. Dragonwilds Sync does not accept shell commands, PowerShell, post-install scripts or arbitrary executable instructions from the remote manifest.</p></div><div class="panel-subtitle" data-upstream-status>Ready.</div>`;
    base.insertAdjacentElement('beforebegin',section);

    section.addEventListener('click',async(event)=>{
      const button=event.target.closest('[data-upstream-action]'); if(!button||loading)return;
      loading=true; const action=button.dataset.upstreamAction; button.disabled=true;
      try{
        if(action==='refresh-registry'){
          await loadRegistry(true);
          setStatus(section,`Sources refreshed from ${sourceUrl}.`,'ok');
          section.remove(); renderPanel(page,{skipBackground:true}); return;
        }
        if(action==='save-registry'){
          const value=section.querySelector('[data-upstream-url]')?.value.trim()||OFFICIAL_URL;
          if(!/^https:\/\//i.test(value))throw new Error('Registry URL must use HTTPS.');
          localStorage.setItem(URL_KEY,value);
          await loadRegistry(true);
          setStatus(section,`Registry changed and validated: ${sourceUrl}`,'ok');
          section.remove(); renderPanel(page,{skipBackground:true}); return;
        }
        if(action==='reset-registry'){
          localStorage.removeItem(URL_KEY);
          await loadRegistry(true);
          section.remove(); renderPanel(page,{skipBackground:true}); return;
        }
        if(action==='rsdw'||action==='icons'||action==='items')await refreshRsdw(section,action==='icons'?'RSDW icons':action==='items'?'RSDW item manifest':'RSDWTools data/content');
        if(action==='toolkit')await updateRsdwDevKit(section);
        if(action==='dragonconnect')await repairDragonConnect(section);
        if(action==='runeschema')await downloadRuneSchemaUpdate(section);
        if(action==='ue4ss')await downloadUe4ssUpdate(section);
        if(action==='all'){
          await refreshRsdw(section,'RSDWTools data, icons and item manifest');
          try{await repairDragonConnect(section);}catch(error){setStatus(section,`Data refresh completed; DragonConnect needs attention: ${error.message}`,'error');}
          for(const fn of [updateRsdwDevKit,downloadRuneSchemaUpdate,downloadUe4ssUpdate]){try{await fn(section);}catch(error){setStatus(section,`Content refresh completed; runtime download needs attention: ${error.message}`,'error');}}
        }
      }catch(error){setStatus(section,error.message||String(error),'error');}
      finally{loading=false;button.disabled=false;}
    });

    const ue4ss=page.querySelector('#server-ue4ss-source-url'); if(ue4ss)ue4ss.value=String(src('ue4ss').release_url||src('ue4ss').download_url||ue4ss.value||'');
    if(!options.skipBackground) queueMicrotask(()=>refreshRegistryInBackground(page,section));
  }

  function enhance() {
    const page=[...document.querySelectorAll('.settings-section')].find((section)=>/Base Runtime Cores/i.test(section.textContent||''))?.parentElement;
    if(page)renderPanel(page).catch(()=>{});
  }
  let pending=false; const schedule=()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;enhance();});};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  const observationRoot=document.getElementById('app')||document.documentElement;
  new MutationObserver(schedule).observe(observationRoot,{childList:true,subtree:true});
})();