'use strict';
// Run the shipped Save Manager function against Chromium DOM/events with a
// fixture API. No real profiles, network calls, or saves are modified.
const {app,BrowserWindow}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
app.commandLine.appendSwitch('disable-gpu');
app.on('will-quit',()=>{if(process.exitCode)app.exit(process.exitCode);});
app.whenReady().then(async()=>{
  const win=new BrowserWindow({show:false,webPreferences:{contextIsolation:true,nodeIntegration:false}});
  await win.loadURL('data:text/html,<div id="modal-root"></div>');
  const source=fs.readFileSync(path.join(__dirname,'../renderer/app-v2.js'),'utf8');
  const start=source.indexOf('  async function openSaveManagement(');
  const end=source.indexOf('  async function requestConnectedWorldSave(',start);
  assert.ok(start>0&&end>start);
  const result=await win.webContents.executeJavaScript(`(async()=>{
    const modalRoot=document.querySelector('#modal-root');
    const calls=[];const notices=[];
    const escapeHtml=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
    const formatBytes=value=>value+' B';
    const toast=(...args)=>notices.push(args);
    const managedConfirm=async()=>true;
    const closeModal=()=>{};
    const showModal=html=>{modalRoot.innerHTML=html;return modalRoot;};
    const api={invoke:async(method,params)=>{
      calls.push({method,params});
      if(method==='save.management.list')return {player_backups:[{id:'alice/Hero/old.rsdwl'}],player_backup_groups:[{id:'alice',name:'Hero',revisions:[{id:'alice/Hero/old.rsdwl',name:'old.rsdwl',mtime:1,size:100}]}]};
      return {ok:true};
    }};
    ${source.slice(start,end)}
    await openSaveManagement({id:'host-world',name:'Test World'},'server');
    const history=modalRoot.querySelector('.save-player-history');
    history.querySelector('summary').click();
    const opened=history.open;
    const send=history.querySelector('[data-save-manager-player]');
    const label=send.textContent;
    send.click();await new Promise(resolve=>setTimeout(resolve,100));
    return {opened,label,calls,notices};
  })()`);
  assert.equal(result.opened,true,'Player history click must expand');
  assert.equal(result.label,'Send to Player');
  assert.ok(result.calls.some(row=>row.method==='save.management.player.queue'&&row.params.profile_id==='host-world'&&row.params.revision_id==='alice/Hero/old.rsdwl'));
  assert.ok(!result.calls.some(row=>row.method==='save.management.player.restore'),'Send must not perform a local rollback');
  console.log('Save Manager Chromium history expansion and profile-bound Send action: PASS');
  app.quit();
}).catch(error=>{console.error(error);process.exitCode=1;app.quit();});
