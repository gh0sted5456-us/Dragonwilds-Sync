(() => {
  'use strict';
  const api=window.dragonwilds;
  let cache=null, fetched=0, busy=false;
  const esc=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function appState(force=false){
    if(!force&&window.__DWSYNC_STATE__){cache=window.__DWSYNC_STATE__;fetched=Date.now();return cache}
    if(!api?.invoke)return cache||window.__DWSYNC_STATE__||{}
    if(!force&&cache&&Date.now()-fetched<3000)return cache
    try{cache=await api.invoke('state.get',{});fetched=Date.now()}catch(_){}
    return cache||window.__DWSYNC_STATE__||{}
  }
  // Phase 6 owns the single Community settings workspace. Integrations keeps
  // its own identity instead of being renamed into a second Community tab.
  function renameCommunity(){}
  function retireHeavyWindows(root=document){root.querySelectorAll('[id^="detach-"],[data-detach-route],[data-open-detached]').forEach(n=>n.classList.remove('rc2-retired'));root.querySelectorAll('button').forEach(n=>{if(/^open in window$/i.test((n.textContent||'').trim()))n.classList.remove('rc2-retired')})}
  function removeDefender(root=document){root.querySelectorAll('section,.settings-section,.identity-box,.detail-section').forEach(section=>{const text=(section.textContent||'').toLowerCase();if(text.includes('microsoft defender')||/^\s*(server|client) defender\b/.test(text))section.classList.add('rc2-retired')})}
  function singleGithubChangelog(root=document){root.querySelectorAll('.settings-section').forEach(section=>{if(section.id==='github-release-changelog')return;const h=[...section.querySelectorAll('h2,h3')].find(x=>/^changelog$/i.test((x.textContent||'').trim()));if(h)section.classList.add('rc2-retired')})}
  async function openRouter(event){event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();try{const r=await api.invoke('network.default_router',{});if(r?.url)await api.openExternal(r.url)}catch(e){alert(`Default router could not be opened: ${e.message||e}`)}}
  function fixRouter(root=document){root.querySelectorAll('[data-router-home],a[href*="unifi.ui.com"],button[data-open-external*="unifi.ui.com"]').forEach(node=>{node.textContent='Open Default Router Homepage';node.removeAttribute('data-open-external');node.removeAttribute('href');if(node.dataset.rc2Router!=='1'){node.dataset.rc2Router='1';node.addEventListener('click',openRouter,true)}})}
  function combineServerManagement(root=document){const settings=root.querySelector('[data-webhost-tab="settings"]');if(settings)settings.textContent='WebHost';root.querySelectorAll('[data-webhost-tab="remote"]').forEach(b=>{b.textContent='Server Management';b.classList.remove('rc2-retired')})}
  function allWorlds(s){return [...(s?.client?.worlds||[]),...(s?.client?.discovered_worlds||[]),...(s?.client?.directory_worlds||[]),...(s?.client?.private_worlds||[]),...(s?.server_profiles||[])]}
  async function annotateCommunities(root=document){const cards=[...root.querySelectorAll('[data-world-id]')].filter(c=>!c.dataset.rc2Communities);if(!cards.length)return;const s=await appState();const map=new Map(allWorlds(s).map(w=>[String(w.id||''),w]));cards.forEach(card=>{card.dataset.rc2Communities='1';const world=map.get(String(card.dataset.worldId||''));const sources=world?.public_discovery?.directory_sources||world?.directory_sources||[];if(!sources.length)return;const host=card.querySelector('.world-tag-row,.tag-groups,.world-badges,.world-list-tags,.world-copy')||card;const chips=document.createElement('span');chips.className='community-source-chips';chips.title='Community lists that shared this same verified World';chips.innerHTML=sources.slice(0,2).map(x=>`<span class="community-source-chip">${esc(x.name||'Community')}</span>`).join('')+(sources.length>2?`<span class="community-source-chip">+${sources.length-2}</span>`:'');host.appendChild(chips)})}
  async function renderCommunity(){return;}
  function smoothIcons(root=document){root.querySelectorAll('.platform-logo,.platforms img').forEach(img=>{img.style.filter='none';img.style.background='transparent';img.style.border='0';img.style.boxShadow='none'})}
  function enhance(){renameCommunity();retireHeavyWindows();removeDefender();singleGithubChangelog();fixRouter();combineServerManagement();smoothIcons();void renderCommunity();void annotateCommunities()}
  let scheduled=false;const schedule=()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;enhance()})};
  document.addEventListener('click',e=>{if(e.target.closest('[data-settings-tab],[data-route]')){cache=null;setTimeout(schedule,20)}},true);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
})();
