from __future__ import annotations

"""Small additive WebGUI layer for authoritative runtime/core/tooling state."""

# Source/developer runs do not execute the PyInstaller runtime hook. Install the
# same idempotent persistence/index layer here because this module is imported by
# the additive service before its profile adapters are bound.
try:
    from shell_persistence_stabilization import install as _install_shell_persistence
    _install_shell_persistence()
except Exception:
    pass


_EXTENSION = r'''
<style id="dws-phase3-runtime-style">
.dws-phase3-state{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:8px}.dws-phase3-pill{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;border:1px solid var(--line2);border-radius:999px;color:var(--muted);font-size:10px;font-weight:800}.dws-phase3-pill.current{color:var(--good);border-color:#29513d}.dws-phase3-pill.outdated,.dws-phase3-pill.error,.dws-phase3-pill.dependency_problem{color:var(--bad);border-color:#713939}.dws-phase3-pill.newer,.dws-phase3-pill.busy,.dws-phase3-pill.update_available{color:var(--gold2);border-color:#655431}.dws-core-components{display:grid;gap:8px;margin-top:10px}.dws-managed-section{margin-top:15px}.dws-managed-section>h4{margin:0 0 4px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}.dws-core-row{display:grid;grid-template-columns:minmax(145px,.8fr) minmax(190px,1.25fr) minmax(150px,.8fr) auto;gap:12px;align-items:center;padding:12px;border:1px solid var(--line2);border-radius:10px;background:#0c1011}.dws-core-row strong{display:block}.dws-core-row small{display:block;color:var(--muted);font-size:10px;overflow-wrap:anywhere}.dws-core-status{text-transform:uppercase;font-size:9px;font-weight:850;letter-spacing:.05em;color:var(--muted)}.dws-core-status.current{color:var(--good)}.dws-core-status.update_available,.dws-core-status.not_installed{color:var(--gold2)}.dws-core-status.dependency_problem,.dws-core-status.unable_to_check{color:var(--bad)}.dws-core-actions{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}.dws-core-actions button{min-height:32px;padding:5px 8px;font-size:10px}.dws-core-result{grid-column:1/-1;min-height:0;color:var(--muted);font-size:10px}.dws-core-result.error{color:var(--bad)}.dws-core-result.success{color:var(--good)}.dws-phase3-busy-note{padding:9px 10px;border:1px solid #655431;border-radius:8px;background:#18150e;color:var(--gold2);font-size:10px;margin-bottom:10px}@media(max-width:900px){.dws-core-row{grid-template-columns:1fr 1fr}.dws-core-actions{justify-content:flex-start}}@media(max-width:560px){.dws-core-row{grid-template-columns:1fr}}
</style>
<script id="dws-phase3-runtime-script">
(()=>{
  'use strict';
  if(typeof renderTab!=='function'||typeof command!=='function'||typeof load!=='function')return;
  const legacyRenderTab=renderTab,legacyLoad=load;
  const statusText=value=>({current:'Current',outdated:'Outdated',newer:'Newer than expected',unknown:'Unknown',unavailable:'Unavailable',update_available:'Update available',not_installed:'Not installed',dependency_problem:'Dependency problem',managed_no_update_source:'Managed · no authoritative update source',unable_to_check:'Unable to check',source_required:'Update source required'})[String(value||'unknown').toLowerCase()]||String(value||'Unknown').replaceAll('_',' ');
  const runtimeBusy=()=>!!(data?.runtime||{}).busy;
  const lifecycleState=()=>String((data?.runtime||{}).state||((data?.runtime||{}).running?'Running':'Stopped'));
  function permissionFor(button){return String(button?.dataset?.permission||button?.dataset?.action||'')}
  function applyActionState(){const busy=runtimeBusy(),state=lifecycleState();document.querySelectorAll('[data-action]').forEach(button=>{const action=String(button.dataset.action||''),permission=permissionFor(button),conflict=['start','stop','restart','update','update_restart'].includes(action);button.disabled=!allowed(permission)||(busy&&conflict);button.title=busy&&conflict?`Server lifecycle is busy: ${state}`:''});document.querySelectorAll('[data-core-update]').forEach(button=>{button.disabled=!allowed('update')||busy||button.dataset.updateAvailable!=='1';button.title=busy?`Server lifecycle is busy: ${state}`:(button.dataset.updateAvailable==='1'?'':'No managed update is currently available')});const online=document.getElementById('online');if(online&&busy){online.textContent='◐ '+state;online.className='badge plain'}}
  function clView(){const cl=data?.maintenance?.cl_version||{},reported=String(cl.reported_cl||''),expected=String(cl.expected_cl||''),status=String(cl.status||'unknown').toLowerCase();return {reported,expected,status,label:statusText(status)}}
  function renderHeaderState(){const head=document.querySelector('.admin-head>div');if(!head)return;let host=document.getElementById('dws-phase3-state');if(!host){host=document.createElement('div');host.id='dws-phase3-state';host.className='dws-phase3-state';head.appendChild(host)}const cl=clView(),rt=data?.runtime||{},state=lifecycleState(),busy=!!rt.busy;host.innerHTML=`<span class="dws-phase3-pill ${busy?'busy':''}">SERVER · ${esc(state)}</span><span class="dws-phase3-pill ${esc(cl.status)}">${esc(cl.reported||'CL unavailable')} · ${esc(cl.label)}</span>${cl.expected?`<span class="dws-phase3-pill">EXPECTED · ${esc(cl.expected)}</span>`:''}${rt.last_error?`<span class="dws-phase3-pill error">${esc(rt.last_error)}</span>`:''}`}
  function rowMarkup(row){const status=String(row.status||'unknown').toLowerCase(),version=[row.installed_version||'Unknown',row.available_version?`→ ${row.available_version}`:''].filter(Boolean).join(' '),dependency=(row.depends_on||[]).length?`Requires ${(row.depends_on||[]).map(x=>String(x).toUpperCase()).join(', ')}`:'No managed dependency',canUpdate=!!row.remote_update_supported&&!!row.update_available&&!row.dependency_problem,legacy=row.legacy_name?` · Internal identity: ${row.legacy_name}`:'',roles=(row.runtime_roles||[]).length?` · Role: ${(row.runtime_roles||[]).map(x=>String(x).toUpperCase()).join('/')}`:'';return `<article class="dws-core-row"><div><strong>${esc(row.name||row.id)}</strong><small>${esc(row.type||'Managed component')}${esc(legacy)}${esc(roles)}</small></div><div><small>${esc(row.physical_relationship||'Existing provider owns deployment')}</small><small>${esc(dependency)}</small></div><div><span class="dws-core-status ${esc(status)}">${esc(statusText(status))}</span><small>${esc(version)}</small></div><div class="dws-core-actions">${row.remote_update_supported?`<button data-core-update="${esc(row.id)}" data-update-available="${canUpdate?'1':'0'}">Update</button><button data-core-update="${esc(row.id)}" data-core-restart="1" data-update-available="${canUpdate?'1':'0'}">Update + Restart</button>`:'<small>Existing provider · no remote update source</small>'}</div><div class="dws-core-result" data-core-result="${esc(row.id)}"></div></article>`}
  function componentRows(group){const rows=(Array.isArray(data?.core_components)?data.core_components:[]).filter(row=>String(row.ui_group||'core_components')===group);return rows.map(rowMarkup).join('')||'<p class="muted">No managed components are reported for this group.</p>'}
  function bindCoreActions(){document.querySelectorAll('[data-core-update]').forEach(button=>button.onclick=async()=>{const component=String(button.dataset.coreUpdate||''),restart=button.dataset.coreRestart==='1',out=document.querySelector(`[data-core-result="${CSS.escape(component)}"]`);if(out){out.className='dws-core-result';out.textContent=`${restart?'Updating and restarting':'Updating'}…`}try{await command('core_update',{component,restart});if(out){out.className='dws-core-result success';out.textContent=`${component} update completed and was verified${restart?' with server restart':''}.`}await load()}catch(error){if(out){out.className='dws-core-result error';out.textContent=error.message||String(error)}applyActionState()}});applyActionState()}
  function decorateOverview(){if(tab!=='overview')return;const body=document.getElementById('tab-body');if(!body||document.getElementById('dws-cl-authority'))return;const cl=clView(),panel=document.createElement('div');panel.id='dws-cl-authority';panel.className='info';panel.style.marginTop='12px';panel.innerHTML=`<h3>Server version authority</h3>${kv('Reported CL',cl.reported||'Unavailable')}${kv('Expected CL',cl.expected||'Unknown')}${kv('CL status',cl.label)}${kv('Lifecycle',lifecycleState())}`;body.appendChild(panel)}
  function decorateMaintenance(){if(tab!=='maintenance')return;const body=document.getElementById('tab-body');if(!body||document.getElementById('dws-core-components-panel'))return;const panel=document.createElement('section');panel.id='dws-core-components-panel';panel.className='announcement';panel.style.marginTop='18px';panel.innerHTML=`<div class="toolbar"><div><strong>Managed Runtime</strong><div class="muted">Core Components and Tooling are separate logical groups over the same authoritative providers.</div></div><span class="${allowed('update')?'grant':'denied'}">${allowed('update')?'REMOTE UPDATES GRANTED':'READ ONLY'}</span></div>${runtimeBusy()?`<div class="dws-phase3-busy-note">${esc(lifecycleState())} is in progress. Conflicting lifecycle and core-update controls are locked.</div>`:''}<section class="dws-managed-section"><h4>Core Components</h4><div class="dws-core-components">${componentRows('core_components')}</div></section><section class="dws-managed-section"><h4>Tooling</h4><div class="dws-core-components">${componentRows('tooling')}</div></section>`;body.appendChild(panel);bindCoreActions()}
  renderTab=function(){legacyRenderTab();decorateOverview();decorateMaintenance();renderHeaderState();applyActionState()};
  load=async function(){const result=await legacyLoad();renderHeaderState();applyActionState();return result};
  renderHeaderState();applyActionState();
})();
</script>
'''.encode("utf-8")


def inject_remote_admin(page: bytes) -> bytes:
    """Append the runtime portal layer without replacing the proven WebGUI."""
    if not isinstance(page, (bytes, bytearray)):
        page = str(page or "").encode("utf-8")
    payload = bytes(page)
    if b'id="dws-phase3-runtime-script"' in payload:
        return payload
    marker = b"</body>"
    return payload.replace(marker, _EXTENSION + marker, 1) if marker in payload else payload + _EXTENSION
