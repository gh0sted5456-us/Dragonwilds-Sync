(() => {
  'use strict';

  const api = window.dragonwilds;
  if (!api?.invoke) return;

  // A World may be rendered in more than one collection at once (for example
  // Favorites plus Connected Worlds). Card face is presentation state, not
  // World state, so key it by the actual card element. Keying by World id made
  // every visible copy flip together on the next decoration pass.
  const cardSides = new WeakMap();
  const network = new Map();
  const openRows = new Map();
  const windows = new Map();
  const modDialogs = new Map();
  const modInventory = new Map();
  let decorating = false;
  let heartbeatTimer = null;

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const text = (value) => String(value ?? '').trim();
  const asArray = (value) => Array.isArray(value) ? value : [];
  const state = () => (window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object') ? window.__DWSYNC_STATE__ : {};
  const ecosystemAssets = {UE4SS:'assets/platforms/ue4ss.webp',RuneSchema:'assets/platforms/runeschema.webp',Pak:'assets/platforms/paks.svg'};
  const animationMode = () => {
    const value = text(state()?.application?.v3_phase4?.animation_mode || state()?.application?.performance?.animations || 'full').toLowerCase();
    return ['full','reduced','off'].includes(value) ? value : 'full';
  };

  function normalizeTags(values, limit=24) {
    if (typeof values === 'string') values = values.split(/[,;\n]+/);
    const result = [], seen = new Set();
    for (const raw of asArray(values)) {
      const value = text(raw).replace(/^#/,'').replace(/\s+/g,' ').slice(0,40);
      const key = value.toLowerCase();
      if (!value || seen.has(key)) continue;
      seen.add(key); result.push(value);
      if (result.length >= limit) break;
    }
    return result;
  }

  function normalizePlatforms(value) {
    const aliases = {steam:'steam',epic:'epic',epicgames:'epic','epic games':'epic',xbox:'xbox',playstation:'playstation',psn:'playstation',nintendo:'nintendo',windows:'windows',linux:'linux'};
    const values = value && typeof value === 'object' && !Array.isArray(value)
      ? Object.entries(value).filter(([,enabled])=>!!enabled).map(([key])=>key)
      : (typeof value === 'string' ? value.split(/[,;\n]+/) : asArray(value));
    return [...new Set(values.map((raw)=>aliases[text(raw).toLowerCase()]).filter(Boolean))];
  }

  function badgeRows(world) {
    const sources = [world?.custom_badges, world?.presentation?.custom_badges, world?.community?.badges, world?.badge_refs, world?.badges];
    const result = [], seen = new Set();
    for (const source of sources) {
      for (const raw of asArray(source)) {
        const row = typeof raw === 'string' ? {label: raw, tooltip: raw} : (raw && typeof raw === 'object' ? raw : null);
        if (!row) continue;
        const label = text(row.label || row.name || row.title || row.id).slice(0,80);
        const tooltip = text(row.tooltip || row.meaning || row.description || (typeof raw === 'string' ? raw : '')).slice(0,240);
        if (!label || !tooltip) continue;
        const key = text(row.id || label).toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        const data = text(row.image_data || row.png_data || row.data_url);
        const remote = text(row.asset_url || row.image_url);
        const image = /^data:image\/png;base64,/i.test(data) ? data : (/^https:\/\//i.test(remote) ? remote : '');
        const link = /^https:\/\//i.test(text(row.link || row.url)) ? text(row.link || row.url) : '';
        result.push({label, tooltip, image, link, assetHash:text(row.asset_hash || row.sha256)});
        if (result.length >= 16) return result;
      }
    }
    return result;
  }

  function modRows(world) {
    const worldId=text(world?.id || world?.profile_id || world?.world_id);
    const connected=asArray(state()?.client?.worlds).some((row)=>text(row?.id)===worldId);
    const sources = connected
      ? [modInventory.get(worldId)?.remote ? modInventory.get(worldId).rows : null, world?.presentation?.mod_summary, world?.manifest_cache?.mod_summary, world?.mod_metadata]
      : [modInventory.get(worldId)?.rows, world?.mod_metadata, world?.manifest_cache?.mod_summary, world?.metadata_cache?.mods, world?.mods, world?.manifest?.mods, world?.world_manifest?.mods, world?.mod_requirements, world?.sync_config?.required_mods];
    const rows = [];
    for (const source of sources) {
      for (const raw of asArray(source)) {
        const row = typeof raw === 'string' ? {name:raw} : (raw && typeof raw === 'object' ? raw : null);
        if (!row) continue;
        const name = text(row.name || row.display_name || row.mod_name || row.id || row.key);
        if (!name || /^(readme(?:\.[^/]+)?|mods\.txt|enabled\.txt)$/i.test(name) || /^dragonconnect$/i.test(name.replace(/\s+/g,''))) continue;
        const rawType = text(`${row.section || ''} ${row.group || ''} ${row.type || ''} ${row.kind || ''} ${row.loader || ''} ${row.mod_type || ''}`).toLowerCase();
        const type = rawType.includes('rune') ? 'RuneSchema' : rawType.includes('pak') ? 'Pak' : 'UE4SS';
        const role = text(row.runtime_role || row.role || row.scope || 'BOTH').toUpperCase();
        rows.push({name, version:text(row.version || row.mod_version), type, role, required:row.required !== false});
      }
      if (rows.length) break;
    }
    const seen = new Set();
    return rows.filter((row)=>{const key=`${row.type}:${row.name}`.toLowerCase();if(seen.has(key))return false;seen.add(key);return true;}).slice(0,64);
  }

  function placardId(world, card) {
    const current=text(card?.style?.getPropertyValue('--world-placard')); const currentMatch=current.match(/placards\/([1-9])\.png/i);
    const value=text(world?.placard_background || world?.presentation?.placard_background || world?.presentation?.placardBackground || world?.placardBackground || card?.dataset?.placardBackground || currentMatch?.[1] || '1');
    return ['1','2','3','4','5','6','7','8','9'].includes(value) ? value : '1';
  }

  function applyPlacardArtwork(card, world) {
    const id=placardId(world,card); const asset=`assets/placards/${id}.webp`;
    card.classList.add('has-placard'); card.dataset.placardBackground=id;
    card.style.setProperty('--world-placard',`url("${asset}")`);
    let preload=card.querySelector(':scope>.v3p4-placard-preload');
    if(!preload){preload=document.createElement('img');preload.className='v3p4-placard-preload';preload.alt='';preload.setAttribute('aria-hidden','true');card.prepend(preload);}
    if(preload.getAttribute('src')!==asset)preload.src=asset;
  }

  function ecosystemFamilies(world) {
    const mods=modRows(world); const advertised=asArray(world?.presentation?.mod_badges).map((value)=>text(value).toLowerCase());
    return ['Pak','UE4SS','RuneSchema'].filter((family)=>mods.some((row)=>row.type===family) || (family==='UE4SS'&&!!world?.auto_ue4ss) || (family==='RuneSchema'&&!!world?.auto_runeschema) || advertised.some((value)=>value.replace(/\s+/g,'')===(family==='Pak'?'paks':family.toLowerCase())));
  }

  function ecosystemMarkup(id, world, compact=false) {
    const families=ecosystemFamilies(world); if(!families.length)return '';
    return `<div class="v3p4-ecosystems ${compact?'compact':''}" aria-label="Loaded mod frameworks">${families.map((family)=>`<button type="button" class="v3p4-ecosystem" data-v3p4-mod-family="${esc(family)}" data-v3p4-mod-world="${esc(id)}" title="Show loaded ${esc(family)} mods"><img src="${ecosystemAssets[family]}" alt=""/><span>${esc(family)}</span></button>`).join('')}</div>`;
  }

  function decorateEcosystemLabels(root=document) {
    root.querySelectorAll('.badge,.tag,.status-pill,.v3p4-back-section h4').forEach((node)=>{
      if(node.dataset.ecosystem)return;
      const value=text(node.textContent).replace(/\s+/g,'').toLowerCase(); const family=value==='ue4ss'?'UE4SS':value==='runeschema'?'RuneSchema':'';
      if(family){node.dataset.ecosystem=family;node.style.setProperty('--ecosystem-icon',`url("${ecosystemAssets[family]}")`);}
    });
  }

  async function openModsPopup(id, family) {
    id=text(id); family=family==='RuneSchema'?'RuneSchema':family==='Pak'?'Pak':'UE4SS'; if(!id)return;
    const key=`${id}:${family}`; const existing=modDialogs.get(key);
    if(existing){window.__DWSYNC_DESKTOP_WINDOWS__?.focus?.(existing);return;}
    if(asArray(state()?.client?.worlds).some((row)=>text(row?.id)===id))await requestProfileModInventory(id,'connected',true);
    const world=findWorld(id)||{id,name:'World'}; const rows=modRows(world).filter((row)=>row.type===family);
    const desktop=window.__DWSYNC_DESKTOP_WINDOWS__;if(!desktop?.open)return;
    const worldName=world.name||world.nickname||world.identity?.world_name||'World';
    const stack=modInventory.get(id)?.runtimeStack||world.runtime_stack||world.manifest_cache?.runtime_stack||world.presentation?.runtime_stack||{};
    const runtime=stack[family==='UE4SS'?'ue4ss':'runeschema']||{};
    const runtimeLabel=runtime.installed_version||runtime.version||runtime.source_name||runtime.name||'Version not advertised by this profile';
    const host=desktop.open(`<div class="modal-header v3p4-mod-window-header"><div class="v3p4-mod-window-title"><img src="${ecosystemAssets[family]}" alt=""/><span><small>PROFILE MODS · ${esc(family)}</small><h2>${esc(worldName)}</h2></span></div></div><div class="modal-body v3p4-mod-window-body"><h3>${esc(family)} loaded mods</h3>${rows.length?`<div class="v3p4-mod-list">${rows.map((row)=>`<div><strong>${esc(row.name)}</strong><span>${esc(row.version||'Version not advertised')} · ${esc(row.role)} · ${row.required?'Required':'Optional'}</span></div>`).join('')}</div>`:`<div class="v3p4-empty">No loaded ${esc(family)} mods are recorded for this profile.</div>`}</div>`,{title:`${family} mods · ${worldName}`,width:680,height:Math.min(760,Math.max(420,210+rows.length*38))});
    if(family!=='Pak')host.querySelector('.v3p4-mod-window-body h3')?.insertAdjacentHTML('afterend',`<p class="runtime-version-label">${esc(family)} loader: ${esc(runtimeLabel)}${runtime.channel?` · ${esc(runtime.channel)}`:''}</p>`);
    host.classList.add('v3p4-mod-window');host.dataset.v3p4ModDialog=key;host._dwsDispose=()=>modDialogs.delete(key);modDialogs.set(key,host);
  }

  function closeModsPopup(key) { const host=modDialogs.get(key)||document.querySelector(`[data-v3p4-mod-dialog="${CSS.escape(key)}"]`);if(host)window.__DWSYNC_DESKTOP_WINDOWS__?.close?.(host);modDialogs.delete(key); }

  function refreshModIndicators(id) {
    const world=findWorld(id)||{id,name:'World'};
    document.querySelectorAll(`.v3p4-placard[data-world-id="${CSS.escape(id)}"]`).forEach((card)=>{
      card.querySelectorAll('.v3p4-ecosystems').forEach((node)=>node.remove());
      const markup=ecosystemMarkup(id,world,true); if(!markup)return;
      const mount=card.classList.contains('app-world-placard')?card.querySelector('.world-card-front .world-card-body'):card.querySelector('.v3p4-front-live');
      mount?.insertAdjacentHTML('beforeend',markup);
    });
  }

  function requestProfileModInventory(id, kind='private', force=false) {
    id=text(id); if(!id)return Promise.resolve([]);
    const current=modInventory.get(id); if(current?.pending)return current.pending;
    if(!force&&current?.rows&&Date.now()-current.at<120000)return Promise.resolve(current.rows);
    if(asArray(state()?.client?.worlds).some((row)=>text(row?.id)===id)){
      const pending=api.invoke('world.ping',{id}).then((response)=>{
        const remote=response?.world;
        const rows=asArray(remote?.presentation?.mod_summary || remote?.manifest_cache?.mod_summary);
        modInventory.set(id,{rows,remote:true,runtimeStack:remote?.runtime_stack||remote?.manifest_cache?.runtime_stack||remote?.presentation?.runtime_stack||{},at:Date.now(),pending:null});refreshModIndicators(id);return rows;
      }).catch(()=>{modInventory.set(id,{...current,pending:null});return current?.rows||[];});
      modInventory.set(id,{...current,pending});return pending;
    }
    const method=kind==='server'?'server.world.inventory':'singleplayer.inventory';
    const params=kind==='server'?{id,rescan:false}:{profile_id:id,rescan:false};
    const pending=api.invoke(method,params).then((response)=>{
      const rows=asArray(response?.units || response?.mods || response?.inventory);
      modInventory.set(id,{rows,at:Date.now(),pending:null});refreshModIndicators(id);return rows;
    }).catch(()=>{modInventory.set(id,{rows:current?.rows||[],at:current?.at||0,pending:null});return current?.rows||[];});
    modInventory.set(id,{rows:current?.rows||[],at:current?.at||0,pending});return pending;
  }

  function candidateCollections(root) {
    return [
      root?.server_profiles, root?.server?.profiles, root?.server?.worlds,
      root?.client?.worlds, root?.client?.private_worlds, root?.client?.public_worlds,
      root?.client?.world_browser?.rows, root?.client?.world_browser?.worlds,
      root?.client?.shared_worlds, root?.client?.manifest_worlds,
    ].filter(Array.isArray);
  }

  function findWorld(id) {
    id = text(id); if (!id) return null;
    const root = state();
    for (const rows of candidateCollections(root)) {
      const found = rows.find((row)=>row && text(row.id || row.profile_id || row.world_id) === id);
      if (found) return found;
    }
    const singles = [root?.client?.singleplayer, root?.client?.active_world, root?.server?.active_world];
    return singles.find((row)=>row && text(row.id || row.profile_id || row.world_id) === id) || null;
  }

  function cardWorld(card) {
    const id = text(card?.dataset?.worldId);
    return {id, world:findWorld(id) || {id, name:card?.querySelector('h2,h3')?.textContent || 'World'}, server:card?.dataset?.serverCard === '1'};
  }

  function publicRules(world) {
    return text(world?.community_rules || world?.rules || world?.presentation?.rules || world?.directory_network?.public_card?.rules || world?.public_card?.rules);
  }

  function platformValues(world) {
    return normalizePlatforms(world?.platforms || world?.platform_compatibility || world?.compatibility?.platforms || world?.presentation?.platforms);
  }

  function platformMarkup(world) {
    const platforms = platformValues(world);
    if (!platforms.length) return '';
    return `<div class="v3p4-platforms" aria-label="Supported platforms">${platforms.map((name)=>`<span class="v3p4-platform" title="${esc(name)}"><img src="assets/platforms/${esc(name === 'epic' ? 'epicgames' : name)}.svg" alt="${esc(name)}"/></span>`).join('')}</div>`;
  }

  function customBadgeMarkup(world) {
    const badges = badgeRows(world);
    if (!badges.length) return '';
    return `<div class="v3p4-badge-rail">${badges.map((row)=>{
      const visual = row.image ? `<img src="${esc(row.image)}" alt=""/>` : '<span class="v3p4-badge-fallback">◆</span>';
      const body = `${visual}<span>${esc(row.label)}</span>`;
      return row.link ? `<a class="v3p4-custom-badge" href="${esc(row.link)}" data-v3p4-external="${esc(row.link)}" title="${esc(row.tooltip)}">${body}</a>` : `<span class="v3p4-custom-badge" title="${esc(row.tooltip)}">${body}</span>`;
    }).join('')}</div>`;
  }

  function modsMarkup(world) {
    const mods = modRows(world);
    if (!mods.length) return '';
    return ['UE4SS','RuneSchema','Pak'].map((type)=>{
      const rows = mods.filter((row)=>row.type===type); if (!rows.length) return '';
      const icon=ecosystemAssets[type]?`<img class="v3p4-family-icon" src="${ecosystemAssets[type]}" alt=""/>`:'';
      return `<section class="v3p4-back-section"><h4>${icon}${type}</h4><div class="v3p4-mod-list">${rows.map((row)=>`<div><strong>${esc(row.name)}</strong><span>${esc(row.version || 'Version not advertised')} · ${esc(row.role)} · ${row.required?'Required':'Optional'}</span></div>`).join('')}</div></section>`;
    }).join('');
  }

  function heartbeatInfo(id, world) {
    const cached = network.get(id)?.value;
    const advertised = text(world?.heartbeat?.state || world?.heartbeat_state || world?.network_state || world?.directory_state);
    const status = cached?.heartbeat || cached || {};
    const connectedWorld = world?.kind && !['singleplayer','server','dedicated'].includes(text(world.kind).toLowerCase());
    const observedConnection = connectedWorld && world?.status?.last_checked_at ? (world.status.online ? 'Active' : 'Failed') : '';
    const value = text(status.state || advertised || observedConnection || ((world?.status?.broadcasting || world?.status?.running) ? 'Connecting' : 'Disabled'));
    const stateName = ['active','connecting','partial','failed','disabled'].includes(value.toLowerCase()) ? value[0].toUpperCase()+value.slice(1).toLowerCase() : 'Disabled';
    return {state:stateName,lastSuccess:status.last_success_at || null,destinations:asArray(status.destinations)};
  }

  function heartbeatMarkup(id, world) {
    const info = heartbeatInfo(id, world);
    const cls = info.state.toLowerCase();
    const mode = animationMode();
    const animated = ['Active','Connecting','Partial'].includes(info.state) && mode !== 'off';
    const label = info.state === 'Active' ? 'Connected' : info.state === 'Failed' ? 'Not Connected' : info.state === 'Partial' ? 'Heartbeat Partial' : `Heartbeat ${info.state}`;
    return `<span class="v3p4-heartbeat ${cls} ${animated?'animated':'static'}" role="status" aria-label="${esc(label)}"><span class="v3p4-heart-shape" aria-hidden="true">♥</span><span>${esc(label)}</span></span>`;
  }

  function backMarkup(id, world) {
    const rules = publicRules(world);
    return `<div class="v3p4-back-scroll" tabindex="0" aria-label="World community guidelines">
      ${rules?`<section class="v3p4-back-section"><h4>Community Guidelines</h4><p>${esc(rules)}</p></section>`:'<div class="v3p4-empty">No community guidelines have been broadcast for this World.</div>'}
    </div>
    <div class="v3p4-back-footer">${heartbeatMarkup(id,world)}<span class="card-flip-hint" aria-hidden="true">CLICK CARD · FRONT ↻</span></div>`;
  }

  function applySide(card, id) {
    const side = cardSides.get(card) || 'front';
    card.dataset.v3p4Side = side;
    card.classList.toggle('v3p4-back-visible', side === 'back');
    card.classList.toggle('flipped', card.classList.contains('app-world-placard') && side === 'back');
    card.setAttribute('role', 'button');
    card.setAttribute('aria-pressed', String(side === 'back'));
    card.setAttribute('aria-label', `${text(card.querySelector('h2,h3')?.textContent || 'World')} · ${side === 'back' ? 'details' : 'front'}`);
    const status = card.querySelector('[data-v3p4-page-status]');
    if (status) status.textContent = side === 'back' ? 'Page 2 / 2' : 'Page 1 / 2';
  }

  function decorateCard(card) {
    if (!card || card.dataset.v3p4Decorated === '1' || card.closest('.v3p4-window')) return;
    const {id,world} = cardWorld(card); if (!id) return;
    card.dataset.v3p4Decorated = '1'; card.classList.add('v3p4-placard'); card.tabIndex = card.tabIndex >= 0 ? card.tabIndex : 0; applyPlacardArtwork(card,world);
    if (card.classList.contains('app-world-placard')) {
      const frontBody=card.querySelector('.world-card-front .world-card-body');
      if(frontBody&&!card.querySelector('.v3p4-front-live')){
        const identity=document.createElement('span');identity.className='v3p4-front-live website-parity-live';identity.innerHTML=heartbeatMarkup(id,world);
        const statusMount=card.querySelector('.placard-sync-status');
        if(statusMount)statusMount.replaceChildren(identity);else card.querySelector('.placard-runtime-status')?.prepend(identity);
      }
      if(frontBody&&!card.querySelector('.v3p4-ecosystems')){
        const footer=frontBody.querySelector('.placard-presentation-footer');
        if(footer)footer.insertAdjacentHTML('beforebegin',ecosystemMarkup(id,world,true));
        else frontBody.insertAdjacentHTML('beforeend',ecosystemMarkup(id,world,true));
      }
      decorateEcosystemLabels(card);
      applySide(card,id);requestHeartbeat(id,card.dataset.serverCard==='1'?'dedicated':'local');requestProfileModInventory(id,card.dataset.serverCard==='1'?'server':'private');return;
    }
    const original = document.createElement('div'); original.className = 'v3p4-face v3p4-front';
    while (card.firstChild) original.appendChild(card.firstChild);
    const identity = document.createElement('div'); identity.className='v3p4-front-live'; identity.innerHTML=`${heartbeatMarkup(id,world)}${platformMarkup(world)}${ecosystemMarkup(id,world,true)}`;
    original.appendChild(identity);
    const frontControls = document.createElement('div'); frontControls.className='v3p4-page-controls'; frontControls.innerHTML='<span data-v3p4-page-status>Page 1 / 2</span><span class="card-flip-hint" aria-hidden="true">CLICK CARD · DETAILS ↻</span>'; original.appendChild(frontControls);
    const back = document.createElement('div'); back.className='v3p4-face v3p4-back'; back.innerHTML=backMarkup(id,world);
    const inner = document.createElement('div'); inner.className='v3p4-inner'; inner.append(original,back); card.appendChild(inner); decorateEcosystemLabels(card);
    applySide(card,id);
    requestHeartbeat(id, card.dataset.serverCard === '1' ? 'dedicated' : 'local');
    requestProfileModInventory(id,card.dataset.serverCard==='1'?'server':'private');
  }

  function decorateAll() {
    if (decorating) return; decorating = true;
    try {
      document.body.dataset.v3p4Animations = animationMode();
      document.querySelectorAll('.world-card[data-world-id]:not([data-v3p4-decorated])').forEach(decorateCard);
      document.querySelectorAll('.v3p4-placard').forEach((card)=>applySide(card,text(card.dataset.worldId)));
      decorateEcosystemLabels();
      injectSettings(); injectQuickHeartbeat();
    } finally { decorating = false; }
  }

  async function requestHeartbeat(id, kind='dedicated', force=false) {
    const current = network.get(id);
    if (!force && current && Date.now()-current.at < 30000) return current.value;
    if (current?.pending) return current.pending;
    const pending = api.invoke('v3.phase4.world_status',{id,kind}).then((value)=>{
      network.set(id,{at:Date.now(),value,pending:null});
      refreshPlacardLiveBits(id); return value;
    }).catch(()=>{network.set(id,{at:Date.now(),value:current?.value||null,pending:null});return null;});
    network.set(id,{at:current?.at||0,value:current?.value||null,pending}); return pending;
  }

  function refreshPlacardLiveBits(id) {
    const world = findWorld(id) || {id};
    document.querySelectorAll(`.v3p4-placard[data-world-id="${CSS.escape(id)}"]`).forEach((card)=>{
      card.querySelectorAll('.v3p4-heartbeat').forEach((node)=>node.outerHTML=heartbeatMarkup(id,world));
    });
    windows.get(id)?.querySelectorAll('.v3p4-heartbeat').forEach((node)=>node.outerHTML=heartbeatMarkup(id,world));
    injectQuickHeartbeat();
  }

  function toggle(card, side=null) {
    const id=text(card?.dataset?.worldId); if(!id)return;
    const next=side || ((cardSides.get(card)||'front')==='front'?'back':'front');
    cardSides.set(card,next);
    applySide(card,id);
  }

  function openRow(row) {
    const {id,world}=cardWorld(row); if(!id)return;
    document.querySelector(`[data-v3p4-row-open="${CSS.escape(id)}"]`)?.remove();
    const host=document.createElement('div'); host.className='v3p4-row-open'; host.dataset.v3p4RowOpen=id;
    host.innerHTML=`<article class="world-card v3p4-row-open-card" data-world-id="${esc(id)}" data-server-card="${row.dataset.serverCard||'0'}"><div class="v3p4-row-open-shell"><div><div class="eyebrow">Open Placard</div><h3>${esc(world?.name||world?.nickname||world?.identity?.world_name||row.querySelector('h3')?.textContent||'World')}</h3><p>${esc(world?.presentation?.description||world?.description||'World identity and joining details.')}</p></div><button class="btn ghost compact-btn" data-v3p4-close-row="${esc(id)}">Close</button></div></article>`;
    row.insertAdjacentElement('afterend',host); const card=host.querySelector('.world-card'); decorateCard(card); openRows.set(id,host);
  }

  function openWindow(id) {
    id=text(id); if(!id)return;
    const existing=windows.get(id) || document.querySelector(`.v3p4-window[data-v3p4-window="${CSS.escape(id)}"]`);
    if(existing){existing.classList.remove('minimized');existing.style.zIndex='10020';existing.querySelector('button')?.focus();return;}
    const world=findWorld(id)||{id,name:'World'}; const host=document.createElement('section'); host.className='v3p4-window'; host.dataset.v3p4Window=id; host.setAttribute('role','dialog'); host.setAttribute('aria-label',`${text(world.name||world.nickname||'World')} placard`);
    host.innerHTML=`<div class="v3p4-window-titlebar"><strong>${esc(world.name||world.nickname||world.identity?.world_name||'World Placard')}</strong><div><button class="btn ghost compact-btn" data-v3p4-min-window="${esc(id)}" aria-label="Minimize">—</button><button class="btn ghost compact-btn" data-v3p4-close-window="${esc(id)}" aria-label="Close">×</button></div></div><div class="v3p4-window-body"><article class="world-card" data-world-id="${esc(id)}" data-server-card="${world?.kind==='server'||world?.server?'1':'0'}"><div class="v3p4-window-summary"><div class="eyebrow">World Placard</div><h2>${esc(world.name||world.nickname||world.identity?.world_name||'World')}</h2><p>${esc(world.presentation?.description||world.description||'World identity and joining details.')}</p>${customBadgeMarkup(world)}${platformMarkup(world)}</div></article></div>`;
    document.getElementById('modal-root')?.appendChild(host) || document.body.appendChild(host); windows.set(id,host); decorateCard(host.querySelector('.world-card')); requestHeartbeat(id,host.querySelector('.world-card')?.dataset.serverCard==='1'?'dedicated':'local',true);
  }

  function augmentContextMenu(row) {
    const menu=document.querySelector('.world-context-menu'); if(!menu || menu.querySelector('[data-v3p4-open-menu]'))return;
    const id=text(row.dataset.worldId); const button=document.createElement('button'); button.className='context-menu-item'; button.dataset.v3p4OpenMenu=id; button.textContent='Open Placard'; menu.prepend(button);
  }

  function injectSettings() {
    if (document.querySelector('[data-v3p4-animation-settings]')) return;
    const anchor=document.querySelector('#save-performance-settings')?.closest('.settings-row'); if(!anchor)return;
    const row=document.createElement('div'); row.className='settings-row v3p4-animation-settings'; row.dataset.v3p4AnimationSettings='1'; const mode=animationMode();
    row.innerHTML=`<div class="settings-copy"><strong>Animations</strong><span>Controls placard flips, heartbeat motion, and other nonessential Phase 4 motion.</span></div><div class="v3p4-animation-picker">${['full','reduced','off'].map((value)=>`<button class="btn ${mode===value?'primary':'ghost'} compact-btn" data-v3p4-animation="${value}">${value[0].toUpperCase()+value.slice(1)}</button>`).join('')}</div>`;
    anchor.insertAdjacentElement('beforebegin',row);
  }

  async function saveAnimation(mode) {
    if(!['full','reduced','off'].includes(mode))return;
    const current=state(); current.application=current.application||{}; current.application.v3_phase4={...(current.application.v3_phase4||{}),animation_mode:mode};
    document.body.dataset.v3p4Animations=mode; decorateAll();
    try { const next=await api.invoke('application.update',{v3_phase4:{...(current.application.v3_phase4||{}),animation_mode:mode}}); if(next&&typeof next==='object')window.__DWSYNC_STATE__=next; }
    catch(_) {}
    document.querySelectorAll('[data-v3p4-animation]').forEach((button)=>{button.classList.toggle('primary',button.dataset.v3p4Animation===mode);button.classList.toggle('ghost',button.dataset.v3p4Animation!==mode);});
  }

  function injectQuickHeartbeat() {
    const query=new URLSearchParams(location.search); if(query.get('quick')!=='1'&&query.get('minimal')!=='1')return;
    const root=document.querySelector('.v3q-shell,.minimal-shell,#app'); if(!root)return;
    const id=text(query.get('worldId')||state()?.server?.active_world_id||state()?.client?.active_private_world_id); if(!id)return;
    let pill=root.querySelector('[data-v3p4-quick-heartbeat]'); if(!pill){pill=document.createElement('div');pill.dataset.v3p4QuickHeartbeat='1';pill.className='v3p4-quick-heartbeat';root.prepend(pill);}
    pill.innerHTML=heartbeatMarkup(id,findWorld(id)||{id}); requestHeartbeat(id,query.get('minimal')==='1'?'dedicated':'local');
  }

  document.addEventListener('click',(event)=>{
    const animation=event.target.closest('[data-v3p4-animation]'); if(animation){event.preventDefault();saveAnimation(animation.dataset.v3p4Animation);return;}
    const external=event.target.closest('[data-v3p4-external]'); if(external){event.preventDefault();event.stopPropagation();const url=external.dataset.v3p4External;if(/^https:\/\//i.test(url))api.openExternal?.(url);return;}
    const modFamily=event.target.closest('[data-v3p4-mod-family]');if(modFamily){event.preventDefault();event.stopPropagation();openModsPopup(modFamily.dataset.v3p4ModWorld,modFamily.dataset.v3p4ModFamily);return;}
    const closeMods=event.target.closest('[data-v3p4-close-mods]');if(closeMods){event.preventDefault();event.stopPropagation();closeModsPopup(closeMods.dataset.v3p4CloseMods);return;}
    const modBackdrop=event.target.closest('.v3p4-mod-dialog');if(modBackdrop&&event.target===modBackdrop){closeModsPopup(modBackdrop.dataset.v3p4ModDialog);return;}
    const toggleButton=event.target.closest('[data-v3p4-toggle]'); if(toggleButton){event.preventDefault();event.stopPropagation();const card=toggleButton.closest('.v3p4-placard');toggle(card);return;}
    const surface=event.target.closest('.world-card-inner,.v3p4-inner');
    const surfaceCard=surface?.closest('.v3p4-placard[data-world-id]');
    const interactive=event.target.closest('button,a,input,select,textarea,label,[role="button"],.v3p4-back-scroll');
    if(surfaceCard&&(!interactive||interactive===surfaceCard)){
      if(String(window.getSelection?.()||'').trim())return;
      event.preventDefault();event.stopPropagation();toggle(surfaceCard);return;
    }
    const openMenu=event.target.closest('[data-v3p4-open-menu]'); if(openMenu){event.preventDefault();event.stopPropagation();const row=document.querySelector(`.world-list-row[data-world-id="${CSS.escape(openMenu.dataset.v3p4OpenMenu)}"]`);document.querySelector('.world-context-menu')?.remove();if(row)openRow(row);return;}
    const closeRow=event.target.closest('[data-v3p4-close-row]'); if(closeRow){event.preventDefault();event.stopPropagation();document.querySelector(`[data-v3p4-row-open="${CSS.escape(closeRow.dataset.v3p4CloseRow)}"]`)?.remove();return;}
    const closeWindow=event.target.closest('[data-v3p4-close-window]'); if(closeWindow){const id=closeWindow.dataset.v3p4CloseWindow;windows.get(id)?.remove();windows.delete(id);return;}
    const minWindow=event.target.closest('[data-v3p4-min-window]'); if(minWindow){windows.get(minWindow.dataset.v3p4MinWindow)?.classList.toggle('minimized');return;}
  }, true);

  document.addEventListener('keydown',(event)=>{
    if(event.key==='Escape'&&modDialogs.size){[...modDialogs.keys()].forEach(closeModsPopup);return;}
    if((event.key==='Enter'||event.key===' ')&&event.target.matches('.v3p4-placard[data-world-id]')){
      event.preventDefault();event.stopPropagation();toggle(event.target);
    }
  });

  document.addEventListener('contextmenu',(event)=>{
    const row=event.target.closest('.world-list-row[data-world-id]'); if(!row)return; setTimeout(()=>augmentContextMenu(row),0);
  });

  document.addEventListener('dblclick',(event)=>{
    const card=event.target.closest('.v3p4-placard[data-world-id]'); if(card && !event.target.closest('button,a,input,select,textarea'))openWindow(card.dataset.worldId);
  });

  window.addEventListener('dragonwilds:state-updated',()=>requestAnimationFrame(decorateAll));
  new MutationObserver(()=>requestAnimationFrame(decorateAll)).observe(document.documentElement,{childList:true,subtree:true});

  function refreshHeartbeats() {
    document.querySelectorAll('[data-world-id]').forEach((node)=>{const id=text(node.dataset.worldId);if(id)requestHeartbeat(id,node.dataset.serverCard==='1'?'dedicated':'local',true);});
  }
  heartbeatTimer=setInterval(refreshHeartbeats,30000);
  window.addEventListener('beforeunload',()=>clearInterval(heartbeatTimer),{once:true});
  window.__DWSYNC_V3_PHASE4__={openPlacard:openWindow,closeModPopup:closeModsPopup,togglePlacard:(id)=>{const card=document.querySelector(`.v3p4-placard[data-world-id="${CSS.escape(text(id))}"]`);if(card)toggle(card);},animationMode};
  requestAnimationFrame(decorateAll);
})();
