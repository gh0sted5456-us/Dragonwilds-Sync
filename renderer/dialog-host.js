(() => {
  const params=new URLSearchParams(location.search); const dialogId=params.get('dialogId')||'';
  const content=document.getElementById('dialog-content'); const title=document.getElementById('dialog-title');
  let lastHtml=''; let wired=false;
  const fieldSnapshot=()=>{const out={}; content.querySelectorAll('input[id],textarea[id],select[id]').forEach((el)=>{out[el.id]={value:el.value,checked:!!el.checked,type:el.type||el.tagName.toLowerCase()};}); return out;};
  const descriptor=(el)=>{if(!el)return{}; if(el.id)return{id:el.id}; const data={}; for(const [k,v] of Object.entries(el.dataset||{}))data[k]=v; return{tag:String(el.tagName||'').toLowerCase(),data,text:String(el.textContent||'').trim().slice(0,120)};};
  const applyFields=(fields={})=>{for(const [id,state] of Object.entries(fields||{})){const el=document.getElementById(id);if(!el)continue;const activelyTyping=document.activeElement===el&&['text','password','search','email','url','tel','number','textarea'].includes(String(el.type||el.tagName).toLowerCase());if('value' in state&&!activelyTyping)el.value=state.value??'';if('checked' in state)el.checked=!!state.checked;}};
  const wire=()=>{
    if(wired)return;wired=true;
    for(const type of ['input','change'])content.addEventListener(type,(event)=>{const el=event.target.closest('input,textarea,select');if(el)window.dragonwilds.managedDialogEvent({id:dialogId,type,target:descriptor(el),fields:fieldSnapshot()});});
    content.addEventListener('click',(event)=>{const el=event.target.closest('button,a,[data-close-modal]');if(!el)return;event.preventDefault();window.dragonwilds.managedDialogEvent({id:dialogId,type:'click',target:descriptor(el),fields:fieldSnapshot()});});
  };
  const setContent=(payload={})=>{if(payload.theme)document.body.dataset.theme=payload.theme;if(payload.title)title.textContent=payload.title;if(payload.html!=null&&String(payload.html)!==lastHtml){lastHtml=String(payload.html);content.innerHTML=`<div class="modal">${lastHtml}</div>`;}wire();applyFields(payload.fields||{});};
  window.dragonwilds.managedDialogContent(dialogId).then(setContent).catch((error)=>{content.innerHTML=`<div class="empty-state">${String(error.message||error)}</div>`;});
  window.dragonwilds.onManagedDialogUpdate?.((payload)=>{if(payload.id===dialogId)setContent(payload);});
  document.getElementById('dlg-min').addEventListener('click',()=>window.dragonwilds.windowMinimize());
  document.getElementById('dlg-max').addEventListener('click',()=>window.dragonwilds.windowToggleMaximize());
  document.getElementById('dlg-close').addEventListener('click',()=>window.dragonwilds.windowClose());
})();
