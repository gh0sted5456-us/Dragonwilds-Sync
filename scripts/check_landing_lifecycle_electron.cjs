'use strict';
// Exercise the complete shipped renderer, not a source-string splash assertion.
const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
process.env.DWSYNC_TEST_MODE = '1';
process.env.DWSYNC_DISABLE_UPDATE_CHECK = '1';
process.env.DRAGONWILDS_SYNC_APPDATA = fs.mkdtempSync(path.join(os.tmpdir(), 'dws-landing-test-'));
app.setPath('userData', path.join(process.env.DRAGONWILDS_SYNC_APPDATA, 'electron'));
app.commandLine.appendSwitch('disable-gpu');
app.on('will-quit', () => { if(process.exitCode)app.exit(process.exitCode); });
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, label) {
  const end=Date.now()+15000;
  while(Date.now()<end){const value=await check();if(value)return value;await wait(80);}
  throw new Error(`Timed out: ${label}`);
}
let failure = '';
app.on('web-contents-created', (_event, contents) => {
  contents.on('console-message', event => {
    if (/Uncaught|SyntaxError|ReferenceError|TypeError/.test(event.message || '')) failure ||= event.message;
  });
});
require('../electron/main.cjs');
let updateChecks = 0;
let updateMode = 'available';
ipcMain.removeHandler('dragonwilds:app-update-check');
ipcMain.handle('dragonwilds:app-update-check', () => {
  updateChecks += 1;
  if(updateMode==='error')throw new Error('Offline test');
  if(updateMode==='current')return {available:false,latestVersion:'3.5.4'};
  return {available:true,latestVersion:'999.0.0',name:'Landing test update',notes:'Test only; no download performed.'};
});
app.whenReady().then(async () => {
  let win;
  const deadline = Date.now() + 45000;
  let surface;
  while (Date.now() < deadline) {
    win = BrowserWindow.getAllWindows().find(item => !item.isDestroyed());
    if (win) surface = await win.webContents.executeJavaScript(`({entry:!!document.querySelector('#enter-launcher'), shell:!!document.querySelector('#app > .sidebar'), text:document.querySelector('#app')?.textContent?.slice(0,400)})`);
    if (surface?.entry || surface?.shell) break;
    await wait(100);
  }
  assert.ok(surface?.entry && !surface.shell, `Normal launch must stop at the landing page: ${JSON.stringify(surface)}; ${failure}`);
  await wait(2500);
  assert.equal(await win.webContents.executeJavaScript(`!!document.querySelector('#enter-launcher') && !document.querySelector('#app > .sidebar')`), true, 'Hydration must not bypass Enter');
  assert.equal(failure, '');
  assert.ok(updateChecks > 0, 'Main landing must check application releases');
  assert.equal(await win.webContents.executeJavaScript(`!!document.querySelector('#splash-update-now') && document.querySelector('[data-landing-update-status]').textContent.includes('Landing test update')`), true);
  assert.equal(await win.webContents.executeJavaScript(`!!document.querySelector('script[data-dws-monaco-loader]')`), false, 'Landing must not load the editor');
  assert.equal(await win.webContents.executeJavaScript(`getComputedStyle(document.querySelector('.fantasy-entry'),'::before').backgroundImage.includes('animated-splash.webp')`), true);
  fs.mkdirSync(path.join(__dirname,'../test-results'),{recursive:true});
  fs.writeFileSync(path.join(__dirname,'../test-results/landing-lifecycle.png'),(await win.webContents.capturePage()).toPNG());
  await win.webContents.executeJavaScript(`document.querySelector('#enter-launcher').click()`);
  await wait(500);
  assert.equal(await win.webContents.executeJavaScript(`!!document.querySelector('#app > .sidebar')`), true);
  // The first-run profile dialog must not be replaced by an app reopen.
  app.emit('second-instance', {}, [process.execPath]);
  await wait(200);
  assert.equal(await win.webContents.executeJavaScript(`!!document.querySelector('#app > .sidebar')`), true);
  const dialog=BrowserWindow.getAllWindows().find(item=>item!==win&&!item.isDestroyed());
  assert.ok(dialog, 'First-run identity dialog should be native');
  await until(()=>dialog.webContents.executeJavaScript(`document.body?.dataset?.dialogHydration==='ready' && !!document.querySelector('#save-profile')`),'identity dialog hydration');
  await dialog.webContents.executeJavaScript(`const name=document.querySelector('#p-name');name.value='Lifecycle Test';name.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#save-profile').click()`);
  await until(()=>dialog.isDestroyed(),'identity save and close');
  const guided=await until(()=>BrowserWindow.getAllWindows().find(item=>item!==win&&!item.isDestroyed()),'guided setup window');
  await until(()=>guided.webContents.executeJavaScript(`document.body?.dataset?.dialogHydration==='ready'`),'guided setup hydration');
  guided.close();
  await until(()=>win.webContents.executeJavaScript(`document.querySelector('#modal-root').children.length===0`),'guided setup close');
  app.emit('second-instance', {}, [process.execPath]);
  await wait(300);
  const reopened = await win.webContents.executeJavaScript(`({entry:!!document.querySelector('#enter-launcher'),dialogs:document.querySelector('#modal-root').textContent.slice(0,250)})`);
  assert.equal(reopened.entry, true, `Explicit reopen must restore the landing page: ${JSON.stringify(reopened)}`);
  await until(()=>win.webContents.executeJavaScript(`!document.querySelector('#check-application-update')?.disabled`),'reopen update check');
  updateMode='error';
  await win.webContents.executeJavaScript(`document.querySelector('#check-application-update').click()`);
  await until(()=>win.webContents.executeJavaScript(`document.querySelector('[data-landing-update-status]').textContent.includes('Offline test')`),'visible update error');
  assert.equal(await win.webContents.executeJavaScript(`document.querySelector('#enter-launcher').disabled`),false,'Offline update checks cannot prevent Enter');
  updateMode='current';
  await win.webContents.executeJavaScript(`document.querySelector('#check-application-update').click()`);
  await until(()=>win.webContents.executeJavaScript(`document.querySelector('[data-landing-update-status]').textContent.includes('up to date')`),'successful update retry');
  assert.equal(await win.webContents.executeJavaScript(`window.__DWSYNC_MONACO__.warm().then(monaco=>!!monaco.editor?.create)`),true,'Editor must still load on demand');
  assert.equal(failure, '');
  console.log('Full renderer landing, update/error/retry, lazy editor, Enter, protected dialog, and reopen: PASS');
  app.quit();
}).catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
  app.quit();
});
