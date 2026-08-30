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
  await win.webContents.executeJavaScript("document.querySelector('[data-route=\"worlds\"]')?.click()");
  await until(()=>win.webContents.executeJavaScript("!!document.querySelector('#add-world, #add-world-card')"),10000);
  await win.webContents.executeJavaScript("document.querySelector('#add-world, #add-world-card').click()");
  const connectNativeWindow=await until(()=>BrowserWindow.getAllWindows().find((item)=>item!==win&&!item.isDestroyed()),10000);
  await until(()=>connectNativeWindow.webContents.executeJavaScript("document.body?.dataset?.dialogHydration==='ready'"),10000);
  const connectWorldWindow=await until(()=>win.webContents.executeJavaScript(`(()=>{
    const surface=[...document.querySelectorAll('.modal-window, .managed-dialog-shadow')].find((item)=>item.textContent?.includes('Unified World Access'));
    if(!surface)return null;
    const tabs=[...surface.querySelectorAll('[data-connect-world-tab]')].map((item)=>item.dataset.connectWorldTab);
    const panels={};
    for(const key of tabs){surface.querySelector('[data-connect-world-tab="'+key+'"]')?.click();panels[key]=surface.querySelector('[data-connect-world-panel]')?.textContent?.trim()||'';}
    return {tabs,panels};
  })()`),10000);
  const expectedConnectTabs=['saved','lan','direct','import','host'];
  if(!connectNativeWindow.isVisible()||expectedConnectTabs.some((key)=>!connectWorldWindow.tabs.includes(key)))throw new Error(`Unified Connect to World window is incomplete: ${JSON.stringify(connectWorldWindow)}`);
  for(const key of expectedConnectTabs){if(!connectWorldWindow.panels[key])throw new Error(`Unified Connect to World tab ${key} rendered an empty panel.`);}
  await win.webContents.executeJavaScript(`[...document.querySelectorAll('.modal-window, .managed-dialog-shadow')].find((item)=>item.textContent?.includes('Unified World Access'))?.querySelector('[data-close-modal]')?.click()`);
  await win.webContents.executeJavaScript("window.__DWSYNC_SWAP_METRICS__?.clear()");
  const selectors=[
    '[data-route="profile"]','[data-profile-tab="characters"]','[data-profile-tab="user"]',
    '[data-route="world-management"]','[data-world-management-tab="game-setup"]','[data-world-management-tab="worlds"]',
    '[data-route="settings"]','[data-settings-tab="mods"]','[data-settings-tab="application"]',
    '[data-route="help"]','[data-route="webhost"]','[data-webhost-tab="manifest"]',
    '[data-webhost-tab="remote"]','[data-webhost-tab="live"]','[data-webhost-tab="settings"]','[data-route="worlds"]',
  ];
  for(let round=0;round<3;round+=1){for(const selector of selectors){
    const clicked=await win.webContents.executeJavaScript(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)return false;el.click();return true;})()`);
    if(clicked)await wait(260);
  }}
  const assertSyncTabSticks=async(key)=>{
    const exists=await win.webContents.executeJavaScript(`!!document.querySelector('.webhost-tabs [data-webhost-tab="${key}"]')`);
    if(!exists)return;
    await win.webContents.executeJavaScript(`document.querySelector('.webhost-tabs [data-webhost-tab="${key}"]').click()`);
    await wait(450);
    const selected=await win.webContents.executeJavaScript(`document.querySelector('.webhost-tabs [data-webhost-tab="${key}"]')?.classList.contains('active')===true`);
    if(!selected)throw new Error(`Sync tab ${key} repainted or lost its selected state.`);
  };
  await win.webContents.executeJavaScript("document.querySelector('[data-route=\"webhost\"]')?.click()");
  const previewLabelFirstFrame=await win.webContents.executeJavaScript(`document.querySelector('.webhost-tabs [data-webhost-tab="live"]')?.textContent?.trim()||''`);
  if(previewLabelFirstFrame && previewLabelFirstFrame!=='WebGUI Preview')throw new Error(`Sync preview tab first rendered as "${previewLabelFirstFrame}" instead of "WebGUI Preview".`);
  await wait(260);
  const previewLabelSettled=await win.webContents.executeJavaScript(`document.querySelector('.webhost-tabs [data-webhost-tab="live"]')?.textContent?.trim()||''`);
  if(previewLabelSettled && previewLabelSettled!=='WebGUI Preview')throw new Error(`Sync preview tab settled as "${previewLabelSettled}" instead of "WebGUI Preview".`);
  await assertSyncTabSticks('manifest');
  await assertSyncTabSticks('remote');
  await assertSyncTabSticks('live');
  await assertSyncTabSticks('settings');
  await win.webContents.executeJavaScript("document.querySelector('[data-route=\"settings\"]')?.click()");
  await wait(260);
  const stableSettings=await win.webContents.executeJavaScript(`(()=>{
    const header=document.querySelector('.main>.content>.page-header');
    const nav=document.querySelector('.settings-layout>.settings-nav');
    const subnav=document.querySelector('.settings-layout>div>.settings-subnav');
    if(!header||!nav||!subnav)return {ok:false,stage:'initial'};
    window.__DWSYNC_SETTINGS_STABLE__={header,nav,subnav};
    document.querySelector('[data-settings-tab="advanced"]')?.click();
    const first=window.__DWSYNC_SETTINGS_STABLE__.header===document.querySelector('.main>.content>.page-header')&&window.__DWSYNC_SETTINGS_STABLE__.nav===document.querySelector('.settings-layout>.settings-nav');
    document.querySelector('[data-settings-tab="application"]')?.click();
    const second=window.__DWSYNC_SETTINGS_STABLE__.header===document.querySelector('.main>.content>.page-header')&&window.__DWSYNC_SETTINGS_STABLE__.nav===document.querySelector('.settings-layout>.settings-nav');
    const restoredSubnav=document.querySelector('.settings-layout>div>.settings-subnav');
    window.__DWSYNC_SETTINGS_STABLE__.subnav=restoredSubnav;
    document.querySelector('[data-application-settings-tab="runtimes"]')?.click();
    const third=window.__DWSYNC_SETTINGS_STABLE__.subnav===document.querySelector('.settings-layout>div>.settings-subnav');
    return {ok:first&&second&&third,first,second,third};
  })()`);
  if(!stableSettings.ok)throw new Error(`Settings shell repainted during category swap: ${JSON.stringify(stableSettings)}`);
  await until(()=>win.webContents.executeJavaScript("!!document.querySelector('[data-phase6-settings-community]')"),5000);
  await win.webContents.executeJavaScript("document.querySelector('[data-phase6-settings-community]').click()");
  await until(()=>win.webContents.executeJavaScript("!!document.querySelector('.phase6-community-page')"),5000);
  await win.webContents.executeJavaScript("document.querySelector('[data-settings-tab=\"integrations\"]').click()");
  const communityExit=await until(()=>win.webContents.executeJavaScript(`(()=>({
    integrationActive:document.querySelector('[data-settings-tab="integrations"]')?.classList.contains('active')===true,
    integrationContent:!!document.querySelector('.integration-overview'),
    communityGone:!document.querySelector('.phase6-community-page')
  }))()`),5000);
  if(!communityExit.integrationActive||!communityExit.integrationContent||!communityExit.communityGone)throw new Error(`Community prevented navigation to Integrations: ${JSON.stringify(communityExit)}`);
  await wait(300);
  const metrics=await win.webContents.executeJavaScript("window.__DWSYNC_SWAP_METRICS__?.snapshot()||null");
  if(!metrics||metrics.count<5)throw new Error(`Too few measured swaps: ${JSON.stringify(metrics)}`);
  console.log(JSON.stringify({...metrics,rows:metrics.rows.slice(-20)},null,2));
  if(metrics.sync_p95_ms>100)throw new Error(`Synchronous swap p95 ${metrics.sync_p95_ms} ms exceeds 100 ms test ceiling.`);
  if(metrics.settled_p95_ms>1200)throw new Error(`Click-to-settled p95 ${metrics.settled_p95_ms} ms exceeds 1200 ms integration ceiling.`);
  finish(0,`Navigation swap timing: PASS · ${metrics.count} swaps · sync p50/p95 ${metrics.sync_p50_ms}/${metrics.sync_p95_ms} ms · settled p50/p95 ${metrics.settled_p50_ms}/${metrics.settled_p95_ms} ms`);
}).catch((error)=>finish(1,`Navigation swap timing: FAIL · ${error?.stack||error}`));
setTimeout(()=>finish(1,'Navigation swap timing: FAIL · 60 second timeout'),60000).unref?.();
