// Run with Electron, not Node. Uses an isolated hidden renderer and no backend.
const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'dws-mapping-test-')));
app.disableHardwareAcceleration();
app.whenReady().then(async () => {
  const win = new BrowserWindow({ show: false, webPreferences: { sandbox: true, contextIsolation: true } });
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
    win.destroy();app.exit(0);
  } catch(error) {
    console.error(error);win.destroy();app.exit(1);
  }
});
