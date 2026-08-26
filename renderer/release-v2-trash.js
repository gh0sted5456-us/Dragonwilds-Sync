(() => {
  'use strict';
  const bridge=window.dragonwilds;let opening=false,lastPayload=null,lastRead=0,page=1;
  let selected=new Set();
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const size=n=>{n=Number(n||0);if(n<1024)return `${n} B`;if(n<1024**2)return `${(n/1024).toFixed(1)} KiB`;if(n<1024**3)return `${(n/1024**2).toFixed(1)} MiB`;return `${(n/1024**3).toFixed(2)} GiB`;};
  const invoke=(method,params={})=>{if(!bridge?.invoke)throw Error('Backend bridge unavailable.');return bridge.invoke(method,params);};
  const kindLabel=kind=>({private_world:'Private World',server_world:'Server World',character:'Character'})[String(kind||'')]||String(kind||'Deleted item').replaceAll('_',' ');
  const signature=payload=>JSON.stringify([payload?.count||0,payload?.size||0,(payload?.entries||[])[0]?.deleted_at||0]);
  // A 10s front-end cache keeps the idle sticker from hammering the backend
  // every poll; opening the Trash always forces a fresh read underneath, but
  // the overlay itself paints instantly using whatever is cached first (see
  // openTrash below) so the fresh read never blocks the click.
  async function read(force=false){if(!force&&lastPayload&&Date.now()-lastRead<10000)return lastPayload;lastPayload=await invoke('application.trash.list',{});lastRead=Date.now();return lastPayload;}
  function sticker(payload){
    let node=document.querySelector('#dws-trash-sticker');if(!node){node=document.createElement('aside');node.id='dws-trash-sticker';node.innerHTML='<button class="dws-trash-sticker-open" title="Open Trash" aria-label="Open Trash"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m-9 0 1 13h10l1-13M10 11v5m4-5v5"/></svg><small></small></button><button class="dws-trash-sticker-dismiss" title="Dismiss Trash icon" aria-label="Dismiss Trash icon">×</button>';document.body.appendChild(node);node.querySelector('.dws-trash-sticker-open').onclick=()=>openTrash();node.querySelector('.dws-trash-sticker-dismiss').onclick=()=>{localStorage.setItem('dws-trash-dismissed',signature(lastPayload));node.hidden=true;};}
    const count=Number(payload?.count||0);node.querySelector('small').textContent=count?String(count):'';node.classList.toggle('has-items',count>0);node.hidden=localStorage.getItem('dws-trash-dismissed')===signature(payload);
  }
  async function refresh(force=false){try{sticker(await read(force));}catch(_){/* Keep background status unobtrusive. */}}

  function rowsHtml(shown){
    if(!shown.length)return '<div class="empty-state">Trash is empty.</div>';
    return shown.map(entry=>`<article class="dws-trash-entry"><label class="dws-trash-select-row" title="Select"><input type="checkbox" data-trash-select="${esc(entry.id)}" ${selected.has(String(entry.id))?'checked':''}/></label><div><strong>${esc(entry.display_name||'Deleted item')}</strong><small>${entry.deleted_at?new Date(Number(entry.deleted_at)*1000).toLocaleString():'Deleted'} · ${size(entry.size)} · ${Number(entry.files||0)} files</small><span class="dws-trash-kind">${esc(kindLabel(entry.kind))}</span></div><div class="header-actions"><button class="btn primary compact-btn" data-trash-restore="${esc(entry.id)}">Restore</button><button class="btn danger compact-btn" data-trash-empty="${esc(entry.id)}">Delete Permanently</button></div></article>`).join('');
  }

  function shell(seedPayload){
    const overlay=document.createElement('section');overlay.className='dws-trash-overlay';overlay.id='dws-trash-overlay';
    const settings=seedPayload?.settings||{};
    overlay.innerHTML=`<div class="dws-trash-card"><div class="dws-trash-head"><div><div class="eyebrow">Recoverable deletion</div><h2>Trash</h2><p>Restore verified Worlds and Characters, or permanently delete their Trash copy.</p></div><button class="btn ghost" data-trash-close>×</button></div><div class="dws-trash-policy"><label><span>Automatically empty</span><select class="select" id="dws-trash-retention">${[0,7,14,30,60,90,180,365].map(days=>`<option value="${days}" ${Number(settings.auto_empty_days||0)===days?'selected':''}>${days?`After ${days} days`:'Never'}</option>`).join('')}</select></label><span data-trash-meta>Loading…</span></div><div class="dws-trash-select-all-row"><label><input type="checkbox" id="dws-trash-select-all"/> <span>Select page</span></label><div class="header-actions"><button class="btn ghost compact-btn" id="dws-trash-restore-selected" disabled>Restore Selected (0)</button><button class="btn danger compact-btn" id="dws-trash-empty-selected" disabled>Empty Selected (0)</button></div></div><div class="dws-trash-list"><div class="dws-trash-skeleton">Loading Trash…</div></div><div class="dws-trash-footer"><div class="pager-row"><button class="btn ghost compact-btn" data-trash-page-prev disabled>Previous</button><span data-trash-pager-label>Page 1 of 1</span><button class="btn ghost compact-btn" data-trash-page-next disabled>Next</button></div><div class="header-actions"><button class="btn danger" id="dws-trash-empty-all" disabled>Empty Trash</button><button class="btn ghost" data-trash-close>Done</button></div></div></div>`;
    return overlay;
  }

  function paintSelectionControls(overlay){
    const restoreBtn=overlay.querySelector('#dws-trash-restore-selected'),emptyBtn=overlay.querySelector('#dws-trash-empty-selected');
    if(restoreBtn){restoreBtn.disabled=selected.size===0;restoreBtn.textContent=`Restore Selected (${selected.size})`;}
    if(emptyBtn){emptyBtn.disabled=selected.size===0;emptyBtn.textContent=`Empty Selected (${selected.size})`;}
    const shownIds=[...overlay.querySelectorAll('[data-trash-select]')].map(node=>node.dataset.trashSelect);
    const selectAll=overlay.querySelector('#dws-trash-select-all');
    if(selectAll){const allSelected=shownIds.length>0&&shownIds.every(id=>selected.has(id));selectAll.checked=allSelected;selectAll.indeterminate=!allSelected&&shownIds.some(id=>selected.has(id));}
  }

  function acceptMutation(response){
    if(!response?.trash)return;
    lastPayload={...response.trash,settings:lastPayload?.settings||response.settings||{}};
    lastRead=Date.now();
  }

  function wireRowHandlers(overlay){
    overlay.querySelectorAll('[data-trash-select]').forEach(node=>node.onchange=()=>{const id=node.dataset.trashSelect;if(node.checked)selected.add(id);else selected.delete(id);paintSelectionControls(overlay);});
    overlay.querySelectorAll('[data-trash-restore]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{const response=await invoke('application.trash.restore',{entry_id:button.dataset.trashRestore});acceptMutation(response);selected.delete(button.dataset.trashRestore);await paintBody(overlay,false);}catch(error){button.disabled=false;alert(error.message||error);}});
    overlay.querySelectorAll('[data-trash-empty]').forEach(button=>button.onclick=async()=>{if(!confirm('Permanently delete this Trash copy? This cannot be undone.'))return;button.disabled=true;try{const response=await invoke('application.trash.empty',{entry_id:button.dataset.trashEmpty});acceptMutation(response);selected.delete(button.dataset.trashEmpty);await paintBody(overlay,false);}catch(error){button.disabled=false;alert(error.message||error);}});
  }

  // Re-renders only the list body, page controls, and selection state --
  // never tears down and rebuilds the overlay card itself. Doing a full
  // overlay.remove()+recreate on every click (the old behavior) is what made
  // Trash feel like it was glitching open/closed on every restore, delete,
  // or page change.
  async function paintBody(overlay,force=true){
    if(!overlay?.isConnected)return;
    try{
      const payload=await read(force);
      const entries=payload.entries||[];
      selected=new Set([...selected].filter(id=>entries.some(entry=>String(entry.id)===id)));
      const pages=Math.max(1,Math.ceil(entries.length/25));
      page=Math.min(page,pages);
      const shown=entries.slice((page-1)*25,page*25);
      const body=overlay.querySelector('.dws-trash-list');if(body)body.innerHTML=rowsHtml(shown);
      const meta=overlay.querySelector('[data-trash-meta]');if(meta)meta.textContent=`${entries.length} item${entries.length===1?'':'s'} · ${size(payload.size)}`;
      const pagerLabel=overlay.querySelector('[data-trash-pager-label]');if(pagerLabel)pagerLabel.textContent=`Page ${page} of ${pages}`;
      const prev=overlay.querySelector('[data-trash-page-prev]');if(prev)prev.disabled=page<=1;
      const next=overlay.querySelector('[data-trash-page-next]');if(next)next.disabled=page>=pages;
      const emptyAll=overlay.querySelector('#dws-trash-empty-all');if(emptyAll)emptyAll.disabled=!entries.length;
      wireRowHandlers(overlay);
      paintSelectionControls(overlay);
      sticker(payload);
    }catch(error){
      const body=overlay.querySelector('.dws-trash-list');if(body)body.innerHTML=`<div class="warning-box">${esc(error.message||error)}</div>`;
    }
  }

  async function openTrash(){
    const existing=document.querySelector('#dws-trash-overlay');
    if(existing){window.__DWSYNC_DESKTOP_WINDOWS__?.focus?.(existing);return void paintBody(existing);}
    if(opening)return;opening=true;
    // Build and mount the overlay with cached (or empty) content immediately
    // -- the click feels instant -- then fill in a fresh read in the
    // background instead of blocking the open on network/disk latency.
    const shellNode=shell(lastPayload);const desktop=window.__DWSYNC_DESKTOP_WINDOWS__;
    const overlay=desktop?.openNative?desktop.openNative(shellNode.innerHTML,{title:'Trash',width:980,height:820}):shellNode;
    if(!desktop?.openNative)document.body.appendChild(overlay);
    if(desktop?.openNative)overlay.classList.add('dws-trash-native-window');
    overlay.id='dws-trash-overlay';overlay._dwsOnNativeClosed=()=>{opening=false;void refresh(false);};
    const close=()=>{opening=false;if(desktop?.close)desktop.close(overlay);else overlay.remove();void refresh(false);};
    overlay.querySelectorAll('[data-trash-close]').forEach(button=>button.onclick=close);
    if(!desktop?.openNative)overlay.onclick=e=>{if(e.target===overlay)close();};
    overlay.querySelector('#dws-trash-retention').onchange=async e=>{await invoke('application.trash.settings',{auto_empty_days:Number(e.target.value||0)});lastRead=0;};
    overlay.querySelector('#dws-trash-select-all').onchange=e=>{const shownIds=[...overlay.querySelectorAll('[data-trash-select]')].map(node=>node.dataset.trashSelect);if(e.target.checked)shownIds.forEach(id=>selected.add(id));else shownIds.forEach(id=>selected.delete(id));overlay.querySelectorAll('[data-trash-select]').forEach(node=>{node.checked=selected.has(node.dataset.trashSelect);});paintSelectionControls(overlay);};
    overlay.querySelector('[data-trash-page-prev]').onclick=()=>{page=Math.max(1,page-1);void paintBody(overlay,false);};
    overlay.querySelector('[data-trash-page-next]').onclick=()=>{page=page+1;void paintBody(overlay,false);};
    overlay.querySelector('#dws-trash-empty-all').onclick=async()=>{if(!confirm('Permanently empty all Dragonwilds Sync Trash? This cannot be undone.'))return;const button=overlay.querySelector('#dws-trash-empty-all');button.disabled=true;try{selected=new Set();const response=await invoke('application.trash.empty',{});acceptMutation(response);page=1;await paintBody(overlay,false);}catch(error){button.disabled=false;alert(error.message||error);}};
    overlay.querySelector('#dws-trash-restore-selected').onclick=async()=>{const ids=[...selected];if(!ids.length||!confirm(`Restore ${ids.length} selected item${ids.length===1?'':'s'}?`))return;const button=overlay.querySelector('#dws-trash-restore-selected');button.disabled=true;try{const response=await invoke('application.trash.restore',{entry_ids:ids});acceptMutation(response);selected=new Set((response.failed||[]).map(row=>String(row.entry_id||'')));await paintBody(overlay,false);if(response.failed?.length)alert(`Restored ${Number(response.restored_count||0)} item(s); ${response.failed.length} could not be restored (likely a conflicting file already exists).`);}catch(error){button.disabled=false;alert(error.message||error);}};
    overlay.querySelector('#dws-trash-empty-selected').onclick=async()=>{const ids=[...selected];if(!ids.length||!confirm(`Permanently delete ${ids.length} selected item${ids.length===1?'':'s'}? This cannot be undone.`))return;const button=overlay.querySelector('#dws-trash-empty-selected');button.disabled=true;try{const response=await invoke('application.trash.empty',{entry_ids:ids});acceptMutation(response);selected=new Set();await paintBody(overlay,false);}catch(error){button.disabled=false;alert(error.message||error);}};
    opening=false;
    void paintBody(overlay);
  }

  // The persistent System navigation invokes the same authoritative Trash
  // surface as the dismissible corner icon; there is no duplicate Trash UI.
  window.__DWSYNC_OPEN_TRASH__=()=>openTrash();

  const boot=()=>{void refresh(true);setInterval(()=>void refresh(false),30000);};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
