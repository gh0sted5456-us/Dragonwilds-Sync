(() => {
  const params=new URLSearchParams(location.search); const dialogId=params.get('dialogId')||'';
  if(params.get('nativeFrame')==='1')document.body.classList.add('native-frame-host');
  const content=document.getElementById('dialog-content'); const title=document.getElementById('dialog-title');
  let lastHtml=''; let wired=false;
  const fieldSnapshot=()=>{const out={}; content.querySelectorAll('input[id],textarea[id],select[id]').forEach((el)=>{out[el.id]={value:el.value,checked:!!el.checked,type:el.type||el.tagName.toLowerCase()};}); return out;};
  const descriptor=(el)=>{if(!el)return{}; if(el.id)return{id:el.id}; const data={}; for(const [k,v] of Object.entries(el.dataset||{}))data[k]=v; return{tag:String(el.tagName||'').toLowerCase(),data,text:String(el.textContent||'').trim().slice(0,120)};};
  const applyFields=(fields={})=>{for(const [id,state] of Object.entries(fields||{})){const el=document.getElementById(id);if(!el)continue;const activelyTyping=document.activeElement===el&&['text','password','search','email','url','tel','number','textarea'].includes(String(el.type||el.tagName).toLowerCase());if('value' in state&&!activelyTyping)el.value=state.value??'';if('checked' in state)el.checked=!!state.checked;}};
  const wire=()=>{
    if(wired)return;wired=true;
    for(const type of ['input','change'])content.addEventListener(type,(event)=>{const el=event.target.closest('input,textarea,select');if(!el)return;if(type==='input'&&el.maxLength>0){const counterId=String(el.getAttribute('aria-describedby')||'').trim();const counter=counterId&&document.getElementById(counterId);if(counter){const count=Array.from(el.value||'').length;counter.textContent=`${count} / ${el.maxLength} characters`;counter.classList.toggle('near-limit',count>=Math.floor(el.maxLength*.9));}}window.dragonwilds.managedDialogEvent({id:dialogId,type,target:descriptor(el),fields:fieldSnapshot()});});
    content.addEventListener('click',(event)=>{const el=event.target.closest('button,a,[data-close-modal]');if(!el)return;event.preventDefault();window.dragonwilds.managedDialogEvent({id:dialogId,type:'click',target:descriptor(el),fields:fieldSnapshot()});});
  };
  const setContent=(payload={})=>{if(!payload||typeof payload!=='object')return false;if(payload.theme)document.body.dataset.theme=payload.theme;if(payload.title)title.textContent=payload.title;if(payload.html!=null&&String(payload.html)!==lastHtml){lastHtml=String(payload.html);content.innerHTML=`<div class="modal">${lastHtml}</div>`;}wire();applyFields(payload.fields||{});return lastHtml.trim().length>0;};
  const showHydrationError=(message)=>{content.innerHTML=`<div class="empty-state"><strong>Window could not hydrate</strong><br/>${String(message||'No window content was returned.')}</div>`;document.body.dataset.dialogHydration='failed';};
  if(!dialogId){showHydrationError('The window did not receive a dialog identifier.');return;}
  if(!window.dragonwilds?.managedDialogContent){
    content.innerHTML='<div class="empty-state"><strong>Window bridge unavailable</strong><br/>Close this window and reopen the tool from Dragonwilds Sync.</div>';
    document.body.dataset.dialogHydration='failed';
    return;
  }
  const hydrate=async()=>{
    let lastError=null;
    for(let attempt=0;attempt<5;attempt+=1){
      try{
        const payload=await window.dragonwilds.managedDialogContent(dialogId);
        if(setContent(payload)){document.body.dataset.dialogHydration='ready';return;}
      }catch(error){lastError=error;}
      await new Promise((resolve)=>setTimeout(resolve,80*(attempt+1)));
    }
    showHydrationError(lastError?.message||'No window content was returned after several attempts.');
  };
  void hydrate();
  window.dragonwilds.onManagedDialogUpdate?.((payload)=>{if(payload.id===dialogId&&setContent(payload))document.body.dataset.dialogHydration='ready';});
  document.getElementById('dlg-min').addEventListener('click',()=>window.dragonwilds.windowMinimize());
  document.getElementById('dlg-max').addEventListener('click',()=>window.dragonwilds.windowToggleMaximize());
  document.getElementById('dlg-close').addEventListener('click',()=>window.dragonwilds?.windowClose?.()||window.close());
  document.addEventListener('keydown',(event)=>{if(event.key!=='Escape')return;event.preventDefault();event.stopImmediatePropagation();window.dragonwilds.windowClose();},true);
})();
