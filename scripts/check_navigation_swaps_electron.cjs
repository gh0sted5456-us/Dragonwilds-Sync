'use strict';

process.env.DWSYNC_TEST_MODE='1';
process.env.DWSYNC_DISABLE_UPDATE_CHECK='1';
const {app,BrowserWindow}=require('electron');
app.commandLine.appendSwitch('disable-gpu');

let finished=false;
function finish(code,message){if(finished)return;finished=true;process.exitCode=code;(code?console.error:console.log)(message);app.exit(code);}
const wait=(ms)=>new Promise((resolve)=>setTimeout(resolve,ms));
async function until(fn,timeout=20000){const end=Date.now()+timeout;while(Date.now()<end){const value=await fn();if(value)return value;await wait(80);}throw new Error('Timed out waiting for the renderer.');}

app.on('web-contents-created',(_event,contents)=>{
  if(contents.getType()!=='window')return;
  contents.on('console-message',(event,level,legacyMessage,lineNumber,sourceId)=>{
    const params=event&&typeof event==='object'?event:{};
    const message=String(params.message||legacyMessage||'');
    if(!/Uncaught|SyntaxError|ReferenceError|TypeError/i.test(message))return;
    const source=params.sourceId||sourceId||'renderer';
    const line=params.lineNumber||lineNumber||0;
    finish(1,`Navigation swap timing: FAIL · renderer error: ${message} (${source}:${line})`);
  });
  contents.on('render-process-gone',(_goneEvent,details)=>{
    if(String(details?.reason||'')!=='clean-exit')finish(1,`Navigation swap timing: FAIL · renderer process ${details?.reason||'exited'}`);
  });
});

require('../electron/main.cjs');
app.whenReady().then(async()=>{
  const win=await until(()=>BrowserWindow.getAllWindows().find((item)=>!item.isDestroyed()));
  await until(()=>win.webContents.executeJavaScript("document.readyState==='complete'"));
  await until(()=>win.webContents.executeJavaScript("!!document.querySelector('#app')"));
  const entryState=await until(()=>win.webContents.executeJavaScript("document.querySelector('.app-shell .sidebar')?'shell':(document.querySelector('#enter-launcher, #enter-app, [data-enter-app], .welcome-enter')?'enter':'')"),30000);
  if(entryState==='enter')await win.webContents.executeJavaScript("document.querySelector('#enter-launcher, #enter-app, [data-enter-app], .welcome-enter').click()");
  await until(()=>win.webContents.executeJavaScript("!!document.querySelector('.app-shell .sidebar')"),30000);
  await win.webContents.executeJavaScript("window.__DWSYNC_SWAP_METRICS__?.clear()");
  const selectors=[
    '[data-route="profile"]','[data-profile-tab="characters"]','[data-profile-tab="user"]',
    '[data-route="world-management"]','[data-world-management-tab="game-setup"]','[data-world-management-tab="worlds"]',
    '[data-route="settings"]','[data-settings-tab="mods"]','[data-settings-tab="application"]',
    '[data-route="help"]','[data-route="worlds"]',
  ];
  for(let round=0;round<3;round+=1){for(const selector of selectors){
    const clicked=await win.webContents.executeJavaScript(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)return false;el.click();return true;})()`);
    if(clicked)await wait(260);
  }}
  await wait(300);
  const metrics=await win.webContents.executeJavaScript("window.__DWSYNC_SWAP_METRICS__?.snapshot()||null");
  if(!metrics||metrics.count<5)throw new Error(`Too few measured swaps: ${JSON.stringify(metrics)}`);
  console.log(JSON.stringify({...metrics,rows:metrics.rows.slice(-20)},null,2));
  if(metrics.sync_p95_ms>100)throw new Error(`Synchronous swap p95 ${metrics.sync_p95_ms} ms exceeds 100 ms test ceiling.`);
  if(metrics.settled_p95_ms>1200)throw new Error(`Click-to-settled p95 ${metrics.settled_p95_ms} ms exceeds 1200 ms integration ceiling.`);
  finish(0,`Navigation swap timing: PASS · ${metrics.count} swaps · sync p50/p95 ${metrics.sync_p50_ms}/${metrics.sync_p95_ms} ms · settled p50/p95 ${metrics.settled_p50_ms}/${metrics.settled_p95_ms} ms`);
}).catch((error)=>finish(1,`Navigation swap timing: FAIL · ${error?.stack||error}`));
setTimeout(()=>finish(1,'Navigation swap timing: FAIL · 60 second timeout'),60000).unref?.();
