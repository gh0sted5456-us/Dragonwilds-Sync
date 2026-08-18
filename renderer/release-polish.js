(() => {
  'use strict';

  const api = window.dragonwilds;
  const CHANGELOG_URL = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/codex/webgui-catalog-console-overhaul/docs/changelog.json';
  let cachedState = null;
  let stateFetchedAt = 0;
  let modMode = 'private';

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const initials = (value) => String(value || 'Player').trim().split(/\s+/).slice(0,2).map((part)=>part[0]||'').join('').toUpperCase() || 'P';

  async function currentState(force = false) {
    if (!api?.invoke) return cachedState || {};
    if (!force && cachedState && Date.now() - stateFetchedAt < 5000) return cachedState;
    try { cachedState = await api.invoke('state.get', {}); stateFetchedAt = Date.now(); } catch (_) {}
    return cachedState || {};
  }

  function countryFlag(code) {
    const cc = String(code || '').trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(cc)) return '🌐';
    return String.fromCodePoint(...[...cc].map((char)=>127397 + char.charCodeAt(0)));
  }

  function theme() {
    const root = document.documentElement;
    return root.dataset.theme || document.body.dataset.theme || 'dark';
  }

  async function showReviews(worldId, title = 'World') {
    if (!worldId || !api?.invoke || !api?.openManagedDialog) return;
    let rows = [], summary = {};
    try {
      const response = await api.invoke('world.feedback.list', { id: worldId, days: 90 });
      rows = response?.reviews || [];
      summary = response || {};
    } catch (error) {
      await api.openManagedDialog({ title:`${title} · Reviews`, width:760, height:480, theme:theme(), html:`<div class="modal-header"><div><h2>Reviews unavailable</h2><p>${esc(error.message)}</p></div></div>` });
      return;
    }
    const cards = rows.length ? rows.map((row) => {
      const name = row.profile_name || row.reviewer_name || row.client_id || 'Player';
      const avatar = row.profile_avatar || row.avatar_data || '';
      const country = row.country_name || row.country || '';
      const code = row.country_code || '';
      return `<article class="public-review-card"><div class="review-profile">${avatar?`<img src="${esc(avatar)}" alt=""/>`:`<span>${esc(initials(name))}</span>`}<div><strong>${esc(name)}</strong><small>${countryFlag(code)} ${esc(country || 'Country not shared')}</small></div><b>${'★'.repeat(Number(row.rating||0))}${'☆'.repeat(Math.max(0,5-Number(row.rating||0)))}</b></div><p>${esc(row.report || 'No written review.')}</p><small>${row.received_at?new Date(Number(row.received_at)*1000).toLocaleString():''}${row.integrity?' · verified':''}</small></article>`;
    }).join('') : '<div class="empty-state">No visible reviews have been submitted yet.</div>';
    const css = `<style>body{margin:0;background:#0b0f10;color:#eee7d6;font:14px/1.45 Segoe UI,sans-serif}.review-shell{padding:20px}.review-head{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid #39413e;padding-bottom:12px;margin-bottom:14px}.review-head h2{font:700 25px Georgia,serif;margin:0}.review-head span{color:#c7aa56}.public-review-list{display:grid;gap:10px}.public-review-card{border:1px solid #34403d;background:#111817;border-radius:14px;padding:14px}.review-profile{display:grid;grid-template-columns:42px 1fr auto;gap:10px;align-items:center}.review-profile>img,.review-profile>span{width:40px;height:40px;border-radius:10px;object-fit:cover;background:#25302d;display:grid;place-items:center;color:#e3c66c;font-weight:800}.review-profile small,.public-review-card>small{color:#92a09b}.review-profile b{color:#e3c66c;letter-spacing:2px}.public-review-card p{margin:10px 0}.empty-state{padding:30px;text-align:center;color:#92a09b}</style>`;
    await api.openManagedDialog({ title:`${title} · Reviews`, width:820, height:680, theme:theme(), html:`${css}<div class="review-shell"><div class="review-head"><div><h2>${esc(title)} Reviews</h2><small>Verified World feedback · last 90 days</small></div><span>${Number(summary.rating_average||0).toFixed(1)} / 5 · ${Number(summary.rating_count||rows.length)} review${Number(summary.rating_count||rows.length)===1?'':'s'}</span></div><div class="public-review-list">${cards}</div></div>` });
  }

  function enhanceRatings(root = document) {
    root.querySelectorAll('.world-rating:not([data-release-rating])').forEach((rating) => {
      rating.dataset.releaseRating = '1'; rating.setAttribute('role','button'); rating.setAttribute('tabindex','0'); rating.style.cursor='pointer';
      const open = (event) => {
        event.preventDefault(); event.stopPropagation();
        const card = rating.closest('[data-world-id]');
        const id = card?.dataset.worldId || '';
        const title = card?.querySelector('h2,h3,.world-card-title,.world-list-title')?.textContent?.trim() || 'World';
        showReviews(id,title);
      };
      rating.addEventListener('click', open); rating.addEventListener('keydown',(event)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open(event);}});
    });
  }

  async function renderModProfileLists(host) {
    const state = await currentState();
    if (!host?.isConnected) return;
    const privateWorlds = state?.client?.private_worlds || (state?.client?.singleplayer ? [state.client.singleplayer] : []);
    const servers = state?.server_profiles || [];
    const rows = modMode === 'server' ? servers : privateWorlds;
    host.querySelectorAll('[data-release-mod-mode]').forEach((button)=>button.classList.toggle('active',button.dataset.releaseModMode===modMode));
    const list = host.querySelector('[data-release-mod-list]');
    if (!list) return;
    list.innerHTML = rows.length ? rows.map((world)=>{
      const name=world.name||world.world_name||'World';
      const meta=world.metadata_cache||{}; const mods=meta.mods||[];
      const detail=modMode==='server'?'Dedicated Server':'Private World / Co-Op';
      return `<article class="release-mod-world"><div><strong>${esc(name)}</strong><small>${esc(detail)} · ${mods.length} cached mod${mods.length===1?'':'s'}</small></div><button class="btn primary compact-btn" data-release-open-mods="${esc(world.id||'')}" data-release-open-kind="${modMode}">Open Mod Manager</button></article>`;
    }).join('') : `<div class="empty-state">No ${modMode==='server'?'dedicated Server':'Private World / Co-Op'} profiles are configured.</div>`;
    list.querySelectorAll('[data-release-open-mods]').forEach((button)=>button.addEventListener('click',()=>{
      const id=button.dataset.releaseOpenMods||''; const kind=button.dataset.releaseOpenKind;
      if(kind==='server') api.openDetachedWindow?.({route:'server-detail',title:'Dragonwilds Sync · Server Mods',context:{selectedServerWorldId:id,serverTab:'mods'},width:1240,height:820});
      else api.openDetachedWindow?.({route:'world-detail',title:'Dragonwilds Sync · Private World Mods',context:{selectedWorldId:id,privateTab:'mods'},width:1240,height:820});
    }));
  }

  function enhanceModSettings(root = document) {
    const activeNav=[...root.querySelectorAll('.settings-nav button.active')].find((node)=>/mod management/i.test(node.textContent||''));
    if(!activeNav) return;
    const note=root.querySelector('.settings-page-note'); const page=note?.parentElement;
    if(!page || page.querySelector('#release-mod-management')) return;
    const host=document.createElement('section'); host.id='release-mod-management'; host.className='settings-section release-mod-management';
    host.innerHTML=`<div class="panel-header"><div><h2>Mod Management</h2><span class="panel-subtitle">Private/Co-Op and dedicated Server profiles are intentionally separate. Each opens its own profile-owned mod manager.</span></div></div><nav class="settings-subnav release-mod-tabs"><button class="active" data-release-mod-mode="private">Private World / Co-Op</button><button data-release-mod-mode="server">Server</button></nav><div class="release-mod-list" data-release-mod-list><div class="empty-state">Loading profiles…</div></div>`;
    note.insertAdjacentElement('afterend',host);
    [...page.children].forEach((child)=>{if(child!==note&&child!==host&&!child.classList.contains('settings-subnav')){child.dataset.releaseLegacyMods='1';child.style.display='none';}});
    host.querySelectorAll('[data-release-mod-mode]').forEach((button)=>button.addEventListener('click',()=>{modMode=button.dataset.releaseModMode==='server'?'server':'private';renderModProfileLists(host);}));
    renderModProfileLists(host);
  }

  async function enhanceChangelog(root = document) {
    const activeNav=[...root.querySelectorAll('.settings-nav button.active')].find((node)=>/about/i.test(node.textContent||''));
    if(!activeNav) return;
    const note=root.querySelector('.settings-page-note'); const page=note?.parentElement;
    if(!page || page.querySelector('#github-release-changelog')) return;
    const section=document.createElement('section'); section.id='github-release-changelog'; section.className='settings-section';
    section.innerHTML='<div class="panel-header"><div><h2>GitHub Changelog</h2><span class="panel-subtitle">Release notes update from GitHub without requiring a new launcher build.</span></div><button class="btn ghost compact-btn" data-open-changelog-page>Open Full Changelog</button></div><div data-changelog-body class="empty-state">Loading current release notes…</div>';
    page.appendChild(section);
    section.querySelector('[data-open-changelog-page]')?.addEventListener('click',()=>api.openInAppBrowser?.({url:'https://gh0sted5456-us.github.io/Dragonwilds-Sync/changelog.html',purpose:'docs'}));
    try {
      const response=await fetch(CHANGELOG_URL,{cache:'no-store'}); if(!response.ok)throw new Error(`HTTP ${response.status}`); const data=await response.json();
      const rows=data.releases||[]; const body=section.querySelector('[data-changelog-body]');
      body.className='release-changelog'; body.innerHTML=`<nav class="release-changelog-tabs">${rows.map((row,index)=>`<button class="btn ${index===0?'primary':'ghost'} compact-btn" data-change-index="${index}">${esc(row.version)}</button>`).join('')}</nav><div data-change-view></div>`;
      const show=(index)=>{const row=rows[index]||{};body.querySelectorAll('[data-change-index]').forEach((b,i)=>{b.classList.toggle('primary',i===index);b.classList.toggle('ghost',i!==index)});body.querySelector('[data-change-view]').innerHTML=`<div class="identity-box"><strong>${esc(row.version||'Version')} · ${esc(row.title||'')}</strong><p>${esc(row.date||'')} · ${esc(row.status||'release')}</p><ul>${(row.highlights||[]).map((item)=>`<li>${esc(item)}</li>`).join('')}</ul></div>`;};
      body.querySelectorAll('[data-change-index]').forEach((button)=>button.addEventListener('click',()=>show(Number(button.dataset.changeIndex||0)))); show(0);
    } catch (error) { section.querySelector('[data-changelog-body]').textContent=`Could not refresh GitHub changelog: ${error.message}`; }
  }

  function enhanceServerManagement(root = document) {
    if(!/server management|sync/i.test(root.querySelector('.page-header h1')?.textContent||'')) return;
    root.querySelectorAll('[data-webhost-tab]').forEach((button)=>{
      const key=button.dataset.webhostTab||'';
      if(key==='settings') button.textContent='Website & Networking';
      if(key==='remote') button.textContent='Remote Users & Permissions';
    });
    const add=root.querySelector('#add-webhost-user');
    if(add){add.textContent='+ Add Remote User';add.title='Create login credentials and assign World-scoped permissions';}
  }

  function enhance() {
    enhanceRatings(); enhanceModSettings(); enhanceChangelog(); enhanceServerManagement();
  }
  let pending=false;
  const schedule=()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;enhance();});};
  document.addEventListener('click',(event)=>{if(event.target.closest('[data-settings-tab]')){cachedState=null;setTimeout(schedule,30);}});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
})();
