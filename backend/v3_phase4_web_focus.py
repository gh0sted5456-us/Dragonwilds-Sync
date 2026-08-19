from __future__ import annotations

"""Focused/touch-friendly Open behavior for the existing V3 Phase 4 WebHost placards.

This is presentation-only. It reuses the already-rendered public card, never
creates a second directory, heartbeat source, login flow, or data authority.
"""

_EXTENSION = r'''
<style id="dws-v3-phase4-focus-style">
.dws-v3p4-open{margin-left:auto}.dws-v3p4-focus{position:fixed;inset:0;z-index:240;display:none;place-items:center;padding:18px;background:rgba(0,0,0,.72);backdrop-filter:blur(9px)}.dws-v3p4-focus.open{display:grid}.dws-v3p4-focus-shell{display:flex;flex-direction:column;width:min(820px,100%);height:min(760px,calc(100vh - 36px));min-height:360px;border:1px solid var(--line);border-radius:16px;background:#101516;box-shadow:0 30px 100px #000c;overflow:hidden}.dws-v3p4-focus-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border-bottom:1px solid var(--line2)}.dws-v3p4-focus-head strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dws-v3p4-focus-body{flex:1;min-height:0;overflow:auto;padding:14px}.dws-v3p4-focus-body>.dws-v3p4{height:100%;min-height:520px;margin:0}.dws-v3p4-focus-body .dws-v3p4-back-scroll{max-height:min(480px,60vh)}@media(max-width:650px){.dws-v3p4-focus{padding:5px}.dws-v3p4-focus-shell{width:100%;height:calc(100vh - 10px)}.dws-v3p4-focus-body{padding:7px}.dws-v3p4-focus-body>.dws-v3p4{min-height:460px}}
</style>
<script id="dws-v3-phase4-focus-script">
(()=>{
  'use strict';
  if(document.getElementById('dws-v3p4-focus'))return;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const txt=v=>String(v??'').trim();
  const modal=document.createElement('section');modal.id='dws-v3p4-focus';modal.className='dws-v3p4-focus';modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.innerHTML='<div class="dws-v3p4-focus-shell"><div class="dws-v3p4-focus-head"><strong>World Placard</strong><button data-v3p4-focus-close aria-label="Close">×</button></div><div class="dws-v3p4-focus-body"></div></div>';document.body.appendChild(modal);
  const body=modal.querySelector('.dws-v3p4-focus-body'),title=modal.querySelector('.dws-v3p4-focus-head strong');let activeId='';
  function idOf(node){return txt(node?.dataset?.v3p4Id||node?.dataset?.worldId||'')}
  function clearHash(){if(location.hash.startsWith('#world='))history.replaceState(null,'',location.pathname+location.search)}
  function close(){modal.classList.remove('open');body.replaceChildren();activeId='';clearHash()}
  function wireClone(clone){clone.dataset.v3p4FocusClone='1';clone.querySelectorAll('[data-v3p4-open]').forEach(x=>x.remove());clone.addEventListener('click',e=>{const toggle=e.target.closest('[data-v3p4-toggle]');if(toggle){e.preventDefault();e.stopPropagation();clone.classList.toggle('back');return}if(e.target.closest('a,button,input,select,textarea,.dws-v3p4-back-scroll'))return;clone.classList.toggle('back')});clone.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&!e.target.closest('a,button,input,select,textarea')){e.preventDefault();clone.classList.toggle('back')}})}
  function open(node,pushHash=true){if(!node)return;const id=idOf(node);if(!id)return;const clone=node.cloneNode(true);wireClone(clone);activeId=id;const label=txt(node.querySelector('h2,h3')?.textContent)||'World Placard';title.textContent=label;body.replaceChildren(clone);modal.classList.add('open');if(pushHash)history.replaceState(null,'',`${location.pathname}${location.search}#world=${encodeURIComponent(id)}`);modal.querySelector('[data-v3p4-focus-close]')?.focus()}
  function ensureOpen(root=document){root.querySelectorAll?.('.dws-v3p4:not([data-v3p4-focus-clone])').forEach(node=>{node.querySelectorAll('.dws-v3p4-controls').forEach((controls,index)=>{if(controls.querySelector('[data-v3p4-open]'))return;const button=document.createElement('button');button.className='dws-v3p4-open';button.dataset.v3p4Open='1';button.textContent='Open';button.title='Open focused World placard';button.onclick=e=>{e.preventDefault();e.stopPropagation();open(node)};controls.appendChild(button)});});}
  modal.querySelector('[data-v3p4-focus-close]').onclick=close;modal.addEventListener('click',e=>{if(e.target===modal)close()});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&modal.classList.contains('open'))close()});
  document.addEventListener('contextmenu',e=>{const node=e.target.closest?.('.cards.horizontal .dws-v3p4:not([data-v3p4-focus-clone])');if(!node)return;e.preventDefault();e.stopImmediatePropagation();document.querySelector('.dws-v3p4-menu')?.remove();const menu=document.createElement('div');menu.className='dws-v3p4-menu';menu.style.left=Math.min(e.clientX,innerWidth-170)+'px';menu.style.top=Math.min(e.clientY,innerHeight-80)+'px';menu.innerHTML='<button>Open Placard</button>';document.body.appendChild(menu);menu.querySelector('button').onclick=()=>{open(node);menu.remove()};setTimeout(()=>document.addEventListener('click',()=>menu.remove(),{once:true}),0)},true);
  const observer=new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node instanceof Element)ensureOpen(node);ensureOpen(document)});observer.observe(document.documentElement,{childList:true,subtree:true});ensureOpen();
  function openHash(){if(!location.hash.startsWith('#world='))return;let id='';try{id=decodeURIComponent(location.hash.slice(7))}catch(_){return}const node=[...document.querySelectorAll('.dws-v3p4:not([data-v3p4-focus-clone])')].find(x=>idOf(x)===id);if(node)open(node,false)}
  setTimeout(openHash,0);window.addEventListener('hashchange',openHash);
})();
</script>
'''.encode("utf-8")


def _decorate(page: bytes) -> bytes:
    payload = bytes(page)
    if b'id="dws-v3-phase4-focus-script"' in payload:
        return payload
    marker = b"</body>"
    return payload.replace(marker, _EXTENSION + marker, 1) if marker in payload else payload + _EXTENSION


def install() -> None:
    import directory_web
    if getattr(directory_web, "_DWS_V3_PHASE4_FOCUS_INSTALLED", False):
        return
    directory_web._DWS_V3_PHASE4_FOCUS_INSTALLED = True
    public = directory_web.public_browser_html
    detail = directory_web.detail_html
    directory_web.public_browser_html = lambda *args, **kwargs: _decorate(public(*args, **kwargs))
    directory_web.detail_html = lambda *args, **kwargs: _decorate(detail(*args, **kwargs))
