(() => {
  'use strict';

  const api = window.dragonwilds;
  if (!api?.invoke) return;

  const sides = new Map();
  const network = new Map();
  const openRows = new Map();
  const windows = new Map();
  let decorating = false;
  let heartbeatTimer = null;

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const text = (value) => String(value ?? '').trim();
  const asArray = (value) => Array.isArray(value) ? value : [];
  const state = () => (window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object') ? window.__DWSYNC_STATE__ : {};
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
    const sources = [world?.metadata_cache?.mods, world?.mods, world?.manifest?.mods, world?.world_manifest?.mods, world?.mod_requirements, world?.sync_config?.required_mods];
    const rows = [];
    for (const source of sources) {
      for (const raw of asArray(source)) {
        const row = typeof raw === 'string' ? {name:raw} : (raw && typeof raw === 'object' ? raw : null);
        if (!row) continue;
        const name = text(row.name || row.display_name || row.mod_name || row.id || row.key);
        if (!name || /^(dragoncore|dragonconnect)$/i.test(name.replace(/\s+/g,''))) continue;
        const rawType = text(row.type || row.kind || row.loader || row.mod_type).toLowerCase();
        const type = rawType.includes('rune') ? 'RuneSchema' : rawType.includes('pak') ? 'Pak' : 'UE4SS';
        const role = text(row.runtime_role || row.role || row.scope || 'BOTH').toUpperCase();
        rows.push({name, version:text(row.version || row.mod_version), type, role, required:row.required !== false});
      }
      if (rows.length) break;
    }
    const seen = new Set();
    return rows.filter((row)=>{const key=`${row.type}:${row.name}`.toLowerCase();if(seen.has(key))return false;seen.add(key);return true;}).slice(0,64);
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
      return `<section class="v3p4-back-section"><h4>${type}</h4><div class="v3p4-mod-list">${rows.map((row)=>`<div><strong>${esc(row.name)}</strong><span>${esc(row.version || 'Version not advertised')} · ${esc(row.role)} · ${row.required?'Required':'Optional'}</span></div>`).join('')}</div></section>`;
    }).join('');
  }

  function heartbeatInfo(id, world) {
    const cached = network.get(id)?.value;
    const advertised = text(world?.heartbeat?.state || world?.heartbeat_state || world?.network_state || world?.directory_state);
    const status = cached?.heartbeat || cached || {};
    const value = text(status.state || advertised || ((world?.status?.broadcasting || world?.status?.running) ? 'Connecting' : 'Disabled'));
    const stateName = ['active','connecting','partial','failed','disabled'].includes(value.toLowerCase()) ? value[0].toUpperCase()+value.slice(1).toLowerCase() : 'Disabled';
    return {state:stateName,lastSuccess:status.last_success_at || null,destinations:asArray(status.destinations)};
  }

  function heartbeatMarkup(id, world) {
    const info = heartbeatInfo(id, world);
    const cls = info.state.toLowerCase();
    const mode = animationMode();
    const animated = ['Active','Connecting','Partial'].includes(info.state) && mode !== 'off';
    const label = info.state === 'Partial' ? 'Heartbeat Partial' : `Heartbeat ${info.state}`;
    return `<span class="v3p4-heartbeat ${cls} ${animated?'animated':'static'}" role="status" aria-label="${esc(label)}"><span class="v3p4-heart-shape" aria-hidden="true">♥</span><span>${esc(label)}</span></span>`;
  }

  function backMarkup(id, world) {
    const rules = publicRules(world);
    const badges = customBadgeMarkup(world);
    const mods = modsMarkup(world);
    const compatibility = platformMarkup(world);
    const extra = text(world?.additional_information || world?.presentation?.additional_information || world?.region || world?.classification?.region);
    return `<div class="v3p4-back-scroll" tabindex="0" aria-label="World joining and community details">
      ${rules?`<section class="v3p4-back-section"><h4>Community Rules</h4><p>${esc(rules)}</p></section>`:''}
      ${badges?`<section class="v3p4-back-section"><h4>Community Badges</h4>${badges}</section>`:''}
      ${mods?`<section class="v3p4-back-section"><h4>Required Mods</h4>${mods}</section>`:''}
      ${compatibility?`<section class="v3p4-back-section"><h4>Compatibility</h4>${compatibility}</section>`:''}
      ${extra?`<section class="v3p4-back-section"><h4>Additional Information</h4><p>${esc(extra)}</p></section>`:''}
      ${(!rules&&!badges&&!mods&&!compatibility&&!extra)?'<div class="v3p4-empty">No additional joining requirements are published for this World.</div>':''}
    </div>
    <div class="v3p4-back-footer">${heartbeatMarkup(id,world)}<button class="btn ghost compact-btn" data-v3p4-toggle="${esc(id)}">← Front</button></div>`;
  }

  function applySide(card, id) {
    const side = sides.get(id) || 'front';
    card.dataset.v3p4Side = side;
    card.classList.toggle('v3p4-back-visible', side === 'back');
    card.setAttribute('aria-label', `${text(card.querySelector('h2,h3')?.textContent || 'World')} · ${side === 'back' ? 'details' : 'front'}`);
    const status = card.querySelector('[data-v3p4-page-status]');
    if (status) status.textContent = side === 'back' ? 'Page 2 / 2' : 'Page 1 / 2';
  }

  function decorateCard(card) {
    if (!card || card.dataset.v3p4Decorated === '1' || card.closest('.v3p4-window')) return;
    const {id,world} = cardWorld(card); if (!id) return;
    card.dataset.v3p4Decorated = '1'; card.classList.add('v3p4-placard'); card.tabIndex = card.tabIndex >= 0 ? card.tabIndex : 0;
    const original = document.createElement('div'); original.className = 'v3p4-face v3p4-front';
    while (card.firstChild) original.appendChild(card.firstChild);
    const identity = document.createElement('div'); identity.className='v3p4-front-live'; identity.innerHTML=`${heartbeatMarkup(id,world)}${platformMarkup(world)}`;
    original.appendChild(identity);
    const frontControls = document.createElement('div'); frontControls.className='v3p4-page-controls'; frontControls.innerHTML=`<span data-v3p4-page-status>Page 1 / 2</span><button class="btn ghost compact-btn" data-v3p4-toggle="${esc(id)}">Details →</button>`; original.appendChild(frontControls);
    const back = document.createElement('div'); back.className='v3p4-face v3p4-back'; back.innerHTML=backMarkup(id,world);
    const inner = document.createElement('div'); inner.className='v3p4-inner'; inner.append(original,back); card.appendChild(inner);
    applySide(card,id);
    requestHeartbeat(id, card.dataset.serverCard === '1' ? 'dedicated' : 'local');
  }

  function decorateAll() {
    if (decorating) return; decorating = true;
    try {
      document.body.dataset.v3p4Animations = animationMode();
      document.querySelectorAll('.world-card[data-world-id]:not([data-v3p4-decorated])').forEach(decorateCard);
      document.querySelectorAll('.v3p4-placard').forEach((card)=>applySide(card,text(card.dataset.worldId)));
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
    const next=side || ((sides.get(id)||'front')==='front'?'back':'front'); sides.set(id,next); applySide(card,id);
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
    const toggleButton=event.target.closest('[data-v3p4-toggle]'); if(toggleButton){event.preventDefault();event.stopPropagation();const card=toggleButton.closest('.v3p4-placard');toggle(card);return;}
    const openMenu=event.target.closest('[data-v3p4-open-menu]'); if(openMenu){event.preventDefault();event.stopPropagation();const row=document.querySelector(`.world-list-row[data-world-id="${CSS.escape(openMenu.dataset.v3p4OpenMenu)}"]`);document.querySelector('.world-context-menu')?.remove();if(row)openRow(row);return;}
    const closeRow=event.target.closest('[data-v3p4-close-row]'); if(closeRow){event.preventDefault();event.stopPropagation();document.querySelector(`[data-v3p4-row-open="${CSS.escape(closeRow.dataset.v3p4CloseRow)}"]`)?.remove();return;}
    const closeWindow=event.target.closest('[data-v3p4-close-window]'); if(closeWindow){const id=closeWindow.dataset.v3p4CloseWindow;windows.get(id)?.remove();windows.delete(id);return;}
    const minWindow=event.target.closest('[data-v3p4-min-window]'); if(minWindow){windows.get(minWindow.dataset.v3p4MinWindow)?.classList.toggle('minimized');return;}
    const card=event.target.closest('.v3p4-placard'); if(card && !event.target.closest('button,a,input,select,textarea,.v3p4-back-scroll')){toggle(card);}
  }, true);

  document.addEventListener('keydown',(event)=>{
    if(!['Enter',' '].includes(event.key))return; const card=event.target.closest('.v3p4-placard'); if(!card||event.target.closest('button,a,input,select,textarea'))return; event.preventDefault();toggle(card);
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
  window.__DWSYNC_V3_PHASE4__={openPlacard:openWindow,togglePlacard:(id)=>{const card=document.querySelector(`.v3p4-placard[data-world-id="${CSS.escape(text(id))}"]`);if(card)toggle(card);},animationMode};
  requestAnimationFrame(decorateAll);
})();
