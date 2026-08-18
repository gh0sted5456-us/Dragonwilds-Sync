(() => {
  'use strict';
  const bridge=window.dragonwilds;let queued=false;

  async function persistToggle(toggle){
    if(!bridge?.invoke)return;
    const state=await bridge.invoke('state.get',{}),application=state?.application||{},advanced=application.advanced||{},current=application.world_directory_host||{},currentRemote=current.remote_admin||{};
    const remoteEnabled=toggle.classList.contains('on'),webHostWorkspace=!!advanced.webhost_enabled;
    const payload={...current,remote_admin:{...currentRemote,enabled:remoteEnabled}};
    if(!webHostWorkspace){
      // A target can run Remote Server without publishing a public World site.
      // Turning the target authority off must also release that remote-only
      // listener; otherwise the machine keeps a useless bound TCP socket.
      payload.directory_enabled=false;
      payload.enabled=remoteEnabled;
    }
    await bridge.invoke('application.world_directory_host.settings',payload);
  }

  function bind(){
    const toggle=document.querySelector('#toggle-webhost-remote-admin');
    if(!toggle||toggle.dataset.v2RemoteLifecycle==='1')return;
    toggle.dataset.v2RemoteLifecycle='1';
    toggle.addEventListener('click',()=>setTimeout(async()=>{
      toggle.disabled=true;
      try{await persistToggle(toggle);}
      catch(error){console.error('Remote Server toggle could not be persisted',error);}
      finally{toggle.disabled=false;}
    },0));
  }

  function schedule(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;bind();});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
})();
