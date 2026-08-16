const { app, BrowserWindow, session } = require('electron');
const fs = require('fs');
const path = require('path');

const urlIndex = process.argv.findIndex((value, index) => index > 0 && /^https?:\/\//i.test(String(value)));
const base = String(process.env.DWS_WEBHOST_CAPTURE_BASE || (urlIndex >= 0 ? process.argv[urlIndex] : '') || 'http://127.0.0.1:27181').replace(/\/$/, '');
const output = path.resolve(process.env.DWS_WEBHOST_CAPTURE_OUTPUT || (urlIndex >= 0 ? process.argv[urlIndex + 1] : '') || path.join(__dirname, '..', 'release', 'screenshots'));
const logPath = path.join(__dirname, '..', 'capture-webhost.log');
fs.writeFileSync(logPath, `argv=${JSON.stringify(process.argv)}\nbase=${base}\noutput=${output}\n`);
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function shot(win, name) {
  await wait(700);
  const image = await win.webContents.capturePage();
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, name), image.toPNG());
}

app.whenReady().then(async () => {
  fs.appendFileSync(logPath, 'ready\n');
  const partition = 'dws-webhost-help-' + Date.now();
  const webSession = session.fromPartition(partition, { cache: false });
  const win = new BrowserWindow({ show: false, width: 1600, height: 1000, backgroundColor: '#090c0d',
    webPreferences: { session: webSession, contextIsolation: true, nodeIntegration: false, sandbox: true } });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  await win.loadURL(base + '/servers');
  fs.appendFileSync(logPath, 'loaded servers\n');
  await shot(win, '18-directory-public.png');
  await win.loadURL(base + '/admin/login');
  await shot(win, 'WebHost-Server-Admin-Login.png');
  await win.webContents.executeJavaScript(`fetch('/api/v1/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({world_name:'Effing Desync',password:'preview'})}).then(r=>r.json())`);
  await win.loadURL(base + '/admin/server');
  await shot(win, '28-webhost-preview.png');
  await win.webContents.executeJavaScript(`document.querySelector('[data-tab="mods"]').click()`);
  await shot(win, '19-webhost-mods.png');
  await win.webContents.executeJavaScript(`document.querySelector('[data-tab="config"]').click()`);
  await shot(win, 'WebHost-Remote-Config.png');
  await win.webContents.executeJavaScript(`document.querySelector('[data-tab="audit"]').click()`);
  await shot(win, 'WebHost-Remote-Audit.png');
  await win.webContents.executeJavaScript(`fetch('/api/v1/admin/logout',{method:'POST'}).then(()=>fetch('/api/v1/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({world_name:'Effing Desync',username:'observer',password:'preview'})})).then(r=>r.json())`);
  await win.loadURL(base + '/admin/server');
  await win.webContents.executeJavaScript(`document.querySelector('[data-tab="mods"]').click()`);
  await shot(win, '22-webhost-permission.png');
  win.setSize(430, 900);
  await win.loadURL(base + '/servers');
  await shot(win, '20-webhost-mobile.png');
  await win.webContents.executeJavaScript(`document.getElementById('mobile-filter-open').click()`);
  await shot(win, 'WebHost-Public-Mobile-Filters.png');
  await win.loadURL(base + '/admin/login');
  await shot(win, '23-webhost-login-mobile.png');
  await win.webContents.executeJavaScript(`fetch('/api/v1/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({world_name:'Effing Desync',password:'preview'})}).then(r=>r.json())`);
  await win.loadURL(base + '/admin/server');
  await shot(win, 'WebHost-Remote-Mobile.png');
  await win.loadURL(base + '/servers/sync-effing');
  await shot(win, 'WebHost-World-Detail-Mobile.png');
  win.destroy();
  app.quit();
}).catch((error) => { fs.appendFileSync(logPath, `error=${error?.stack||error}\n`); console.error(error); app.exit(1); });
