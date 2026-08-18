from __future__ import annotations

"""Additive public WebGUI presentation layer.

The full, previously shipped WebGUI implementation is retained byte-for-byte in
``directory_web_legacy``.  This wrapper only decorates the public World browser
with the post-RC2 Declared/Horizontal/profile-badge parity requested by the
launcher UI, while every admin/detail/API surface continues to come from the
preserved implementation.
"""

from directory_web_legacy import *  # noqa: F401,F403
from directory_web_legacy import public_browser_html as _legacy_public_browser_html


_PUBLIC_BROWSER_EXTENSION = r'''
<style id="dws-public-vnext-style">
.title-line{flex-wrap:wrap}.title-line .badge,.title-line .community-sources{flex:0 0 auto}.world-copy{min-width:0}.world-copy .dws-profile-badges{display:flex;gap:5px;flex-wrap:wrap;margin:6px 0}.dws-profile-badge{display:inline-flex;align-items:center;padding:4px 7px;border:1px solid #51472d;border-radius:999px;color:var(--gold2);background:#18170f;font-size:9px;font-weight:850;letter-spacing:.05em;text-transform:uppercase}.view-toggle{display:inline-flex;gap:4px;padding:3px;border:1px solid var(--line2);border-radius:10px;background:#0c1011}.view-toggle button{min-height:34px;padding:6px 9px;background:transparent}.view-toggle button.active{border-color:var(--gold);background:#292419;color:var(--gold2)}.cards.horizontal{display:grid;grid-template-columns:1fr;gap:9px}.cards.horizontal .world-card{display:grid;grid-template-columns:110px minmax(0,1fr) auto;min-height:104px;overflow:hidden}.cards.horizontal .banner{height:100%;min-height:104px;border-radius:0}.cards.horizontal .world-body{display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:12px;padding:12px 14px}.cards.horizontal .world-icon{position:static;width:48px;height:48px;margin:0}.cards.horizontal .world-copy p{margin:3px 0 5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.cards.horizontal .world-copy .platforms,.cards.horizontal .tag-groups{margin-top:4px}.cards.horizontal .world-body dl{display:flex;gap:16px;align-items:center;margin:0}.cards.horizontal .world-card footer{border:0;border-left:1px solid var(--line2);display:grid;align-content:center;gap:7px;min-width:150px;padding:12px}.cards.horizontal .world-card footer span{font-size:10px}.cards.horizontal .world-card footer .button{white-space:nowrap}@media(max-width:900px){.cards.horizontal .world-card{grid-template-columns:82px minmax(0,1fr)}.cards.horizontal .world-card footer{grid-column:1/-1;border-left:0;border-top:1px solid var(--line2);display:flex;justify-content:space-between}.cards.horizontal .world-body{grid-template-columns:44px minmax(0,1fr)}.cards.horizontal .world-body dl{display:none}}
</style>
<script id="dws-public-vnext-script">
(() => {
  'use strict';
  let webView='cards', declaredCache=[];
  const originalCard=card, originalLoad=load;
  function profileBadgeValues(w){const values=[...(Array.isArray(w.badges)?w.badges:[]),...(Array.isArray(w.profile_badges)?w.profile_badges:[]),...(Array.isArray(w.mod_badges)?w.mod_badges:[])];return [...new Set(values.map(v=>String(typeof v==='object'?(v.label||v.name||v.title||v.id||''):v||'').trim()).filter(Boolean).map(v=>v.toUpperCase()))].slice(0,10)}
  function profileBadges(w){const values=profileBadgeValues(w);return values.length?`<div class="dws-profile-badges">${values.map(v=>`<span class="dws-profile-badge">${esc(v)}</span>`).join('')}</div>`:''}
  function horizontalCard(w){const sync=!!w.sync_ready,declared=!!(w.directory_verified&&w.fingerprint_claimed&&w.last_seen),players=Number(w.players||0),max=Number(w.max_players||0);return `<article class="world-card panel"><div class="banner"${w.banner_b64?` style="background-image:url('${esc(w.banner_b64)}')"`:''}><span class="source">${esc(w.source_label||'Dragonwilds')}</span></div><div class="world-body"><div class="world-icon">${w.icon_b64?`<img src="${esc(w.icon_b64)}" alt="">`:esc((w.world_name||'W')[0])}</div><div class="world-copy"><div class="title-line"><h2>${esc(w.world_name||'Unnamed World')}</h2>${identityBadges(w)}${communitySourceBadges(w)}${declared?'<span class="badge good">◆ Declared</span>':sync?'<span class="badge good">◆ Sync Ready</span>':'<span class="badge plain">Vanilla discovery</span>'}</div><p>${esc(w.description||'A discovered RuneScape: Dragonwilds World.')}</p>${profileBadges(w)}${platformBadges(w)}${tagGroups(w)}</div><dl><div><dt>Players</dt><dd>${players}${max?' / '+max:''}</dd></div><div><dt>Region</dt><dd>${flag(w.country_code)} ${esc(w.region||w.country_name||'Unknown')}</dd></div><div><dt>Ping</dt><dd>${w.ping_ms!=null?Math.round(w.ping_ms)+' ms':'—'}</dd></div></dl></div><footer><span>${w.password_required?'🔒 Password':'◇ Open'} · ${w.modded?'Modded':'Vanilla'}</span><a class="button ${sync?'primary':''}" href="/servers/${encodeURIComponent(w.id)}">Details</a></footer></article>`}
  card=function(w){if(webView==='horizontal')return horizontalCard(w);const html=originalCard(w);const badges=profileBadges(w);return badges?html.replace('</p>',`</p>${badges}`):html};
  async function allSyncPages(){const first=await fetch('/api/v1/worlds?active=sync&page=1&sort='+encodeURIComponent($('#sort').value),{cache:'no-store'}).then(r=>r.json());const payloads=[first],count=Math.max(1,Math.min(50,Number(first.page_count||1)));for(let p=2;p<=count;p++){const next=await fetch('/api/v1/worlds?active=sync&page='+p+'&sort='+encodeURIComponent($('#sort').value),{cache:'no-store'}).then(r=>r.json());payloads.push(next)}return payloads.flatMap(x=>x.worlds||[])}
  async function loadDeclared(){const currentSearch=$('#search').value.trim().toLowerCase(),region=$('#region').value,access=$('#access').value;let values=(await allSyncPages()).filter(w=>w.directory_verified&&w.fingerprint_claimed&&Number(w.last_seen||0)>0);if(currentSearch)values=values.filter(w=>JSON.stringify([w.world_name,w.description,w.region,w.country_name,w.tags,w.badges,w.mod_badges]).toLowerCase().includes(currentSearch));if(region)values=values.filter(w=>String(w.region||'')===region);if(access==='password')values=values.filter(w=>w.password_required);if(access==='open')values=values.filter(w=>!w.password_required);declaredCache=values;rows=values;total=values.length;page=1;pageCount=1;const count=$('#count-declared');if(count)count.textContent=String(values.length);$('#updated').textContent='Declared updated '+new Date().toLocaleTimeString();render()}
  load=async function(){return active==='declared'?loadDeclared():originalLoad()};
  const syncButton=document.querySelector('.quick[data-filter="sync"]');
  if(syncButton&&!document.querySelector('[data-filter="declared"]')){const button=document.createElement('button');button.className='quick';button.dataset.filter='declared';button.innerHTML='<span><span class="dot"></span> Declared</span><b id="count-declared">0</b>';syncButton.insertAdjacentElement('afterend',button);button.onclick=()=>{$$('.quick').forEach(x=>x.classList.remove('active'));button.classList.add('active');active='declared';page=1;load()};allSyncPages().then(values=>{declaredCache=values.filter(w=>w.directory_verified&&w.fingerprint_claimed&&Number(w.last_seen||0)>0);const count=$('#count-declared');if(count)count.textContent=String(declaredCache.length)}).catch(()=>{})}
  const toolbar=document.querySelector('.toolbar');if(toolbar&&!toolbar.querySelector('.view-toggle')){const toggle=document.createElement('div');toggle.className='view-toggle';toggle.innerHTML='<button class="active" data-public-view="cards" title="Placards">▦</button><button data-public-view="horizontal" title="Horizontal">☰</button>';toolbar.appendChild(toggle);toggle.querySelectorAll('[data-public-view]').forEach(button=>button.onclick=()=>{webView=button.dataset.publicView==='horizontal'?'horizontal':'cards';toggle.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===button));$('#cards').classList.toggle('horizontal',webView==='horizontal');render()})}
  const originalRender=render;render=function(){originalRender();$('#cards')?.classList.toggle('horizontal',webView==='horizontal')};
})();
</script>
'''


def public_browser_html() -> bytes:
    page = _legacy_public_browser_html()
    marker = b"</body>"
    extension = _PUBLIC_BROWSER_EXTENSION.encode("utf-8")
    return page.replace(marker, extension + marker, 1) if marker in page else page + extension
