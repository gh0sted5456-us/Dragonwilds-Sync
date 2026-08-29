'use strict';

process.env.DWSYNC_TEST_MODE='1';
process.env.DWSYNC_DISABLE_UPDATE_CHECK='1';
const {app,BrowserWindow}=require('electron');
app.commandLine.appendSwitch('disable-gpu');

let finished=false;
function finish(code,message){if(finished)return;finished=true;process.exitCode=code;(code?console.error:console.log)(message);app.exit(code);}
const wait=(ms)=>new Promise((resolve)=>setTimeout(resolve,ms));
async function until(fn,timeout=30000,label='window surface'){const end=Date.now()+timeout;while(Date.now()<end){const value=await fn();if(value)return value;await wait(100);}throw new Error(`Timed out waiting for ${label}.`);}
async function renderer(win,source){return win.webContents.executeJavaScript(source,true);}
async function assertPainted(win,marker=''){
  await until(()=>renderer(win,"document.readyState==='complete'"),30000,'window load');
  const state=await until(()=>renderer(win,`(()=>{const body=document.body;const text=String(body?.innerText||'').trim();const rect=body?.getBoundingClientRect?.();return {text,html:String(body?.innerHTML||''),width:Number(rect?.width||0),height:Number(rect?.height||0),ready:document.readyState};})()`),30000,'window body');
  if(!state.html||state.width<100||state.height<100)throw new Error(`Window did not paint a usable surface: ${JSON.stringify({width:state.width,height:state.height,html:state.html.length,text:state.text.slice(0,120)})}`);
  if(marker&&!state.text.includes(marker))throw new Error(`Window painted but marker ${JSON.stringify(marker)} was missing: ${state.text.slice(0,240)}`);
}

app.on('web-contents-created',(_event,contents)=>{
  if(contents.getType()!=='window')return;
  contents.on('did-fail-load',(_event,code,description,url,isMainFrame)=>{if(isMainFrame!==false)finish(1,`Window surfaces: FAIL · load ${code} ${description} ${url}`);});
  contents.on('render-process-gone',(_event,details)=>{if(String(details?.reason||'')!=='clean-exit')finish(1,`Window surfaces: FAIL · renderer process ${details?.reason||'exited'}`);});
  contents.on('unresponsive',()=>finish(1,'Window surfaces: FAIL · a renderer became unresponsive'));
});

require('../electron/main.cjs');
app.whenReady().then(async()=>{
  const main=await until(()=>BrowserWindow.getAllWindows().find((item)=>!item.isDestroyed()),30000,'main window');
  await until(()=>renderer(main,"document.readyState==='complete'"),30000,'main renderer');
  await until(()=>renderer(main,"!!window.dragonwilds?.openManagedDialog&&!!window.dragonwilds?.openDetachedWindow"),30000,'window bridges');

  const openManaged=async(iteration)=>{
    const id=`surface-managed-${iteration}`;
    const before=new Set(BrowserWindow.getAllWindows().map((item)=>item.id));
    const result=await renderer(main,`window.dragonwilds.openManagedDialog({id:${JSON.stringify(id)},kind:'window-surface-test',title:'Managed Surface Test',html:'<div class="modal-header"><h2>Managed Surface Test</h2></div><div class="modal-body"><p>MANAGED_SURFACE_OK_${iteration}</p><input id="surface-field-${iteration}" value="painted"></div><div class="modal-footer"><button data-close-modal>Close</button></div>'})`);
    if(!result?.id)throw new Error(`Managed dialog did not return an id: ${JSON.stringify(result)}`);
    const child=await until(()=>BrowserWindow.getAllWindows().find((item)=>!before.has(item.id)&&!item.isDestroyed()),30000,'managed child window');
    await assertPainted(child,`MANAGED_SURFACE_OK_${iteration}`);
    const hostUrl=child.webContents.getURL();
    if(!/dialog-host\.html/i.test(hostUrl))throw new Error(`Managed dialog used unexpected host: ${hostUrl}`);
    await renderer(main,`window.dragonwilds.closeManagedDialog(${JSON.stringify(result.id)})`);
    await until(()=>child.isDestroyed()||!BrowserWindow.getAllWindows().includes(child),10000,'managed dialog close');
  };

  const openDetached=async(iteration)=>{
    const before=new Set(BrowserWindow.getAllWindows().map((item)=>item.id));
    const result=await renderer(main,`window.dragonwilds.openDetachedWindow({route:'settings',title:'Detached Surface Test ${iteration}',width:980,height:700,context:{settingsTab:'application'}})`);
    if(!result?.id)throw new Error(`Detached window did not return an id: ${JSON.stringify(result)}`);
    const child=await until(()=>BrowserWindow.getAllWindows().find((item)=>!before.has(item.id)&&!item.isDestroyed()),30000,'detached renderer window');
    await assertPainted(child);
    await until(()=>renderer(child,"!!document.querySelector('#app')"),30000,'detached app shell');
    const context=await renderer(child,"window.dragonwilds?.detachedContext?.()");
    const resolved=await context;
    if(String(resolved?.route||'')!=='settings')throw new Error(`Detached renderer lost route context: ${JSON.stringify(resolved)}`);
    await renderer(main,`window.dragonwilds.closeDetachedWindow(${JSON.stringify(result.id)})`);
    await until(()=>child.isDestroyed()||!BrowserWindow.getAllWindows().includes(child),10000,'detached window close');
  };

  await openManaged(1);
  await openManaged(2);
  await openDetached(1);
  await openDetached(2);
  finish(0,'Window surfaces: PASS · managed dialog and full detached renderer both painted, closed, and reopened cleanly');
}).catch((error)=>finish(1,`Window surfaces: FAIL · ${error?.stack||error}`));
setTimeout(()=>finish(1,'Window surfaces: FAIL · 120 second timeout'),120000).unref?.();
