// Run with Electron, not Node. Uses an isolated hidden renderer and no backend.
const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'dws-mapping-test-')));
app.disableHardwareAcceleration();
app.whenReady().then(async () => {
  const win = new BrowserWindow({ show: false, webPreferences: { sandbox: true, contextIsolation: true, backgroundThrottling: false } });
  try {
    await win.loadURL('data:text/html,<main><div id="machine-paths-card"></div></main>');
    await win.webContents.executeJavaScript(`
      window.__DWSYNC_STATE__={application:{machine_custom_paths:[]}};
      window.savedLocations=null;
      window.dragonwilds={
        invoke:async(method,payload)=>{
          if(method==='application.update'){
            window.savedLocations=payload.machine_custom_paths;
            return {application:{machine_custom_paths:payload.machine_custom_paths}};
          }
          return {};
        },
        pickDirectory:async()=>['C:','Mods','LootMenu'].join(String.fromCharCode(92))
      };
      void 0;
    `);
    await win.webContents.executeJavaScript(fs.readFileSync(path.join(__dirname, '../renderer/release-machine-mod-mapping.js'), 'utf8'));
    const result = await win.webContents.executeJavaScript(`(async()=>{
      const tick=()=>new Promise(resolve=>setTimeout(resolve,30));
      const manual=['D:','Manual Mods','Loot Menu'].join(String.fromCharCode(92));
      const assert=(value,message)=>{if(!value)throw Error(message);};
      await tick();
      document.querySelector('[data-machine-custom-add]').click();
      await tick();
      const label=document.querySelector('[data-machine-custom-label]');
      assert(label,'Add Location did not create a row');
      label.focus();
      for(const character of 'Loot Menu Config'){
        label.value+=character;
        label.dispatchEvent(new Event('input',{bubbles:true}));
        const activity=document.createElement('span');document.body.append(activity);
        await tick();activity.remove();
        assert(document.activeElement===label,'Typing lost focus after an unrelated repaint');
        assert(label.isConnected,'Typing replaced the input');
      }
      const browse=document.querySelector('[data-machine-custom-browse]');
      browse.focus();browse.click();await tick();
      let folder=document.querySelector('[data-machine-custom-path]');
      assert(folder.value.includes('LootMenu'),'Browse result was overwritten');
      folder.focus();folder.value=manual;
      folder.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('#machine-paths-card').remove();
      const card=document.createElement('div');card.id='machine-paths-card';document.querySelector('main').append(card);
      await tick();
      folder=document.querySelector('[data-machine-custom-path]');
      assert(folder.value===manual,'Manual draft lost on navigation');
      document.querySelector('[data-machine-custom-save]').click();await tick();
      assert(window.savedLocations?.[0]?.label==='Loot Menu Config','Label was truncated');
      assert(window.savedLocations?.[0]?.path===folder.value,'Manual path was not saved');
      assert(window.__DWSYNC_STATE__.application.machine_custom_paths[0].path===folder.value,'Saved state was not updated');
      document.querySelector('[data-machine-custom-add]').click();await tick();
      assert(document.querySelectorAll('[data-machine-custom-index]').length===2,'Second location was lost');
      document.querySelector('[data-machine-custom-remove="1"]').click();await tick();
      assert(document.querySelectorAll('[data-machine-custom-index]').length===1,'Remove Location was undone by repaint');
      return 'PASS: multi-character typing/focus, folder picker, navigation drafts, save, add and remove';
    })()`);
    console.log(result);
    await win.loadURL('data:text/html,<main></main>');
    await win.webContents.executeJavaScript(`
      document.body.innerHTML='<div class="modal"><input id="edit-private-ue4ss-root" value="manual"><input id="se-server-ue4ss-root"><input id="se-client-ue4ss-root"></div><section class="profile-storage-destinations"><button data-open-profile-mod-lane="Win64" data-profile-kind="server" data-profile-id="chosen">Open Win64 Folder</button></section>';
      window.dragonwilds={openPath:async()=>({ok:true})};
      window.dragonwilds.openProfileMods=async(...args)=>{window.openedProfile=args;return {ok:true,path:'profile/mods/Win64'};};
      window.dragonwilds.invoke=async()=>({player:{runtime_locations:[{label:'Win64',path:'C:/Game/Binaries/Win64',game_relative:'Binaries/Win64',eligible:true}]},server:{runtime_locations:[{label:'LootMenu',path:'D:/Server/Binaries/Win64/LootMenu',game_relative:'Binaries/Win64/LootMenu',eligible:true},{label:'Outside',eligible:false,reason:'Outside installation'}]}});
      void 0;
    `);
    await win.webContents.executeJavaScript(fs.readFileSync(path.join(__dirname, '../renderer/release-profile-mod-folders.js'), 'utf8'));
    console.log(await win.webContents.executeJavaScript(`(async()=>{
      const tick=()=>new Promise(resolve=>setTimeout(resolve,100));
      const assert=(value,message)=>{if(!value)throw Error(message);};
      await tick();
      const input=document.getElementById('edit-private-ue4ss-root');
      assert(input.value==='manual','Rendering replaced manual loader path');
      for(const [id,value] of [['edit-private-ue4ss-root','Binaries/Win64'],['se-server-ue4ss-root','D:/Server/Binaries/Win64/LootMenu'],['se-client-ue4ss-root','Binaries/Win64/LootMenu']]){
        const picker=document.querySelector('[data-profile-runtime-choice="'+id+'"]');
        assert(picker,'Missing saved-location picker '+id);
        picker.value=value;picker.dispatchEvent(new Event('change',{bubbles:true}));
        assert(document.getElementById(id).value===value,'Wrong destination '+id);
        assert(document.getElementById(id).dataset.userEdited==='1','Choice not marked edited');
      }
      assert(document.querySelector('[data-profile-runtime-choice="se-server-ue4ss-root"] option:last-child').disabled,'Outside path selectable');
      input.focus();input.value='custom draft';document.body.append(document.createElement('span'));await tick();
      assert(document.activeElement===input&&input.value==='custom draft','Repaint lost draft');
      document.querySelector('[data-open-profile-mod-lane]').click();await tick();
      assert(JSON.stringify(window.openedProfile)===JSON.stringify(['server','chosen','Win64']),'Opened wrong profile or lane');
      assert(document.querySelector('[data-profile-storage-status]').textContent.includes('Opened'),'Missing folder feedback');
      return 'PASS: saved locations, relative client paths, absolute host paths, draft persistence and explicit Win64 profile folder';
    })()`));
    await win.loadURL('data:text/html,<main></main>');
    const appSource=fs.readFileSync(path.join(__dirname,'../renderer/app-v2.js'),'utf8');
    const syncFunction=appSource.slice(appSource.indexOf('  async function runWorldSyncJob('),appSource.indexOf('  function worldSaveDownloadPolicy('));
    await win.webContents.executeJavaScript(`
      window.state={data:{application:{}},operation:null};window.calls=[];
      window.render=()=>{};window.toast=()=>{};window.updateOperationProgress=()=>{};
      window.escapeHtml=value=>String(value);window.setData=value=>{state.data=value;};
      window.closeDesktopWindow=win=>win.remove();
      window.showModal=(html,options)=>{if(options.native!==false)throw Error('Migration must be embedded');const div=document.createElement('div');div.innerHTML=html;document.body.append(div);return div;};
      window.api={invoke:async(method,params)=>{calls.push({method,params});if(method.endsWith('.preview'))return {file_count:2,manifest_fingerprint:'hash',paths:['UE4SS/Mods','RuneSchema/mods','Paks/~mods']};if(method.endsWith('.apply'))return {ok:true};if(method.endsWith('.start'))return {job_id:'test'};return {status:'complete',response:{ok:true}};}};
      ${syncFunction}
      window.testSync=runWorldSyncJob;
      void 0;
    `);
    console.log(await win.webContents.executeJavaScript(`(async()=>{
      const tick=()=>new Promise(resolve=>setTimeout(resolve,50));
      const assert=(value,message)=>{if(!value)throw Error(message);};
      let pending=testSync({id:'server'},'sync').catch(error=>({cancelled:true}));await tick();
      document.querySelector('[data-migration-choice="cancel"]').click();await pending;
      assert(!calls.some(c=>c.method.endsWith('.start')||c.method.endsWith('.apply')),'Cancel changed files or launched sync');
      pending=testSync({id:'server'},'sync');await tick();
      document.querySelector('[data-migration-disable]').checked=true;
      document.querySelector('[data-migration-choice="continue"]').click();await pending;
      const choice=calls.find(c=>c.method.endsWith('.apply')).params;
      assert(choice.choice==='continue'&&choice.disable_warning===true,'Wrong per-server consent');
      assert(calls.findIndex(c=>c.method.endsWith('.apply'))<calls.findIndex(c=>c.method.endsWith('.start')),'Sync started before consent');
      return 'PASS: embedded migration warning, cancellation, per-server suppression and consent-before-sync';
    })()`));
    win.destroy();app.exit(0);
  } catch(error) {
    console.error(error);win.destroy();app.exit(1);
  }
});
