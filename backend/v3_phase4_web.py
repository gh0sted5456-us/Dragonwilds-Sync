from __future__ import annotations

"""Add V3 Phase 4 two-sided placards to the existing public WebHost surface."""

_EXTENSION = r'''
<style id="dws-v3-phase4-web-style">
.world-card.dws-v3p4{perspective:1100px;overflow:visible}.dws-v3p4-inner{display:grid;height:100%;min-height:inherit;transform-style:preserve-3d;transition:transform .5s cubic-bezier(.2,.7,.2,1)}.dws-v3p4-face{grid-area:1/1;backface-visibility:hidden;-webkit-backface-visibility:hidden;min-width:0}.dws-v3p4-back{transform:rotateY(180deg);display:flex;flex-direction:column;padding:16px;border-radius:inherit;background:linear-gradient(145deg,#111718,#0a0e0f)}.dws-v3p4.back .dws-v3p4-inner{transform:rotateY(180deg)}.dws-v3p4-back-scroll{max-height:340px;overflow:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding-right:6px}.dws-v3p4-section{padding:10px 0;border-bottom:1px solid var(--line2)}.dws-v3p4-section:last-child{border-bottom:0}.dws-v3p4-section h4{margin:0 0 6px;color:var(--gold2);font-size:10px;text-transform:uppercase;letter-spacing:.08em}.dws-v3p4-section p{margin:0;white-space:pre-line;color:var(--text);font-size:12px}.dws-v3p4-badges,.dws-v3p4-platforms{display:flex;gap:7px;flex-wrap:wrap}.dws-v3p4-badge,.dws-v3p4-platform{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;border:1px solid var(--line2);border-radius:999px;color:var(--text);text-decoration:none;font-size:10px;font-weight:800}.dws-v3p4-badge img{width:20px;height:20px;object-fit:contain;border-radius:4px}.dws-v3p4-platform img{width:22px;height:22px;object-fit:contain}.dws-v3p4-mods{display:grid;gap:5px}.dws-v3p4-mods div{display:flex;justify-content:space-between;gap:10px;padding:6px 7px;border:1px solid var(--line2);border-radius:7px;font-size:10px}.dws-v3p4-controls{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:auto;padding-top:10px;border-top:1px solid var(--line2);color:var(--muted);font-size:10px}.dws-v3p4-heart{display:inline-flex;gap:5px;align-items:center}.dws-v3p4-heart.active{color:var(--good)}.dws-v3p4-heart.partial,.dws-v3p4-heart.connecting{color:var(--gold2)}.dws-v3p4-heart.failed{color:#e58a8a}.dws-v3p4-heart.motion b{animation:dws-v3-heart 1.1s ease-in-out infinite}@keyframes dws-v3-heart{0%,100%{transform:scale(1);opacity:.7}25%{transform:scale(1.25);opacity:1}55%{transform:scale(1.04);opacity:.85}}.dws-v3p4-menu{position:fixed;z-index:120;min-width:150px;padding:6px;border:1px solid var(--line);border-radius:9px;background:#111617;box-shadow:0 18px 50px #000a}.dws-v3p4-menu button{width:100%;text-align:left}.cards.horizontal>.dws-v3p4-open-row{grid-column:1/-1!important;display:block!important;min-height:330px!important}.cards.horizontal>.dws-v3p4-open-row .dws-v3p4-face{display:flex;flex-direction:column}.cards.horizontal>.dws-v3p4-open-row .banner{height:110px;min-height:110px}.cards.horizontal>.dws-v3p4-open-row .world-body{display:grid;grid-template-columns:52px 1fr auto}.cards.horizontal>.dws-v3p4-open-row footer{display:flex}.dws-v3p4[data-motion="reduced"] .dws-v3p4-inner{transition-duration:.14s}.dws-v3p4[data-motion="reduced"] .dws-v3p4-heart.motion b{animation-duration:2.2s}.dws-v3p4[data-motion="off"] .dws-v3p4-inner{transform:none!important;transition:none}.dws-v3p4[data-motion="off"] .dws-v3p4-face{transform:none;backface-visibility:visible}.dws-v3p4[data-motion="off"] .dws-v3p4-front,.dws-v3p4[data-motion="off"] .dws-v3p4-back{display:none}.dws-v3p4[data-motion="off"]:not(.back) .dws-v3p4-front{display:flex;flex-direction:column}.dws-v3p4[data-motion="off"].back .dws-v3p4-back{display:flex}.dws-v3p4[data-motion="off"] .dws-v3p4-heart b{animation:none!important}@media(prefers-reduced-motion:reduce){.dws-v3p4-inner{transition-duration:.14s}.dws-v3p4-heart b{animation:none!important}}
</style>
<script id="dws-v3-phase4-web-script">
(()=>{
  'use strict';
  if(typeof card!=='function'||typeof render!=='function')return;
  const side=new Map();
  const esc4=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const arr=v=>Array.isArray(v)?v:[];
  const txt=v=>String(v??'').trim();
  const motion=()=>{const saved=localStorage.getItem('dws-v3-animation-mode');if(['full','reduced','off'].includes(saved))return saved;return matchMedia('(prefers-reduced-motion: reduce)').matches?'reduced':'full'};
  const safeBadgeAsset=(v)=>/^\/assets\/placards\/badge-[0-9a-f]{64}\.png$/i.test(txt(v))||/^https:\/\//i.test(txt(v));
  const safeHttps=(v)=>/^https:\/\//i.test(txt(v));
  function badges(w){const src=[w.badge_refs,w.custom_badges,w.badges].find(Array.isArray)||[];return src.map(raw=>typeof raw==='string'?{label:raw,tooltip:raw}:raw).filter(Boolean).map(row=>{const label=txt(row.label||row.name||row.id),tip=txt(row.tooltip||row.meaning||row.description||label),remote=txt(row.asset_url||row.asset_path||row.image_url),image=safeBadgeAsset(remote)?`<img src="${esc4(remote)}" alt="">`:'<span>◆</span>',link=safeHttps(row.link||row.url)?txt(row.link||row.url):'';if(!label)return'';return link?`<a class="dws-v3p4-badge" href="${esc4(link)}" target="_blank" rel="noopener" title="${esc4(tip||label)}">${image}<span>${esc4(label)}</span></a>`:`<span class="dws-v3p4-badge" title="${esc4(tip||label)}">${image}<span>${esc4(label)}</span></span>`}).filter(Boolean).slice(0,16).join('')}
  function platforms(w){const iconAlias={steam:'steam',epic:'epicgames',xbox:'xbox',playstation:'playstation',windows:'windows','nintendo-switch-2':'nintendo',linux:'linux'};let refs=arr(w.platform_refs);if(!refs.length){const aliases={steam:'steam',epic:'epic',epicgames:'epic',xbox:'xbox',playstation:'playstation',psn:'playstation',nintendo:'nintendo-switch-2','switch 2':'nintendo-switch-2',windows:'windows',linux:'linux'},values=w.platforms||w.platform_compatibility||w.compatibility?.platforms||[];refs=[...new Set(arr(values).map(v=>aliases[txt(v).toLowerCase()]).filter(Boolean))].map(id=>({id,displayName:id}))}return refs.map(row=>{const id=txt(row.id),icon=iconAlias[id];if(!icon)return'';const label=txt(row.displayName||id),url=safeHttps(row.directSupportUrl)?txt(row.directSupportUrl):(safeHttps(row.fallbackInfoUrl)?txt(row.fallbackInfoUrl):'');const body=`<img src="/assets/platforms/${esc4(icon)}.svg" alt=""><span>${esc4(label)}</span>`;return url?`<a class="dws-v3p4-platform" href="${esc4(url)}" target="_blank" rel="noopener" title="${esc4(row.verified?'Official store/details':'Platform information')}">${body}</a>`:`<span class="dws-v3p4-platform" title="No verified direct store link is currently registered">${body}</span>`}).join('')}
  function mods(w){const values=[w.mods,w.mod_requirements,w.required_mods].find(Array.isArray)||[];return values.map(raw=>typeof raw==='string'?{name:raw}:raw).filter(row=>row&&txt(row.name||row.id)&&!/^dragonconnect$/i.test(txt(row.name||row.id).replace(/\s+/g,''))).slice(0,32).map(row=>`<div><strong>${esc4(row.name||row.id)}</strong><span>${esc4(row.version||'')} ${esc4(String(row.runtime_role||row.role||'BOTH').toUpperCase())}</span></div>`).join('')}
  function heartbeat(w){const raw=txt(w.heartbeat_state||w.directory_state||w.heartbeat?.state||w.status||'');const s=['active','connecting','partial','failed','disabled'].includes(raw.toLowerCase())?raw.toLowerCase():(Number(w.last_seen||0)>0?'active':'disabled');return `<span class="dws-v3p4-heart ${s} ${motion()!=='off'&&['active','connecting','partial'].includes(s)?'motion':''}"><b>♥</b><span>Heartbeat ${esc4(s[0].toUpperCase()+s.slice(1))}</span></span>`}
  function back(w){const rules=txt(w.rules||w.community_rules),b=badges(w),m=mods(w),p=platforms(w),extra=txt(w.additional_information||w.region||'');return `<div class="dws-v3p4-back-scroll" tabindex="0">${rules?`<section class="dws-v3p4-section"><h4>Community Rules</h4><p>${esc4(rules)}</p></section>`:''}${b?`<section class="dws-v3p4-section"><h4>Community Badges</h4><div class="dws-v3p4-badges">${b}</div></section>`:''}${m?`<section class="dws-v3p4-section"><h4>Required Mods</h4><div class="dws-v3p4-mods">${m}</div></section>`:''}${p?`<section class="dws-v3p4-section"><h4>Compatibility</h4><div class="dws-v3p4-platforms">${p}</div></section>`:''}${extra?`<section class="dws-v3p4-section"><h4>Additional Information</h4><p>${esc4(extra)}</p></section>`:''}${(!rules&&!b&&!m&&!p&&!extra)?'<p class="muted">No additional joining requirements are published.</p>':''}</div><div class="dws-v3p4-controls">${heartbeat(w)}<button data-v3p4-toggle>← Front</button></div>`}
  const baseCard=card;
  card=function(w){const html=baseCard(w),tpl=document.createElement('template');tpl.innerHTML=html.trim();const article=tpl.content.firstElementChild;if(!article)return html;article.classList.add('dws-v3p4');article.dataset.v3p4Id=String(w.id||w.world_id||w.world_name||'');article.dataset.motion=motion();const front=document.createElement('div');front.className='dws-v3p4-face dws-v3p4-front';while(article.firstChild)front.appendChild(article.firstChild);const frontCtl=document.createElement('div');frontCtl.className='dws-v3p4-controls';frontCtl.innerHTML=`${heartbeat(w)}<button data-v3p4-toggle>Details →</button>`;front.appendChild(frontCtl);const backFace=document.createElement('div');backFace.className='dws-v3p4-face dws-v3p4-back';backFace.innerHTML=back(w);const inner=document.createElement('div');inner.className='dws-v3p4-inner';inner.append(front,backFace);article.appendChild(inner);if(side.get(article.dataset.v3p4Id)==='back')article.classList.add('back');return article.outerHTML};
  function toggle(node){const id=node.dataset.v3p4Id||'';const next=node.classList.toggle('back')?'back':'front';side.set(id,next)}
  function bind(){document.querySelectorAll('.dws-v3p4').forEach(node=>{node.dataset.motion=motion();if(node.dataset.v3p4Bound==='1')return;node.dataset.v3p4Bound='1';node.addEventListener('click',e=>{if(e.target.closest('button,a,input,select,textarea,.dws-v3p4-back-scroll')){if(e.target.closest('[data-v3p4-toggle]')){e.preventDefault();e.stopPropagation();toggle(node)}return}toggle(node)});node.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button,a,input,select,textarea')){e.preventDefault();toggle(node)}});node.tabIndex=0;node.addEventListener('contextmenu',e=>{if(!document.getElementById('cards')?.classList.contains('horizontal'))return;e.preventDefault();document.querySelector('.dws-v3p4-menu')?.remove();const menu=document.createElement('div');menu.className='dws-v3p4-menu';menu.style.left=Math.min(e.clientX,innerWidth-170)+'px';menu.style.top=Math.min(e.clientY,innerHeight-80)+'px';menu.innerHTML='<button>Open Placard</button>';document.body.appendChild(menu);menu.querySelector('button').onclick=()=>{document.querySelectorAll('.dws-v3p4-open-row').forEach(x=>x.remove());const clone=node.cloneNode(true);clone.classList.add('dws-v3p4-open-row');clone.classList.remove('back');clone.dataset.v3p4Bound='0';node.insertAdjacentElement('afterend',clone);menu.remove();bind()};setTimeout(()=>document.addEventListener('click',()=>menu.remove(),{once:true}),0)})})}
  const baseRender=render;render=function(){baseRender();bind()};bind();
})();
</script>
'''.encode("utf-8")


def _decorate(page: bytes) -> bytes:
    payload = bytes(page)
    if b'id="dws-v3-phase4-web-script"' in payload:
        return payload
    marker = b"</body>"
    return payload.replace(marker, _EXTENSION + marker, 1) if marker in payload else payload + _EXTENSION


def install() -> None:
    import directory_web
    if getattr(directory_web, "_DWS_V3_PHASE4_WEB_INSTALLED", False):
        return
    directory_web._DWS_V3_PHASE4_WEB_INSTALLED = True
    public = directory_web.public_browser_html
    detail = directory_web.detail_html
    directory_web.public_browser_html = lambda *args, **kwargs: _decorate(public(*args, **kwargs))
    directory_web.detail_html = lambda *args, **kwargs: _decorate(detail(*args, **kwargs))

    # Reuse the already-hardened PNG /assets/placards route instead of creating
    # another listener. The filename allowlist expands only to badge-<sha256>.png
    # and the cache resolver re-verifies PNG signature + hash before serving.
    try:
        import directory_host
        from v3_phase4_badges import badge_asset_bytes
        if not getattr(directory_host, "_DWS_V3_PHASE4_BADGE_ROUTE_INSTALLED", False):
            original = directory_host._placard_background_bytes
            def phase4_asset(name: str) -> bytes:
                value = str(name or "")
                if value.casefold().startswith("badge-"):
                    return badge_asset_bytes(value)
                return original(name)
            directory_host._placard_background_bytes = phase4_asset
            directory_host._DWS_V3_PHASE4_BADGE_ROUTE_INSTALLED = True
    except Exception:
        pass
