(() => {
  'use strict';
  const api = window.dragonwilds;
  if (!api?.invoke) return;
  const text = (v) => String(v ?? '').trim();
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = () => window.__DWSYNC_STATE__ && typeof window.__DWSYNC_STATE__ === 'object' ? window.__DWSYNC_STATE__ : {};
  const contract = () => state()?.application?.v3_phase4?.contract || {};
  const platformRows = () => Array.isArray(contract()?.platform_registry?.items) ? contract().platform_registry.items : [];
  const iconToId = {steam:'steam',epicgames:'epic',xbox:'xbox',playstation:'playstation',windows:'windows',nintendo:'nintendo-switch-2',linux:'linux'};
  const managers = new Map();
  const badgeCache = new Map();

  function platformIdFromNode(node) {
    const src = text(node.querySelector('img')?.getAttribute('src'));
    const match = src.match(/\/([^/]+)\.svg(?:\?|$)/i);
    return match ? iconToId[match[1].toLowerCase()] || '' : '';
  }

  function enablePlatformLinks(root=document) {
    root.querySelectorAll('.v3p4-platform:not([data-v3p4-platform-ready])').forEach(node => {
      const id = platformIdFromNode(node); const row = platformRows().find(x => x && x.id === id);
      node.dataset.v3p4PlatformReady = '1';
      if (!row) return;
      const url = text(row.directSupportUrl || row.fallbackInfoUrl);
      node.title = row.verified ? `${row.displayName} · Official store/details` : `${row.displayName} · Platform information`;
      if (!/^https:\/\//i.test(url)) return;
      node.classList.add('v3p4-platform-link'); node.tabIndex = 0; node.setAttribute('role','link'); node.dataset.v3p4PlatformUrl = url;
    });
  }

  async function normalizePng(file) {
    if (!file || file.type !== 'image/png') throw new Error('Custom badge icons must be PNG files.');
    const source = await new Promise((resolve,reject) => { const reader = new FileReader(); reader.onload=()=>resolve(String(reader.result||'')); reader.onerror=()=>reject(new Error('Could not read badge PNG.')); reader.readAsDataURL(file); });
    const image = await new Promise((resolve,reject) => { const img=new Image(); img.onload=()=>resolve(img); img.onerror=()=>reject(new Error('Badge PNG could not be decoded.')); img.src=source; });
    if (image.naturalWidth <= 256 && image.naturalHeight <= 256 && file.size <= 512*1024) return source;
    const scale = Math.min(1, 256/image.naturalWidth, 256/image.naturalHeight); const width=Math.max(1,Math.round(image.naturalWidth*scale)); const height=Math.max(1,Math.round(image.naturalHeight*scale));
    const canvas=document.createElement('canvas'); canvas.width=width; canvas.height=height; const ctx=canvas.getContext('2d',{alpha:true}); ctx.drawImage(image,0,0,width,height);
    const out=canvas.toDataURL('image/png'); if (out.length > 800000) throw new Error('Badge PNG remains too large after normalization.'); return out;
  }

  function managerMarkup(profileId, rows) {
    return `<section class="v3p4-badge-manager" data-v3p4-manager="${esc(profileId)}">
      <header><div><div class="eyebrow">Phase 4</div><h2>Custom Badge Manager</h2><p>PNG only · normalized to 256×256 · routine heartbeats publish only the badge ID/hash reference.</p></div><button class="btn ghost compact-btn" data-v3p4-manager-close>×</button></header>
      <div class="v3p4-manager-body"><aside><button class="btn primary" data-v3p4-badge-new>Add Badge</button><div class="v3p4-manager-list">${rows.map((row,index)=>`<button class="v3p4-manager-item ${index===0?'active':''}" data-v3p4-badge-id="${esc(row.id)}"><span>${esc(row.name||row.label)}</span><small>${row.enabled===false?'Disabled':'Enabled'}</small></button>`).join('')}</div></aside><main data-v3p4-editor></main></div>
    </section>`;
  }

  function editorMarkup(row={}, preview='') {
    const isNew=!row.id; const image=preview || row.preview_data || '';
    return `<div class="v3p4-badge-editor" data-badge-id="${esc(row.id||'')}">
      <div class="v3p4-badge-preview">${image?`<img src="${esc(image)}" alt="Badge preview">`:'<span>◆</span>'}</div>
      <label>Name<input data-field="name" maxlength="80" value="${esc(row.name||row.label||'')}"></label>
      <label>Tooltip<input data-field="tooltip" maxlength="240" value="${esc(row.tooltip||'')}" placeholder="Defaults to badge name"></label>
      <label>Optional HTTPS link<input data-field="link" maxlength="1000" value="${esc(row.link||'')}"></label>
      <label class="v3p4-file-label">PNG Icon<input type="file" accept="image/png,.png" data-field="icon"></label>
      <label class="v3p4-check"><input type="checkbox" data-field="enabled" ${row.enabled===false?'':'checked'}> Enabled</label>
      <div class="v3p4-editor-actions"><button class="btn primary" data-v3p4-badge-save>${isNew?'Add':'Save'}</button>${isNew?'':`<button class="btn ghost" data-v3p4-badge-toggle>${row.enabled===false?'Enable':'Disable'}</button><button class="btn ghost" data-v3p4-badge-up>Move Up</button><button class="btn ghost" data-v3p4-badge-down>Move Down</button><button class="btn danger" data-v3p4-badge-remove>Remove</button>`}</div>
      <p class="muted" data-v3p4-manager-status>${row.asset_hash?`Asset ${esc(row.asset_hash.slice(0,12))}…`:''}</p>
    </div>`;
  }

  async function loadManager(profileId) {
    const result = await api.invoke('v3.phase4.badges.list',{id:profileId}); const rows=Array.isArray(result?.badges)?result.badges:[]; badgeCache.set(profileId, rows);
    let host=managers.get(profileId); if(host?.isConnected){host.classList.remove('hidden');host._rows=rows;selectBadge(host,rows[0]?.id||'');return;}
    host=document.createElement('div'); host.className='v3p4-manager-overlay'; host.innerHTML=managerMarkup(profileId,rows); document.getElementById('modal-root')?.appendChild(host)||document.body.appendChild(host); managers.set(profileId,host); host._rows=rows;
    selectBadge(host, rows[0]?.id || '');
  }

  function selectBadge(host,id) {
    const row=(host._rows||[]).find(x=>x.id===id)||{}; host.querySelectorAll('.v3p4-manager-item').forEach(x=>x.classList.toggle('active',x.dataset.v3p4BadgeId===id)); host.querySelector('[data-v3p4-editor]').innerHTML=editorMarkup(row,row.preview_data||'');
  }

  async function refreshManager(host, preferred='') {
    const id=host.querySelector('.v3p4-badge-manager')?.dataset.v3p4Manager; const result=await api.invoke('v3.phase4.badges.list',{id}); host._rows=Array.isArray(result?.badges)?result.badges:[]; badgeCache.set(id,host._rows);
    const list=host.querySelector('.v3p4-manager-list'); list.innerHTML=host._rows.map(row=>`<button class="v3p4-manager-item" data-v3p4-badge-id="${esc(row.id)}"><span>${esc(row.name||row.label)}</span><small>${row.enabled===false?'Disabled':'Enabled'}</small></button>`).join(''); selectBadge(host, preferred || host._rows[0]?.id || ''); hydrateHostedBadgeIcons(id,true);
  }

  async function hydratedRows(profileId) {
    if (badgeCache.has(profileId)) return badgeCache.get(profileId);
    try { const result=await api.invoke('v3.phase4.badges.list',{id:profileId}); const rows=Array.isArray(result?.badges)?result.badges:[]; badgeCache.set(profileId,rows); return rows; }
    catch (_) { return []; }
  }

  async function hydrateHostedBadgeIcons(profileId, force=false) {
    const cards=[...document.querySelectorAll(`.v3p4-placard[data-server-card="1"][data-world-id="${CSS.escape(profileId)}"]`)];
    if(!cards.length)return;
    if(!force && cards.every(card=>card.dataset.v3p4BadgesHydrated==='1'))return;
    const rows=await hydratedRows(profileId);
    for(const card of cards){
      card.querySelectorAll('.v3p4-custom-badge').forEach(node=>{
        const label=text(node.textContent); const row=rows.find(x=>x.enabled!==false && text(x.name||x.label)===label && x.preview_data);
        if(!row)return; const fallback=node.querySelector('.v3p4-badge-fallback'); if(fallback)fallback.outerHTML=`<img src="${esc(row.preview_data)}" alt="">`;
      });
      card.dataset.v3p4BadgesHydrated='1';
    }
  }

  function injectBadgeButtons() {
    document.querySelectorAll('.v3p4-placard[data-server-card="1"]:not([data-v3p4-badge-button])').forEach(card=>{
      card.dataset.v3p4BadgeButton='1'; const controls=card.querySelector('.v3p4-front .v3p4-page-controls'); if(!controls)return; const btn=document.createElement('button'); btn.className='btn ghost compact-btn'; btn.dataset.v3p4ManageBadges=card.dataset.worldId||''; btn.textContent='Badges'; controls.insertBefore(btn,controls.lastElementChild); hydrateHostedBadgeIcons(card.dataset.worldId||'');
    });
  }

  async function saveEditor(host) {
    const manager=host.querySelector('.v3p4-badge-manager'); const profileId=manager.dataset.v3p4Manager; const editor=host.querySelector('.v3p4-badge-editor'); const badgeId=editor.dataset.badgeId; const status=editor.querySelector('[data-v3p4-manager-status]');
    const badge={name:text(editor.querySelector('[data-field="name"]')?.value),tooltip:text(editor.querySelector('[data-field="tooltip"]')?.value),link:text(editor.querySelector('[data-field="link"]')?.value),enabled:!!editor.querySelector('[data-field="enabled"]')?.checked};
    const file=editor.querySelector('[data-field="icon"]')?.files?.[0]; if(file){status.textContent='Normalizing PNG…'; badge.image_data=await normalizePng(file); editor.querySelector('.v3p4-badge-preview').innerHTML=`<img src="${esc(badge.image_data)}" alt="Badge preview">`;}
    if(!badge.name) throw new Error('Badge name is required.'); status.textContent='Saving…'; const method=badgeId?'v3.phase4.badges.update':'v3.phase4.badges.add'; const payload=badgeId?{id:profileId,badge_id:badgeId,badge}:{id:profileId,badge}; const result=await api.invoke(method,payload); const rows=Array.isArray(result?.badges)?result.badges:[]; host._rows=rows; badgeCache.set(profileId,rows); await refreshManager(host,badgeId||rows.at(-1)?.id||'');
  }

  async function move(host,dir) { const editor=host.querySelector('.v3p4-badge-editor'); const id=editor?.dataset.badgeId; const rows=[...(host._rows||[])]; const index=rows.findIndex(x=>x.id===id); const target=index+dir; if(index<0||target<0||target>=rows.length)return; [rows[index],rows[target]]=[rows[target],rows[index]]; const profileId=host.querySelector('.v3p4-badge-manager').dataset.v3p4Manager; await api.invoke('v3.phase4.badges.reorder',{id:profileId,ordered_ids:rows.map(x=>x.id)}); await refreshManager(host,id); }

  document.addEventListener('click', async (event) => {
    const platform=event.target.closest('[data-v3p4-platform-url]'); if(platform){event.preventDefault();event.stopPropagation();await api.openInAppBrowser(platform.dataset.v3p4PlatformUrl);return;}
    const manage=event.target.closest('[data-v3p4-manage-badges]'); if(manage){event.preventDefault();event.stopPropagation();try{await loadManager(manage.dataset.v3p4ManageBadges);}catch(e){console.error(e);}return;}
    const host=event.target.closest('.v3p4-manager-overlay'); if(!host)return;
    if(event.target.closest('[data-v3p4-manager-close]')){host.remove();managers.delete(host.querySelector('.v3p4-badge-manager')?.dataset.v3p4Manager);return;}
    const item=event.target.closest('[data-v3p4-badge-id]'); if(item){selectBadge(host,item.dataset.v3p4BadgeId);return;}
    if(event.target.closest('[data-v3p4-badge-new]')){selectBadge(host,'');return;}
    if(event.target.closest('[data-v3p4-badge-save]')){try{await saveEditor(host);}catch(e){const status=host.querySelector('[data-v3p4-manager-status]');if(status)status.textContent=String(e?.message||e);}return;}
    if(event.target.closest('[data-v3p4-badge-toggle]')){const editor=host.querySelector('.v3p4-badge-editor');const profileId=host.querySelector('.v3p4-badge-manager').dataset.v3p4Manager;const current=(host._rows||[]).find(x=>x.id===editor.dataset.badgeId);if(current){await api.invoke('v3.phase4.badges.toggle',{id:profileId,badge_id:current.id,enabled:current.enabled===false});await refreshManager(host,current.id);}return;}
    if(event.target.closest('[data-v3p4-badge-up]')){await move(host,-1);return;} if(event.target.closest('[data-v3p4-badge-down]')){await move(host,1);return;}
    if(event.target.closest('[data-v3p4-badge-remove]')){const editor=host.querySelector('.v3p4-badge-editor'); const id=editor.dataset.badgeId; const profileId=host.querySelector('.v3p4-badge-manager').dataset.v3p4Manager; if(id){await api.invoke('v3.phase4.badges.remove',{id:profileId,badge_id:id});await refreshManager(host);}return;}
  }, true);

  document.addEventListener('change', event=>{const file=event.target.closest('[data-field="icon"]'); if(!file?.files?.[0])return; const host=file.closest('.v3p4-manager-overlay'); normalizePng(file.files[0]).then(data=>{host.querySelector('.v3p4-badge-preview').innerHTML=`<img src="${esc(data)}" alt="Badge preview">`;}).catch(e=>{host.querySelector('[data-v3p4-manager-status]').textContent=String(e?.message||e);});});

  const observer=new MutationObserver(()=>{enablePlatformLinks();injectBadgeButtons();}); observer.observe(document.documentElement,{childList:true,subtree:true}); enablePlatformLinks(); injectBadgeButtons();
})();
