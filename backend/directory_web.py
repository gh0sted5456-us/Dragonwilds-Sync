from __future__ import annotations

"""Additive V2 public WebGUI presentation layer.

The proven WebGUI remains in ``directory_web_legacy``. This wrapper adds the
shared placard/horizontal contract, Declared projection, smooth artwork/icons,
the WebHost-as-router Remote Server handoff, and the shared unified console
presentation used by authenticated server management.
"""

from directory_web_legacy import *  # noqa: F401,F403
from directory_web_legacy import admin_login_html as _legacy_admin_login_html
from directory_web_legacy import detail_html as _legacy_detail_html
from directory_web_legacy import public_browser_html as _legacy_public_browser_html
from directory_web_legacy import remote_admin_html as _legacy_remote_admin_html


def _public_extension(remote_admin_enabled: bool) -> str:
    remote_flag = "true" if remote_admin_enabled else "false"
    return rf'''
<style id="dws-public-v2-style">
/* Uniform smooth cards: artwork is part of the surface instead of a boxed panel. */
.cards{{align-items:stretch;grid-auto-rows:1fr}}.cards>.world-card{{height:100%;min-height:330px;display:flex;flex-direction:column;overflow:hidden}}.world-card .world-body{{flex:1}}.world-card footer{{margin-top:auto}}
.banner{{border:0!important;box-shadow:none!important;position:relative;isolation:isolate;mask-image:linear-gradient(to bottom,#000 0%,#000 58%,rgba(0,0,0,.74) 76%,transparent 100%);-webkit-mask-image:linear-gradient(to bottom,#000 0%,#000 58%,rgba(0,0,0,.74) 76%,transparent 100%)}}
.title-line{{flex-wrap:wrap}}.title-line .badge,.title-line .community-sources{{flex:0 0 auto}}.world-copy{{min-width:0}}.world-copy .dws-profile-badges{{display:flex;gap:5px;flex-wrap:wrap;margin:6px 0}}.dws-profile-badge{{display:inline-flex;align-items:center;padding:3px 6px;border:0;border-radius:999px;color:var(--gold2);background:rgba(213,165,74,.08);font-size:9px;font-weight:850;letter-spacing:.05em;text-transform:uppercase}}
.platforms,.community-sources{{display:flex;align-items:center;gap:7px;flex-wrap:wrap}}.platforms img{{width:22px;height:22px;object-fit:contain;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;filter:none}}.platforms img[data-icon-tone="black"],.dws-icon-black{{filter:grayscale(1) brightness(0)!important}}.platforms img[data-icon-tone="white"],.dws-icon-white{{filter:grayscale(1) brightness(0) invert(1)!important}}.platforms img[data-icon-tone="color"],.dws-icon-color{{filter:none!important}}@media(prefers-color-scheme:light){{.dws-icon-auto{{filter:grayscale(1) brightness(0)!important}}}}@media(prefers-color-scheme:dark){{.dws-icon-auto{{filter:grayscale(1) brightness(0) invert(1)!important}}}}
.view-toggle{{display:inline-flex;gap:4px;padding:3px;border:1px solid var(--line2);border-radius:10px;background:#0c1011}}.view-toggle button{{min-height:34px;padding:6px 9px;background:transparent}}.view-toggle button.active{{border-color:var(--gold);background:#292419;color:var(--gold2)}}
.cards.horizontal{{display:grid;grid-template-columns:1fr;gap:9px;grid-auto-rows:auto}}.cards.horizontal .world-card{{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,31%);grid-template-areas:"body banner" "footer banner";min-height:148px;height:auto;overflow:hidden}}.cards.horizontal .banner{{grid-area:banner;height:100%;min-height:148px;mask-image:linear-gradient(to right,transparent 0%,rgba(0,0,0,.35) 14%,#000 42%,#000 100%);-webkit-mask-image:linear-gradient(to right,transparent 0%,rgba(0,0,0,.35) 14%,#000 42%,#000 100%)}}.cards.horizontal .world-body{{grid-area:body;display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:12px;padding:14px}}.cards.horizontal .world-icon{{position:static;width:48px;height:48px;margin:0}}.cards.horizontal .world-copy p{{margin:3px 0 5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.cards.horizontal .world-body dl{{display:flex;gap:16px;align-items:center;margin:0;border:0}}.cards.horizontal .world-card footer{{grid-area:footer;border:0;display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:transparent}}.cards.horizontal .world-card footer .button{{white-space:nowrap}}
.dws-remote-router{{position:fixed;inset:0;z-index:100;display:none;place-items:center;padding:18px;background:#000b;backdrop-filter:blur(10px)}}.dws-remote-router.open{{display:grid}}.dws-remote-router-card{{width:min(520px,100%);padding:22px;border:1px solid #655431;border-radius:16px;background:#111617;box-shadow:0 30px 90px #000}}.dws-remote-router-card h2{{margin:5px 0}}.dws-remote-router-card p{{color:var(--muted)}}.dws-remote-router-actions{{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}}#dws-router-message{{min-height:18px;color:var(--muted);font-size:11px;margin-top:8px}}
@media(max-width:900px){{.cards.horizontal .world-card{{grid-template-columns:minmax(0,1fr) 190px}}.cards.horizontal .world-body{{grid-template-columns:44px minmax(0,1fr)}}.cards.horizontal .world-body dl{{display:none}}}}@media(max-width:650px){{.cards>.world-card{{min-height:0}}.cards.horizontal .world-card{{display:block}}.cards.horizontal .banner{{height:62px;min-height:62px;mask-image:linear-gradient(to bottom,#000 0%,rgba(0,0,0,.6) 60%,transparent 100%);-webkit-mask-image:linear-gradient(to bottom,#000 0%,rgba(0,0,0,.6) 60%,transparent 100%)}}}}
</style>
<script id="dws-public-v2-script">
(() => {{
  'use strict';
  const remoteRoutingEnabled={remote_flag};
  let webView='cards', declaredCache=[];
  const originalCard=card, originalLoad=load;
  function profileBadgeValues(w){{const values=[...(Array.isArray(w.badges)?w.badges:[]),...(Array.isArray(w.profile_badges)?w.profile_badges:[]),...(Array.isArray(w.mod_badges)?w.mod_badges:[])];return [...new Set(values.map(v=>String(typeof v==='object'?(v.label||v.name||v.title||v.id||''):v||'').trim()).filter(Boolean).map(v=>v.toUpperCase()))].slice(0,12)}}
  function profileBadges(w){{const values=profileBadgeValues(w);return values.length?`<div class="dws-profile-badges">${{values.map(v=>`<span class="dws-profile-badge">${{esc(v)}}</span>`).join('')}}</div>`:''}}
  function horizontalCard(w){{const sync=!!w.sync_ready,declared=!!(w.directory_verified&&w.fingerprint_claimed&&w.last_seen),players=Number(w.players||0),max=Number(w.max_players||0);return `<article class="world-card panel"><div class="banner"${{w.banner_b64?` style="background-image:url('${{esc(w.banner_b64)}}')"`:''}}><span class="source">${{esc(w.source_label||'Dragonwilds')}}</span></div><div class="world-body"><div class="world-icon">${{w.icon_b64?`<img src="${{esc(w.icon_b64)}}" alt="">`:esc((w.world_name||'W')[0])}}</div><div class="world-copy"><div class="title-line"><h2>${{esc(w.world_name||'Unnamed World')}}</h2>${{identityBadges(w)}}${{communitySourceBadges(w)}}${{declared?'<span class="badge good">◆ Declared</span>':sync?'<span class="badge good">◆ Sync Ready</span>':'<span class="badge plain">Vanilla discovery</span>'}}</div><p>${{esc(w.description||'A discovered RuneScape: Dragonwilds World.')}}</p>${{profileBadges(w)}}${{platformBadges(w)}}${{tagGroups(w)}}</div><dl><div><dt>Players</dt><dd>${{players}}${{max?' / '+max:''}}</dd></div><div><dt>Region</dt><dd>${{flag(w.country_code)}} ${{esc(w.region||w.country_name||'Unknown')}}</dd></div><div><dt>Ping</dt><dd>${{w.ping_ms!=null?Math.round(w.ping_ms)+' ms':'—'}}</dd></div></dl></div><footer><span>${{w.password_required?'🔒 Password':'◇ Open'}} · ${{w.modded?'Modded':'Vanilla'}}</span><a class="button ${{sync?'primary':''}}" href="/servers/${{encodeURIComponent(w.id)}}">Details</a></footer></article>`}}
  card=function(w){{if(webView==='horizontal')return horizontalCard(w);const html=originalCard(w);const badges=profileBadges(w);return badges?html.replace('</p>',`</p>${{badges}}`):html}};
  async function allSyncPages(){{const first=await fetch('/api/v1/worlds?active=sync&page=1&sort='+encodeURIComponent($('#sort').value),{{cache:'no-store'}}).then(r=>r.json());const payloads=[first],count=Math.max(1,Math.min(50,Number(first.page_count||1)));for(let p=2;p<=count;p++){{const next=await fetch('/api/v1/worlds?active=sync&page='+p+'&sort='+encodeURIComponent($('#sort').value),{{cache:'no-store'}}).then(r=>r.json());payloads.push(next)}}return payloads.flatMap(x=>x.worlds||[])}}
  async function loadDeclared(){{const currentSearch=$('#search').value.trim().toLowerCase(),region=$('#region').value,access=$('#access').value;let values=(await allSyncPages()).filter(w=>w.directory_verified&&w.fingerprint_claimed&&Number(w.last_seen||0)>0);if(currentSearch)values=values.filter(w=>JSON.stringify([w.world_name,w.description,w.region,w.country_name,w.tags,w.badges,w.mod_badges]).toLowerCase().includes(currentSearch));if(region)values=values.filter(w=>String(w.region||'')===region);if(access==='password')values=values.filter(w=>w.password_required);if(access==='open')values=values.filter(w=>!w.password_required);declaredCache=values;rows=values;total=values.length;page=1;pageCount=1;const count=$('#count-declared');if(count)count.textContent=String(values.length);$('#updated').textContent='Declared updated '+new Date().toLocaleTimeString();render()}}
  load=async function(){{return active==='declared'?loadDeclared():originalLoad()}};
  const syncButton=document.querySelector('.quick[data-filter="sync"]');if(syncButton&&!document.querySelector('[data-filter="declared"]')){{const button=document.createElement('button');button.className='quick';button.dataset.filter='declared';button.innerHTML='<span><span class="dot"></span> Declared</span><b id="count-declared">0</b>';syncButton.insertAdjacentElement('afterend',button);button.onclick=()=>{{$$('.quick').forEach(x=>x.classList.remove('active'));button.classList.add('active');active='declared';page=1;load()}};allSyncPages().then(values=>{{declaredCache=values.filter(w=>w.directory_verified&&w.fingerprint_claimed&&Number(w.last_seen||0)>0);const count=$('#count-declared');if(count)count.textContent=String(declaredCache.length)}}).catch(()=>{{}})}}
  const toolbar=document.querySelector('.toolbar');if(toolbar&&!toolbar.querySelector('.view-toggle')){{const toggle=document.createElement('div');toggle.className='view-toggle';toggle.innerHTML='<button class="active" data-public-view="cards" title="Placards">▦</button><button data-public-view="horizontal" title="Horizontal">☰</button>';toolbar.appendChild(toggle);toggle.querySelectorAll('[data-public-view]').forEach(button=>button.onclick=()=>{{webView=button.dataset.publicView==='horizontal'?'horizontal':'cards';toggle.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===button));$('#cards').classList.toggle('horizontal',webView==='horizontal');render()}})}}
  const originalRender=render;render=function(){{originalRender();$('#cards')?.classList.toggle('horizontal',webView==='horizontal')}};

  if(remoteRoutingEnabled){{
    const entry=document.querySelector('.admin-entry');
    if(entry){{entry.href='#';entry.querySelector('b').textContent='Server Management';entry.querySelector('small').textContent='Route to a declared World';}}
    const modal=document.createElement('section');modal.className='dws-remote-router';modal.id='dws-remote-router';modal.innerHTML='<div class="dws-remote-router-card"><div class="eyebrow">WebHost routing</div><h2>Server Management</h2><p>Enter the exact World Name. This WebHost only resolves the active heartbeat and sends you to that World. Your username/password are entered on the target server and are never sent to this hub.</p><label>World Name<input class="field" id="dws-router-world" autocomplete="organization" placeholder="Exact advertised World Name"></label><div id="dws-router-message"></div><div class="dws-remote-router-actions"><button id="dws-router-cancel">Cancel</button><button class="primary" id="dws-router-go">Find Server</button></div></div>';document.body.appendChild(modal);
    const close=()=>modal.classList.remove('open');if(entry)entry.onclick=e=>{{e.preventDefault();modal.classList.add('open');document.getElementById('dws-router-world')?.focus()}};document.getElementById('dws-router-cancel').onclick=close;modal.onclick=e=>{{if(e.target===modal)close()}};
    document.getElementById('dws-router-go').onclick=async()=>{{const name=document.getElementById('dws-router-world').value.trim(),message=document.getElementById('dws-router-message');if(!name){{message.textContent='Enter the exact World Name.';return}}message.textContent='Resolving live heartbeat…';try{{const worlds=await allSyncPages(),world=worlds.find(row=>String(row.world_name||'').trim().toLowerCase()===name.toLowerCase());if(!world)throw Error('No active Sync heartbeat matches that World Name.');const remote=world.remote_management||{{}},endpoint=String(remote.endpoint||'').replace(/\/$/,'');if(!remote.enabled||!endpoint)throw Error('That World is not currently advertising Remote Server management.');const target=new URL(endpoint);if(!['http:','https:'].includes(target.protocol)||target.username||target.password)throw Error('The advertised Remote Server endpoint was rejected.');target.pathname=target.pathname.replace(/\/$/,'')+'/admin/login';target.search='?world='+encodeURIComponent(world.world_name||name);location.href=target.href}}catch(error){{message.textContent=error.message||String(error)}}}};
  }}
}})();
</script>
'''


def _remote_admin_extension() -> bytes:
    return b'''
<style id="dws-remote-unified-console-style">
.dws-web-console-filters{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0}.dws-web-console-filters button{min-height:30px;padding:5px 9px;font-size:10px}.dws-web-console-filters button.active{border-color:var(--gold);color:var(--gold2);background:#292419}.dws-web-unified-console{height:min(420px,46vh);overflow:auto;border:1px solid var(--line2);border-radius:10px;background:#080b0c;font:11px/1.45 Consolas,monospace}.dws-web-console-row{display:grid;grid-template-columns:82px 62px minmax(0,1fr);gap:8px;padding:6px 9px;border-left:3px solid transparent}.dws-web-console-row:nth-child(odd){background:rgba(255,255,255,.018)}.dws-web-console-row time{color:#68706d}.dws-web-console-row b{font-size:9px}.dws-web-console-row.game{border-left-color:#d5a54a}.dws-web-console-row.game b{color:#f0c66e}.dws-web-console-row.server{border-left-color:#67a6dc}.dws-web-console-row.server b{color:#86bbe7}.dws-web-console-row.sync{border-left-color:#70d39b}.dws-web-console-row.sync b{color:#8be7b1}.dws-web-console-row.error{background:rgba(185,67,67,.1);color:#f0b1b1}.dws-web-log-paths{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.dws-web-log-paths>div{min-width:0;padding:8px;border:1px solid var(--line2);border-radius:8px}.dws-web-log-paths small{display:block;color:var(--muted);font-size:8px;font-weight:800}.dws-web-log-paths code{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--gold2);font-size:9px}@media(max-width:620px){.dws-web-console-row{grid-template-columns:64px 48px minmax(0,1fr)}.dws-web-log-paths{grid-template-columns:1fr}}
</style>
<script id="dws-remote-unified-console-script">
(()=>{
  if(typeof renderTab!=='function')return;
  const legacyRenderTab=renderTab;
  let filter='all';
  const rowHtml=(row)=>{const source=String(row.source||'server').toLowerCase(),level=String(row.level||'info').toLowerCase(),when=new Date(Number(row.ts||0)*1000),stamp=Number.isFinite(when.getTime())?when.toLocaleTimeString():'--';return `<div class="dws-web-console-row ${esc(source)} ${esc(level)}"><time>${esc(stamp)}</time><b>${esc(source.toUpperCase())}</b><span>${esc(row.message||'')}</span></div>`};
  const draw=()=>{const stream=data?.unified_console||{},rows=(stream.entries||[]).filter(row=>filter==='all'||row.source===filter),host=document.getElementById('dws-web-unified-console');if(host)host.innerHTML=rows.length?rows.map(rowHtml).join(''):'<p class="muted" style="padding:12px">No activity has been recorded for this server session yet.</p>';document.querySelectorAll('[data-dws-web-console-filter]').forEach(button=>button.classList.toggle('active',button.dataset.dwsWebConsoleFilter===filter))};
  renderTab=function(){legacyRenderTab();if(tab!=='console'||!data||!allowed('view_console'))return;const legacyUnits=document.querySelector('#tab-body .units');if(!legacyUnits)return;const stream=data.unified_console||{},counts=stream.counts||{};const toolbar=document.querySelector('#tab-body .toolbar');if(toolbar){const strong=toolbar.querySelector('strong');if(strong)strong.textContent='Unified Console';const muted=toolbar.querySelector('.muted');if(muted)muted.textContent='RSDW game commands + dedicated-server events + World Sync traffic \xc2\xb7 never an operating-system shell'}legacyUnits.outerHTML='<div class="dws-web-console-filters"><button data-dws-web-console-filter="all">ALL '+Number((counts.game||0)+(counts.server||0)+(counts.sync||0))+'</button><button data-dws-web-console-filter="game">GAME '+Number(counts.game||0)+'</button><button data-dws-web-console-filter="server">SERVER '+Number(counts.server||0)+'</button><button data-dws-web-console-filter="sync">SYNC '+Number(counts.sync||0)+'</button><button id="dws-web-console-refresh">Refresh stream</button></div><div id="dws-web-unified-console" class="dws-web-unified-console"></div><div class="dws-web-log-paths"><div><small>CURRENT SESSION LOG</small><code title="'+esc(stream.current_log||'')+'">'+esc(stream.current_log||'Unavailable')+'</code></div>'+(stream.previous_log?'<div><small>PREVIOUS SESSION BACKUP</small><code title="'+esc(stream.previous_log)+'">'+esc(stream.previous_log)+'</code></div>':'')+'</div>';document.querySelectorAll('[data-dws-web-console-filter]').forEach(button=>button.onclick=()=>{filter=button.dataset.dwsWebConsoleFilter||'all';draw()});const refresh=document.getElementById('dws-web-console-refresh');if(refresh)refresh.onclick=()=>load().catch(()=>{});draw()};
})();
</script>
'''


def public_browser_html(*, remote_admin_enabled: bool = False) -> bytes:
    page = _legacy_public_browser_html(remote_admin_enabled=remote_admin_enabled)
    marker = b"</body>"
    extension = _public_extension(remote_admin_enabled).encode("utf-8")
    return page.replace(marker, extension + marker, 1) if marker in page else page + extension


def admin_login_html() -> bytes:
    page = _legacy_admin_login_html()
    script = b'''<script id="dws-prefill-world">(()=>{const world=new URLSearchParams(location.search).get('world')||'';const input=document.getElementById('world');if(input&&world){input.value=world;input.readOnly=true;document.getElementById('account')?.focus();}})();</script>'''
    return page.replace(b"</body>", script + b"</body>", 1)


def remote_admin_html() -> bytes:
    page = _legacy_remote_admin_html()
    marker = b"</body>"
    extension = _remote_admin_extension()
    return page.replace(marker, extension + marker, 1) if marker in page else page + extension


def detail_html(world_id: str) -> bytes:
    page = _legacy_detail_html(world_id)
    # Public specs/network evidence remain useful. Raw debug dumps/buttons do not.
    cleanup = b'''<style>.all-world-metadata{display:none!important}.detail-actions a[href^="/api/v1/worlds/"]{display:none!important}</style>'''
    return page.replace(b"</head>", cleanup + b"</head>", 1)
