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
async function assertPainted(win,marker='',requireVisibleText=false){
  await until(()=>renderer(win,"document.readyState==='complete'"),30000,'window load');
  const state=await until(()=>renderer(win,`(()=>{const body=document.body;const text=String(body?.innerText||'').trim();const rect=body?.getBoundingClientRect?.();return {text,html:String(body?.innerHTML||''),width:Number(rect?.width||0),height:Number(rect?.height||0),ready:document.readyState};})()`),30000,'window body');
  if(!state.html||state.width<100||state.height<100)throw new Error(`Window did not paint a usable surface: ${JSON.stringify({width:state.width,height:state.height,html:state.html.length,text:state.text.slice(0,120)})}`);
  if(requireVisibleText&&!state.text)throw new Error('Window loaded DOM but rendered no visible text; possible black-window regression.');
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
  await renderer(main,"window.__DWSYNC_SURFACE_EVENTS__=[];window.dragonwilds.onManagedDialogEvent((payload)=>window.__DWSYNC_SURFACE_EVENTS__.push(payload));true");

  const openManaged=async(iteration,{runtime=false}={})=>{
    const id=`surface-managed-${iteration}`;
    const before=new Set(BrowserWindow.getAllWindows().map((item)=>item.id));
    const marker=runtime?`RUNTIME_CONSOLE_SURFACE_OK_${iteration}`:`MANAGED_SURFACE_OK_${iteration}`;
    const html=runtime
      ? `<div class="modal-header"><h2>Runtime Console Surface Test</h2></div><div class="modal-body runtime-console-app"><nav class="runtime-console-tabs"><button data-runtime-console-tab="console">Console</button><button data-runtime-console-tab="runeschema">RuneSchema</button></nav><section class="unified-launch-console"><div class="unified-launch-console-stream">${marker}</div><input id="surface-field-${iteration}" value="painted"></section></div><div class="modal-footer"><button data-close-modal>Close</button></div>`
      : `<div class="modal-header"><h2>Managed Surface Test</h2></div><div class="modal-body"><p>${marker}</p><input id="surface-field-${iteration}" value="painted"></div><div class="modal-footer"><button data-close-modal>Close</button></div>`;
    const started=Date.now();
    const result=await renderer(main,`window.dragonwilds.openManagedDialog({id:${JSON.stringify(id)},kind:${JSON.stringify(runtime?'runtime-console':'window-surface-test')},title:${JSON.stringify(runtime?'Runtime Console Surface Test':'Managed Surface Test')},html:${JSON.stringify(html)}})`);
    if(!result?.id)throw new Error(`Managed dialog did not return an id: ${JSON.stringify(result)}`);
    const child=await until(()=>BrowserWindow.getAllWindows().find((item)=>!before.has(item.id)&&!item.isDestroyed()),30000,'managed child window');
    await assertPainted(child,marker,true);
    if(runtime&&Date.now()-started>5000)throw new Error(`Runtime Console managed surface took ${Date.now()-started}ms to paint; expected the lightweight host within 5 seconds.`);
    const hostUrl=child.webContents.getURL();
    if(!/dialog-host\.html/i.test(hostUrl))throw new Error(`Managed dialog used unexpected host: ${hostUrl}`);
    await renderer(child,`(()=>{const field=document.getElementById('surface-field-${iteration}');field.value='interactive-${iteration}';field.dispatchEvent(new Event('input',{bubbles:true}));const button=document.querySelector('[data-close-modal]');button.dispatchEvent(new MouseEvent('click',{bubbles:true}));return true;})()`);
    await until(()=>renderer(main,`window.__DWSYNC_SURFACE_EVENTS__.some((event)=>event.id===${JSON.stringify(result.id)}&&event.type==='input'&&event.fields?.[${JSON.stringify(`surface-field-${iteration}`)}]?.value===${JSON.stringify(`interactive-${iteration}`)})&&window.__DWSYNC_SURFACE_EVENTS__.some((event)=>event.id===${JSON.stringify(result.id)}&&event.type==='click')`),5000,'managed window input/click bridge');
    await renderer(main,`window.dragonwilds.closeManagedDialog(${JSON.stringify(result.id)})`);
    await until(()=>child.isDestroyed()||!BrowserWindow.getAllWindows().includes(child),10000,'managed dialog close');
  };

  const openDetached=async({route,iteration,context,label})=>{
    const before=new Set(BrowserWindow.getAllWindows().map((item)=>item.id));
    const result=await renderer(main,`window.dragonwilds.openDetachedWindow({route:${JSON.stringify(route)},title:${JSON.stringify(`${label} ${iteration}`)},width:1100,height:760,context:${JSON.stringify(context)}})`);
    if(!result?.id)throw new Error(`${label} did not return a detached window id: ${JSON.stringify(result)}`);
    const child=await until(()=>BrowserWindow.getAllWindows().find((item)=>!before.has(item.id)&&!item.isDestroyed()),30000,`${label} child window`);
    await assertPainted(child,'',true);
    await until(()=>renderer(child,"!!document.querySelector('#app')"),30000,`${label} app shell`);
    const resolved=await renderer(child,"window.dragonwilds?.detachedContext?.()");
    if(String(resolved?.route||'')!==route)throw new Error(`${label} lost route context: ${JSON.stringify(resolved)}`);
    for(const [key,value] of Object.entries(context||{}))if(String(resolved?.context?.[key]??'')!==String(value))throw new Error(`${label} lost context ${key}: ${JSON.stringify(resolved)}`);
    await renderer(main,`window.dragonwilds.closeDetachedWindow(${JSON.stringify(result.id)})`);
    await until(()=>child.isDestroyed()||!BrowserWindow.getAllWindows().includes(child),10000,`${label} close`);
  };

  await openManaged(1);
  await openManaged(2);
  await openManaged(3,{runtime:true});
  await openManaged(4,{runtime:true});
  await openDetached({route:'settings',iteration:1,context:{settingsTab:'application'},label:'Detached Surface Test'});
  await openDetached({route:'settings',iteration:2,context:{settingsTab:'application'},label:'Detached Surface Test'});
  finish(0,'Window surfaces: PASS · managed dialogs, lightweight Runtime Console windows, and generic detached windows painted, closed, and reopened cleanly');
}).catch((error)=>finish(1,`Window surfaces: FAIL · ${error?.stack||error}`));
setTimeout(()=>finish(1,'Window surfaces: FAIL · 150 second timeout'),150000).unref?.();
