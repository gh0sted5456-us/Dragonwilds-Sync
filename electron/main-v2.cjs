const { app, BrowserWindow, ipcMain, dialog, shell, clipboard, Tray, Menu, Notification, nativeImage, webContents, session, screen } = require('electron');
const http = require('http');
const crypto = require('crypto');
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { DiscordRichPresence } = require('./discord_rpc.cjs');
const { checkForUpdates, stageAndApply, detectMode, readAppliedUpdate, dismissAppliedUpdate } = require('./app_updater.cjs');
const { NexusAdapter } = require('./nexus_adapter.cjs');

function startupPerformanceSettings() {
  const defaults={hardware_acceleration:true,renderer_memory_mb:0};
  try {
    const base=process.env.DRAGONWILDS_SYNC_APPDATA || (process.platform==='win32'&&process.env.LOCALAPPDATA?path.join(process.env.LOCALAPPDATA,'DragonwildsSync'):'');
    if(!base)return defaults;
    const state=JSON.parse(fs.readFileSync(path.join(base,'launcher_v2.json'),'utf8'));
    const incoming=state?.application?.performance||{};
    const memory=[0,1024,2048,4096,8192].includes(Number(incoming.renderer_memory_mb))?Number(incoming.renderer_memory_mb):0;
    return {hardware_acceleration:incoming.hardware_acceleration!==false,renderer_memory_mb:memory};
  } catch (_) { return defaults; }
}

const startupPerformance=startupPerformanceSettings();
const safeGraphicsMode=process.argv.includes('--dws-safe-graphics');
if(!startupPerformance.hardware_acceleration||safeGraphicsMode)app.disableHardwareAcceleration();
if(startupPerformance.renderer_memory_mb)app.commandLine.appendSwitch('js-flags',`--max-old-space-size=${startupPerformance.renderer_memory_mb}`);

let rsdwToolkitRoot = '';
let rsdwToolkitServer = null;
let rsdwToolkitBaseUrl = '';
const rsdwGuestPreload = path.join(__dirname, 'rsdw_webview_preload.cjs');

function allowedToolkitNavigation(value) {
  try {
    const u = new URL(String(value || ''));
    if (u.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(u.hostname.toLowerCase())) return true;
    return u.protocol === 'https:' && ['rsdwtools.com', 'www.rsdwtools.com', 'rsdwmodel.com', 'www.rsdwmodel.com'].includes(u.hostname.toLowerCase());
  } catch (_) { return false; }
}

function allowedWebhostPreviewNavigation(value) {
  try { const u=new URL(String(value||'')); return u.protocol==='http:' && ['127.0.0.1','localhost'].includes(u.hostname.toLowerCase()); }
  catch (_) { return false; }
}

function secureAttachedWebview(event, webPreferences, params) {
  const preview=String(params.partition||'')==='persist:webhost-preview';
  if (preview) {
    if (!allowedWebhostPreviewNavigation(params.src)) { event.preventDefault(); return; }
    webPreferences.nodeIntegration=false; webPreferences.contextIsolation=true; webPreferences.sandbox=true; webPreferences.devTools=false;
    delete webPreferences.preload;
    return;
  }
  if (!allowedToolkitNavigation(params.src)) { event.preventDefault(); return; }
  webPreferences.nodeIntegration=false; webPreferences.contextIsolation=true; webPreferences.sandbox=true; webPreferences.preload=rsdwGuestPreload;
}


let mainWindow = null;
let quickWindow = null;
let minimalWindow = null;
const detachedWindows = new Map();
const managedDialogs = new Map();
let detachedCounter = 0;
const nexus = new NexusAdapter();
let tray = null;
let announcementWindow = null;
let announcementTimer = null;
let service = null;
let serviceBuffer = '';
let serviceStderrTail = '';
let requestCounter = 0;
const pending = new Map();
const DEFAULT_SERVICE_TIMEOUT_MS = 5 * 60 * 1000;
const LONG_SERVICE_TIMEOUT_MS = 20 * 60 * 1000;
const BACKGROUND_SERVICE_TIMEOUT_MS = 60 * 1000;
const discordPresence = new DiscordRichPresence();
let benchmarkTimer = null;
let backgroundTimer = null;
let schedulerTimer = null;
let rsdwModuleTimer = null;
let forceQuit = false;
let shutdownInProgress = false;
let shutdownComplete = false;
let visualShutdownStarted = false;
let pendingJoinRequest = null;
let backgroundSettings = { close_to_tray: true, start_minimized: false, notifications_enabled: true, announcement_overlay_enabled: true };
const notificationSeen = new Map();

function cryptoHashFile(file) { const hash=crypto.createHash('sha256'); hash.update(fs.readFileSync(file)); return hash.digest('hex'); }
function projectRoot() { return path.resolve(__dirname, '..'); }
function isElevated() {
  if (process.platform !== 'win32') return typeof process.getuid === 'function' ? process.getuid() === 0 : false;
  try {
    const value=execFileSync('powershell.exe',['-NoProfile','-NonInteractive','-Command','([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)'],{windowsHide:true,encoding:'utf8',timeout:4000});
    return String(value||'').trim().toLowerCase()==='true';
  } catch (_) { return false; }
}
function runtimePlatformStatus() {
  const compatibilityKeys=['WINEPREFIX','WINELOADERNOEXEC','WINEDLLPATH','STEAM_COMPAT_DATA_PATH','STEAM_COMPAT_CLIENT_INSTALL_PATH','PROTON_VERSION'];
  const compatibilityKey=compatibilityKeys.find((key)=>String(process.env[key]||'').trim())||'';
  const linux=process.platform==='linux';
  const wineProton=process.platform==='win32'&&!!compatibilityKey;
  return {platform:process.platform,elevated:isElevated(),canRelaunch:process.platform==='win32'&&!wineProton,linux,wineProton,compatibilityKey,showLinuxSettings:linux||wineProton};
}
function restartElevated() {
  if (process.platform !== 'win32') return Promise.resolve({ok:false,message:'Administrator relaunch is available on Windows. Use your desktop environment or sudo policy on Linux.'});
  if (isElevated()) return Promise.resolve({ok:true,alreadyElevated:true});
  // electron-builder portable apps execute from a temporary extraction path.
  // Relaunch the stable outer executable so elevation still works after this
  // process exits and its temporary directory is cleaned up.
  const unquote=(value)=>String(value||'').trim().replace(/^"(.*)"$/,'$1');
  const portableCandidate=unquote(process.env.PORTABLE_EXECUTABLE_FILE);
  const portable=portableCandidate&&fs.existsSync(portableCandidate)?portableCandidate:'';
  const launchPath=portable||process.execPath;
  if(!launchPath||!fs.existsSync(launchPath)) return Promise.reject(new Error(`Administrator relaunch executable was not found: ${launchPath||'(empty)'}`));
  const launchArgs=portable?[]:(app.isPackaged?process.argv.slice(1):[app.getAppPath(),...process.argv.slice(2)]);
  const workingDirectory=path.dirname(launchPath);
  const psQuote=(value)=>`'${String(value).replace(/'/g,"''")}'`;
  const windowsArgument=(value)=>{const raw=String(value);return /[\s"]/u.test(raw)?`"${raw.replace(/(\\*)"/g,'$1$1\\"').replace(/(\\+)$/,'$1$1')}"`:raw;};
  const argumentText=launchArgs.map(windowsArgument).join(' ');
  // ProcessStartInfo with UseShellExecute is the native ShellExecuteEx path
  // for the `runas` verb.  It is more reliable for electron-builder portable
  // executables than Start-Process (which can fail with code 1 when its
  // ArgumentList is empty or the portable path contains OneDrive characters).
  const script=`$ErrorActionPreference='Stop'; try { $psi = New-Object System.Diagnostics.ProcessStartInfo; $psi.FileName = ${psQuote(launchPath)}; $psi.WorkingDirectory = ${psQuote(workingDirectory)}; $psi.UseShellExecute = $true; $psi.Verb = 'runas'; $psi.Arguments = ${psQuote(argumentText)}; $p = [System.Diagnostics.Process]::Start($psi); if ($null -eq $p -or $p.Id -le 0) { throw 'Windows did not return an elevated process.' }; Write-Output ('DWS_ADMIN_PID=' + $p.Id); exit 0 } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }`;
  const encoded=Buffer.from(script,'utf16le').toString('base64');
  // Release the lock before Windows starts the elevated copy. Previously the
  // new process was rejected as a second instance and the old process then
  // quit, which made the application appear not to restart at all.
  app.releaseSingleInstanceLock();
  return new Promise((resolve,reject)=>{
    const helper=spawn('powershell.exe',['-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',encoded],{stdio:['ignore','pipe','pipe'],windowsHide:true,cwd:workingDirectory});
    let helperError='';
    helper.stdout?.on('data',(chunk)=>{helperError+=String(chunk||'');if(helperError.length>8192)helperError=helperError.slice(-8192);});
    helper.stderr?.on('data',(chunk)=>{helperError+=String(chunk||'');if(helperError.length>8192)helperError=helperError.slice(-8192);});
    helper.once('error',(error)=>{
      app.requestSingleInstanceLock();
      reject(error);
    });
    helper.once('exit',(code)=>{
      if(code!==0){
        app.requestSingleInstanceLock();
        const detail=helperError.replace(/\s+/g,' ').trim();
        const cancelled=code===1223||/cancel|canceled|cancelled|1223/i.test(detail);
        reject(new Error(cancelled?'Administrator relaunch was cancelled.':`Administrator relaunch failed with code ${code}.${detail?` Windows reported: ${detail.slice(0,600)}`:' Verify that the portable executable still exists and is not blocked by Windows Security.'}`));
        return;
      }
      forceQuit=true;
      setTimeout(()=>app.quit(),250);
      resolve({ok:true,relaunching:true,portable:!!portable});
    });
  });
}
function serviceCommand() {
  if (app.isPackaged) {
    const serviceName = process.platform === 'win32' ? 'DragonwildsSync.Service.exe' : 'DragonwildsSync.Service';
    const exe = path.join(process.resourcesPath, 'backend', serviceName);
    return { command: exe, args: [], cwd: path.dirname(exe) };
  }
  const script = path.join(projectRoot(), 'backend', 'dragonwilds_service.py');
  const configuredPython = String(process.env.DRAGONWILDS_SYNC_PYTHON || '').trim();
  if (configuredPython) return { command: configuredPython, args: [script], cwd: path.dirname(script) };
  if (process.platform === 'win32') return { command: 'py', args: ['-3', script], cwd: path.dirname(script) };
  return { command: 'python3', args: [script], cwd: path.dirname(script) };
}
function clearPendingTimer(waiter) { if (waiter?.timer) clearTimeout(waiter.timer); }
function rejectAllPending(message) { for (const waiter of pending.values()) { clearPendingTimer(waiter); waiter.reject(new Error(message)); } pending.clear(); }
function serviceTimeoutFor(method) {
  const name=String(method||'').toLowerCase();
  if(['world.discovery.heartbeat','client.background.tick','server.scheduler.tick','server.network.benchmark.maybe','application.rsdw.maybe'].includes(name))return BACKGROUND_SERVICE_TIMEOUT_MS;
  if(/(?:backup|restore|update|install|download|sync|refresh|import|export|scan|reconcile|materialize)/.test(name))return LONG_SERVICE_TIMEOUT_MS;
  return DEFAULT_SERVICE_TIMEOUT_MS;
}
function serviceEnvironment() {
  const env = { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', DWSYNC_RESOURCES_DIR: app.isPackaged ? path.join(process.resourcesPath, 'resources') : path.join(projectRoot(), 'resources') };
  if (process.platform !== 'linux') return env;
  env.DRAGONWILDS_SYNC_APPDATA ||= app.getPath('userData');
  if (!env.LOCALAPPDATA) {
    const home = env.HOME || app.getPath('home');
    const appId = String(env.DRAGONWILDS_STEAM_APP_ID || '1374490');
    const roots = [
      path.join(home, '.local', 'share', 'Steam'),
      path.join(home, '.steam', 'steam'),
      path.join(home, '.var', 'app', 'com.valvesoftware.Steam', '.local', 'share', 'Steam'),
    ];
    for (const root of roots) {
      const candidate = path.join(root, 'steamapps', 'compatdata', appId, 'pfx', 'drive_c', 'users', 'steamuser', 'AppData', 'Local');
      if (fs.existsSync(candidate)) { env.LOCALAPPDATA = candidate; break; }
    }
  }
  return env;
}
function startService() {
  if (service && !service.killed) return;
  const cfg = serviceCommand();
  serviceStderrTail = '';
  service = spawn(cfg.command, cfg.args, { cwd: cfg.cwd, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, env: serviceEnvironment() });
  service.stdout.setEncoding('utf8');
  service.stdout.on('data', (chunk) => {
    serviceBuffer += chunk;
    while (serviceBuffer.includes('\n')) {
      const idx = serviceBuffer.indexOf('\n'); const line = serviceBuffer.slice(0, idx).trim(); serviceBuffer = serviceBuffer.slice(idx + 1);
      if (!line) continue;
      try {
        const message = JSON.parse(line); const waiter = pending.get(message.id); if (!waiter) continue;
        pending.delete(message.id); clearPendingTimer(waiter); if (message.ok) waiter.resolve(message.result); else waiter.reject(new Error(message.error || 'Service request failed'));
      } catch (error) { console.error('Invalid service response:', line, error); }
    }
  });
  service.stderr.setEncoding('utf8'); service.stderr.on('data', (chunk) => { serviceStderrTail = (serviceStderrTail + String(chunk)).slice(-1800); console.error('[service]', chunk.trim()); });
  service.stdin.on('error', (error) => console.error('[service stdin]', error.message));
  service.on('exit', (code) => { const detail=serviceStderrTail.trim().split(/\r?\n/).slice(-4).join(' '); rejectAllPending(`Dragonwilds service stopped unexpectedly (exit ${code}).${detail ? ` ${detail}` : ' It will restart automatically on the next action.'}`); service = null; });
  service.on('error', (error) => { rejectAllPending(`Could not start Dragonwilds service: ${error.message}`); service = null; });
}
function serviceInvoke(method, params = {}, options = {}) {
  startService();
  return new Promise((resolve, reject) => {
    if (!service || !service.stdin || service.killed) return reject(new Error('Dragonwilds service is not running.'));
    const id = ++requestCounter;
    const configured=Number(options?.timeoutMs);
    const timeoutMs=Number.isFinite(configured)&&configured>0?Math.max(1000,configured):serviceTimeoutFor(method);
    const timer=setTimeout(()=>{
      if(!pending.delete(id))return;
      reject(new Error(`Dragonwilds service request timed out after ${Math.round(timeoutMs/1000)}s: ${String(method||'unknown')}`));
    },timeoutMs);
    timer.unref?.();
    pending.set(id,{resolve,reject,timer,method:String(method||'')});
    try{service.stdin.write(JSON.stringify({id,method,params})+'\n');}
    catch(error){pending.delete(id);clearTimeout(timer);reject(error);}
  });
}

function iconPath() { return path.join(projectRoot(), 'renderer', 'assets', process.platform === 'win32' ? 'dragonwilds_icon.ico' : 'application-icon.png'); }
function windowOptions(extra = {}) {
  return { backgroundColor: '#0b0e10', icon: iconPath(), show: false, frame: false, autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload-v2.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true, webviewTag: true }, ...extra };
}

const rendererRecovery = new WeakMap();
function restartWithSafeGraphics() {
  if (forceQuit) return;
  const args=process.argv.slice(1).filter((value)=>value!=='--dws-safe-graphics');
  args.push('--dws-safe-graphics');
  app.relaunch({args});
  forceQuit=true;
  // Use the normal quit path so the game, Sync worker, feature workers, and
  // Core service are verified stopped before the safe-graphics process opens.
  app.quit();
}
function attachRendererDurability(win) {
  if (!win || win.isDestroyed() || rendererRecovery.has(win)) return;
  const recovery={events:[],unresponsiveTimer:null,reloading:false};
  rendererRecovery.set(win,recovery);
  const recover=(reason)=>{
    if(win.isDestroyed()||forceQuit||shutdownInProgress||recovery.reloading)return;
    const now=Date.now();
    recovery.events=recovery.events.filter((stamp)=>now-stamp<60000);
    if(recovery.events.length>=2){
      console.error(`[renderer] recovery stopped after repeated failures: ${reason}`);
      dialog.showMessageBox(win,{type:'error',title:'Dragonwilds Sync display recovery',message:'The interface stopped repeatedly.',detail:'Restart with Safe Graphics to disable GPU composition for this session. Your server and Sync worker remain under backend lifecycle authority.',buttons:['Restart with Safe Graphics','Close'],defaultId:0,cancelId:1,noLink:true}).then(({response})=>{if(response===0)restartWithSafeGraphics();}).catch(()=>{});
      return;
    }
    recovery.events.push(now);recovery.reloading=true;
    console.error(`[renderer] reloading shell after ${reason}`);
    setTimeout(()=>{
      if(win.isDestroyed()||forceQuit)return;
      win.webContents.reloadIgnoringCache();
      setTimeout(()=>{recovery.reloading=false},1000);
    },250);
  };
  win.webContents.on('render-process-gone',(_event,details)=>{
    const reason=String(details?.reason||'renderer process exit');
    if(reason!=='clean-exit')recover(reason);
  });
  win.on('unresponsive',()=>{
    clearTimeout(recovery.unresponsiveTimer);
    recovery.unresponsiveTimer=setTimeout(()=>recover('renderer unresponsive'),4000);
  });
  win.on('responsive',()=>{clearTimeout(recovery.unresponsiveTimer);recovery.unresponsiveTimer=null;});
  win.on('closed',()=>clearTimeout(recovery.unresponsiveTimer));
}

function mimeFor(file) {
  const ext = path.extname(file).toLowerCase();
  return ({'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.svg':'image/svg+xml','.ico':'image/x-icon','.woff':'font/woff','.woff2':'font/woff2','.ttf':'font/ttf','.wasm':'application/wasm','.glb':'model/gltf-binary','.gltf':'model/gltf+json','.uemodel':'application/octet-stream'})[ext] || 'application/octet-stream';
}
function stopRsdwToolkitServer() {
  if (rsdwToolkitServer) { try { rsdwToolkitServer.close(); } catch (_) {} }
  rsdwToolkitServer = null; rsdwToolkitBaseUrl = '';
}
function startRsdwToolkitServer(rootDir) {
  const requestedRoot = path.resolve(String(rootDir || ''));
  if (rsdwToolkitServer?.listening && rsdwToolkitBaseUrl && rsdwToolkitRoot === requestedRoot) return Promise.resolve(rsdwToolkitBaseUrl);
  stopRsdwToolkitServer();
  rsdwToolkitRoot = requestedRoot;
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      try {
        const parsed = new URL(req.url || '/', 'http://127.0.0.1');
        let relative = decodeURIComponent(parsed.pathname || '/').replace(/^\/+/, '');
        if (relative === '__health') {
          res.writeHead(200, { 'Content-Type':'application/json; charset=utf-8', 'Cache-Control':'no-store', 'Access-Control-Allow-Origin':'*' });
          return res.end(JSON.stringify({ ok:true, service:'dragonwilds-rsdw-localhost' }));
        }
        if (!relative) relative = 'index.html';
        let servingRoot = rsdwToolkitRoot;
        if (relative.startsWith('__rsdwmodel/vendor/three/')) {
          servingRoot = app.isPackaged
            ? path.resolve(process.resourcesPath, 'rsdw-viewer', 'three')
            : path.resolve(projectRoot(), 'node_modules', 'three');
          relative = relative.slice('__rsdwmodel/vendor/three/'.length);
        } else if (relative.startsWith('__rsdwmodel/')) {
          servingRoot = path.resolve(path.dirname(rsdwToolkitRoot), 'model');
          relative = relative.slice('__rsdwmodel/'.length) || 'Avatar/index.html';
        }
        let target = path.resolve(servingRoot, relative);
        const rootWithSep = servingRoot.endsWith(path.sep) ? servingRoot : servingRoot + path.sep;
        if (target !== servingRoot && !target.startsWith(rootWithSep)) { res.writeHead(403); return res.end('Blocked'); }
        if (fs.existsSync(target) && fs.statSync(target).isDirectory()) target = path.join(target, 'index.html');
        if (!fs.existsSync(target) || !fs.statSync(target).isFile()) { res.writeHead(404); return res.end('Not found'); }
        res.writeHead(200, { 'Content-Type': mimeFor(target), 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*' });
        fs.createReadStream(target).pipe(res);
      } catch (error) { res.writeHead(500); res.end(String(error?.message || error)); }
    });
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      rsdwToolkitServer = server;
      rsdwToolkitBaseUrl = `http://127.0.0.1:${address.port}/`;
      resolve(rsdwToolkitBaseUrl);
    });
  });
}
function detachedIdForWindow(win) {
  for (const [id, entry] of detachedWindows) if (entry.window === win) return id;
  return '';
}
function detachedSnapshot() {
  return [...detachedWindows.entries()].map(([id, entry]) => ({ id, title: entry.title, route: entry.route, hidden: !entry.window || entry.window.isDestroyed() ? true : !entry.window.isVisible() }));
}
function notifyDetachedWindows() {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('dragonwilds:detached-changed', detachedSnapshot());
}
function createDetachedWindow(payload = {}) {
  const route = String(payload.route || 'profile');
  const title = String(payload.title || 'Dragonwilds Sync').slice(0, 120);
  const context = payload.context && typeof payload.context === 'object' ? payload.context : {};
  const id = `dw-${Date.now().toString(36)}-${(++detachedCounter).toString(36)}`;
  const win = new BrowserWindow(windowOptions({ width: Number(payload.width || 1120), height: Number(payload.height || 760), minWidth: 720, minHeight: 520, title, skipTaskbar: true }));
  attachRendererDurability(win);
  const ctx = Buffer.from(JSON.stringify(context), 'utf8').toString('base64url');
  detachedWindows.set(id, { id, window: win, title, route, context });
  win.webContents.on('will-attach-webview', (event, webPreferences, params) => {
    secureAttachedWebview(event, webPreferences, params);
  });
  win.loadFile(path.join(projectRoot(), 'renderer', 'index.html'), { query: { detached: '1', route, windowId: id, ctx } });
  win.once('ready-to-show', () => { win.show(); win.focus(); notifyDetachedWindows(); });
  win.on('show', notifyDetachedWindows); win.on('hide', notifyDetachedWindows);
  win.on('closed', () => { detachedWindows.delete(id); notifyDetachedWindows(); });
  notifyDetachedWindows();
  return { id, title, route };
}

// A minimal, fully isolated browser window for mod-author-declared links
// (IDENTITY.txt Nexus/Steam/website entries, "Show Details" on a mod). It
// gets no preload script and no access to window.dragonwilds -- it is
// arbitrary third-party content, not part of this app's own UI -- and uses
// the OS's native window frame instead of the app's custom titlebar, since
// there is no in-app chrome to draw around someone else's website.
function createExternalBrowserWindow(target, ownerContents = null) {
  const request = target && typeof target === 'object' ? target : { url: target };
  const raw = String(request.url || '').trim();
  let url;
  try { url = new URL(raw); } catch (_) { throw new Error('That link is not a valid web address.'); }
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Only http/https links can be opened in the in-app browser.');
  const win = new BrowserWindow({
    width: 1180, height: 820, minWidth: 480, minHeight: 360,
    title: url.hostname, icon: iconPath(), backgroundColor: '#0b0e10',
    frame: true, autoHideMenuBar: true, show: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, webviewTag: false },
  });
  win.setMenuBarVisibility(false);
  const downloadHandler = (_event, item, sourceContents) => {
    if (sourceContents !== win.webContents || request.purpose !== 'nexus') return;
    const original = String(item.getFilename() || 'nexus-mod.zip');
    const safe = original.replace(/[^A-Za-z0-9._ -]/g, '_');
    const destination = path.join(nexus.stagingDir, `${Date.now()}-${safe}`);
    item.setSavePath(destination);
    item.once('done', (_doneEvent, downloadState) => {
      const receiver = ownerContents && !ownerContents.isDestroyed?.() ? ownerContents : mainWindow?.webContents;
      if (receiver && !receiver.isDestroyed()) receiver.send('dragonwilds:nexus-browser-download', { state: downloadState, path: destination, name: safe });
    });
  };
  win.webContents.session.on('will-download', downloadHandler);
  win.webContents.setWindowOpenHandler(({ url: nextUrl }) => {
    if (request.purpose === 'nexus') {
      try { const next=new URL(nextUrl);if(next.protocol==='https:'){win.loadURL(next.toString());return { action:'deny' };} } catch (_) {}
    }
    shell.openExternal(nextUrl).catch(() => {}); return { action: 'deny' };
  });
  win.loadURL(url.toString());
  win.once('ready-to-show', () => { win.show(); win.focus(); });
  win.once('closed', () => win.webContents.session.removeListener('will-download', downloadHandler));
  return { ok: true };
}


function createManagedDialog(ownerContents, payload = {}) {
  const owner = ownerContents && !ownerContents.isDestroyed?.() ? ownerContents : mainWindow?.webContents;
  if (!owner) throw new Error('Dialog owner is unavailable.');
  const title = String(payload.title || 'Dragonwilds Sync').slice(0, 120);
  const id = `dlg-${Date.now().toString(36)}-${(++detachedCounter).toString(36)}`;
  const width = Math.max(520, Math.min(1500, Number(payload.width || 900)));
  const height = Math.max(360, Math.min(1100, Number(payload.height || 720)));
  const win = new BrowserWindow(windowOptions({ width, height, minWidth: 480, minHeight: 320, title, skipTaskbar: true }));
  const entry = { id, window: win, title, route: 'dialog', context: {}, ownerId: owner.id, html: String(payload.html || ''), theme: String(payload.theme || 'dark') };
  managedDialogs.set(id, entry);
  detachedWindows.set(id, entry);
  win.loadFile(path.join(projectRoot(), 'renderer', 'dialog-host.html'), { query: { dialogId: id } });
  win.once('ready-to-show', () => { win.show(); win.focus(); notifyDetachedWindows(); });
  win.on('show', notifyDetachedWindows); win.on('hide', notifyDetachedWindows);
  win.on('closed', () => {
    managedDialogs.delete(id); detachedWindows.delete(id); notifyDetachedWindows();
    try { if (!owner.isDestroyed()) owner.send('dragonwilds:managed-dialog-closed', { id }); } catch (_) {}
  });
  notifyDetachedWindows();
  return { id, title };
}

function managedDialogOwner(entry) {
  if (!entry) return null;
  try { return webContents.fromId(Number(entry.ownerId || 0)); } catch (_) { return null; }
}

function createWindow({ show = true } = {}) {
  if (mainWindow && !mainWindow.isDestroyed()) { if (show) { mainWindow.show(); mainWindow.focus(); } return mainWindow; }
  mainWindow = new BrowserWindow(windowOptions({ width: 1440, height: 920, minWidth: 1080, minHeight: 700, title: 'Dragonwilds Sync' }));
  attachRendererDurability(mainWindow);
  mainWindow.webContents.on('will-attach-webview', (event, webPreferences, params) => {
    secureAttachedWebview(event, webPreferences, params);
  });
  if (!app.isPackaged) {
    mainWindow.webContents.on('console-message', (event, level, legacyMessage) => {
      const message = (event && typeof event === 'object' && event.message) || legacyMessage || (typeof level === 'string' ? level : '');
      if (message) console.error(`[renderer] ${message}`);
    });
  }
  mainWindow.loadFile(path.join(projectRoot(), 'renderer', 'index.html'));
  if (process.env.DWS_HELP_CAPTURE_DIR && !app.isPackaged) {
    mainWindow.webContents.once('did-finish-load', async () => {
      const output=path.resolve(process.env.DWS_HELP_CAPTURE_DIR);
      const wait=(ms)=>new Promise((resolve)=>setTimeout(resolve,ms));
      const shot=async(name)=>{await wait(900);const image=await mainWindow.webContents.capturePage();fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,name),image.toPNG());};
      const click=async(selector,{optional=false}={})=>{for(let attempt=0;attempt<30;attempt++){const clicked=await mainWindow.webContents.executeJavaScript(`(()=>{const node=document.querySelector(${JSON.stringify(selector)});if(!node)return false;node.click();return true;})()`);if(clicked){await wait(700);const healthy=await mainWindow.webContents.executeJavaScript(`!document.querySelector('.fatal-error')&&!!document.querySelector('.main')`);if(!healthy)throw new Error(`Appy render failed after clicking ${selector}`);return true;}await wait(250);}if(optional)return false;throw new Error(`Help capture control was not found: ${selector}`);};
      const scrollTo=async(selector)=>{for(let attempt=0;attempt<120;attempt++){const found=await mainWindow.webContents.executeJavaScript(`(()=>{const node=document.querySelector(${JSON.stringify(selector)});if(!node)return false;node.scrollIntoView({block:'start'});return true;})()`);if(found){await wait(1400);return true;}await wait(250);}return false;};
      const waitFor=async(selector,attempts=120)=>{for(let attempt=0;attempt<attempts;attempt++){if(await mainWindow.webContents.executeJavaScript(`!!document.querySelector(${JSON.stringify(selector)})`))return true;await wait(250);}return false;};
      const enterWhenReady=async()=>{for(let attempt=0;attempt<160;attempt++){const state=await mainWindow.webContents.executeJavaScript(`(()=>{const nav=document.querySelector('[data-route="world-management"]');if(nav)return 'ready';const enter=document.querySelector('#enter-launcher');if(enter){enter.click();return 'entered';}return 'waiting';})()`);if(state==='ready'){await wait(500);return;}await wait(state==='entered'?900:250);}throw new Error('Launcher did not reach its Appy navigation within 40 seconds.');};
      try {
        await wait(2200); await shot('01-getting-started.png');
        await enterWhenReady(); await shot('02-worlds.png');
        await click('[data-route="characters-app"]'); await shot('40-character-creator-top.png'); await scrollTo('.native-avatar-section'); await waitFor('.native-avatar-section .avatar-ready'); await shot('03-characters.png');
        await click('[data-route="mods-app"]'); await wait(1200); await shot('07-mods.png');
        if(await click('[data-release-open-mods]',{optional:true})){
          if(!await waitFor('[data-private-tab="mods"].active,[data-server-tab="mods"].active',40))throw new Error('Manage Mods did not open the selected profile Mods tab.');
          await shot('41-profile-mod-editor.png');
        }
        await click('[data-route="rsdw-launcher"]'); await shot('38-rsdwl.png');
        await click('[data-route="rsdragonwilds-app"]'); await shot('05-server-setup.png');
        await click('[data-route="webhost"]'); await click('[data-webhost-tab="settings"]'); await shot('09-networking.png');
        await click('[data-webhost-tab="manifest"]'); await shot('29-manifest-hosts.png');
        await click('[data-route="settings"]'); await shot('13-settings.png');
        await click('[data-settings-tab="integrations"]'); await shot('39-integrations.png');
        await click('[data-settings-tab="mods"]'); await wait(1200); await shot('37-mod-management.png');
        await click('[data-route="help"]'); await shot('27-help-flow.png');
        console.log(`[OK] Current Help screenshots captured: ${output}`);
      } catch (error) { console.error(`[help-capture] ${error?.stack||error}`); process.exitCode=1; }
      finally { forceQuit=true; app.quit(); }
    });
  }
  mainWindow.once('ready-to-show', () => { if (show && !backgroundSettings.start_minimized) mainWindow.show(); });
  mainWindow.on('close', (event) => {
    if (!forceQuit && backgroundSettings.close_to_tray) { event.preventDefault(); mainWindow.hide(); }
  });
  mainWindow.on('closed', () => { mainWindow = null; });
  return mainWindow;
}
function createQuickWindow(worldId, worldKind = 'world', autoStart = false) {
  const id = String(worldId || '').trim(); if (!id) return createWindow({ show: true });
  const kind = ['world', 'private', 'server'].includes(String(worldKind || '').toLowerCase()) ? String(worldKind).toLowerCase() : 'world';
  if (quickWindow && !quickWindow.isDestroyed()) { quickWindow.close(); quickWindow = null; }
  quickWindow = new BrowserWindow(windowOptions({ width: 520, height: 300, minWidth: 440, minHeight: 250, resizable: false, title: 'Dragonwilds Sync Quick Launch' }));
  attachRendererDurability(quickWindow);
  quickWindow.loadFile(path.join(projectRoot(), 'renderer', 'quick.html'), { query: { quick: '1', worldId: id, worldKind: kind, autoStart: autoStart ? '1' : '0' } });
  quickWindow.once('ready-to-show', () => { quickWindow.show(); quickWindow.focus(); });
  quickWindow.on('closed', () => { quickWindow = null; });
  return quickWindow;
}
function createMinimalWindow(worldId, autoStart = false) {
  const id=String(worldId||'').trim();if(!id)return createWindow({show:true});
  if(minimalWindow&&!minimalWindow.isDestroyed()){
    minimalWindow.loadFile(path.join(projectRoot(),'renderer','quick.html'),{query:{minimal:'1',worldId:id,worldKind:'server',autoStart:autoStart?'1':'0'}});
    minimalWindow.show();minimalWindow.focus();return minimalWindow;
  }
  minimalWindow=new BrowserWindow(windowOptions({width:1050,height:760,minWidth:720,minHeight:520,resizable:true,title:'Dragonwilds Sync · Minimal Mode'}));
  attachRendererDurability(minimalWindow);
  minimalWindow.loadFile(path.join(projectRoot(),'renderer','quick.html'),{query:{minimal:'1',worldId:id,worldKind:'server',autoStart:autoStart?'1':'0'}});
  minimalWindow.once('ready-to-show',()=>{minimalWindow.show();minimalWindow.focus();});
  minimalWindow.on('closed',()=>{minimalWindow=null;});
  return minimalWindow;
}
function parseQuickArgs(argv) {
  const quick = argv.includes('--quick-launch');
  const minimal = argv.includes('--minimal-mode');
  let worldId = '';
  let worldKind = 'world';
  for (let i = 0; i < argv.length; i++) {
    const arg = String(argv[i] || '');
    if (arg.startsWith('--world-id=')) worldId = arg.slice('--world-id='.length);
    else if (arg === '--world-id' && argv[i + 1]) worldId = String(argv[i + 1]);
    else if (arg.startsWith('--world-kind=')) worldKind = arg.slice('--world-kind='.length).toLowerCase();
    else if (arg === '--world-kind' && argv[i + 1]) worldKind = String(argv[i + 1]).toLowerCase();
  }
  if (!['world', 'private', 'server'].includes(worldKind)) worldKind = 'world';
  return { quick, minimal, worldId, worldKind, autoStart: argv.includes('--auto-start') };
}

function parseJoinArgs(argv = []) {
  const raw = (argv || []).map(String).find((value) => value.toLowerCase().startsWith('dragonwilds-sync://'));
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== 'dragonwilds-sync:' || url.hostname.toLowerCase() !== 'join') return null;
    const directoryUrl = new URL(url.searchParams.get('directory') || '');
    if (!['http:', 'https:'].includes(directoryUrl.protocol) || directoryUrl.username || directoryUrl.password) return null;
    const worldId = String(url.searchParams.get('world_id') || '').trim().slice(0, 240);
    if (!worldId) return null;
    return { directoryUrl: directoryUrl.toString().replace(/\/$/, ''), worldId };
  } catch (_) { return null; }
}

function deliverJoinRequest(request) {
  if (!request) return;
  pendingJoinRequest = request;
  if (!app.isReady()) return;
  const win = createWindow({ show: true });
  const send = () => {
    if (!mainWindow || mainWindow.isDestroyed() || mainWindow.webContents.isLoading()) return false;
    mainWindow.webContents.send('dragonwilds:join-request', pendingJoinRequest);
    pendingJoinRequest = null;
    win.show(); win.focus();
    return true;
  };
  if (!send()) win.webContents.once('did-finish-load', send);
}

function refreshBackgroundSettings() {
  return serviceInvoke('state.get', {}).then((data) => {
    backgroundSettings = { ...backgroundSettings, ...((data.application || {}).background_mode || {}) };
    return backgroundSettings;
  }).catch(() => backgroundSettings);
}
function showPassiveNotification(event) {
  if (!backgroundSettings.notifications_enabled) return;
  const key = String(event.key || `${event.title}:${event.body}`); const now = Date.now();
  const last = notificationSeen.get(key) || 0; if (now - last < 5 * 60 * 1000) return;
  notificationSeen.set(key, now);
  if (event.overlay && backgroundSettings.announcement_overlay_enabled !== false) showAnnouncementOverlay(event);
  if (!Notification.isSupported()) return;
  const n = new Notification({ title: String(event.title || 'Dragonwilds Sync'), body: String(event.body || ''), silent: true, icon: iconPath() });
  n.on('click', () => { const w = createWindow({ show: true }); w.show(); w.focus(); }); n.show();
  if (notificationSeen.size > 200) for (const [k, t] of notificationSeen) if (now - t > 24 * 3600 * 1000) notificationSeen.delete(k);
}
function showAnnouncementOverlay(event) {
  const palette={info:'#d5a54a',success:'#70d39b',warning:'#e5ad48',critical:'#e07878',restart:'#e5ad48',update:'#79aee8',latency:'#e5ad48'};
  const kind=String(event.kind||'info').toLowerCase(),accent=palette[kind]||palette.info;
  const escapeHtml=value=>String(value||'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  if (announcementTimer) { clearTimeout(announcementTimer); announcementTimer=null; }
  if (announcementWindow && !announcementWindow.isDestroyed()) announcementWindow.destroy();
  const area=screen.getPrimaryDisplay().workArea, width=Math.min(760,Math.max(420,area.width-40));
  announcementWindow=new BrowserWindow({width,height:108,x:Math.round(area.x+(area.width-width)/2),y:area.y+18,frame:false,transparent:true,backgroundColor:'#00000000',alwaysOnTop:true,focusable:false,skipTaskbar:true,resizable:false,movable:false,show:false,hasShadow:false,webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,devTools:false}});
  announcementWindow.setIgnoreMouseEvents(true,{forward:false}); announcementWindow.setAlwaysOnTop(true,'screen-saver');
  const html=`<!doctype html><html><head><meta charset="utf-8"><style>*{box-sizing:border-box}html,body{margin:0;background:transparent;overflow:hidden}body{padding:5px;font:14px/1.35 Segoe UI,system-ui;color:#f7f3e9}.card{height:96px;display:grid;grid-template-columns:6px 1fr;overflow:hidden;border:1px solid ${accent};border-radius:14px;background:rgba(10,14,15,.94);box-shadow:0 16px 44px rgba(0,0,0,.48)}.accent{background:${accent}}.copy{padding:15px 18px}.title{color:${accent};font-weight:800;letter-spacing:.04em;margin-bottom:5px}.body{font-size:15px}.hint{margin-top:5px;color:#9ca5a2;font-size:10px;text-transform:uppercase;letter-spacing:.12em}</style></head><body><div class="card"><div class="accent"></div><div class="copy"><div class="title">${escapeHtml(event.title||'Dragonwilds Sync')}</div><div class="body">${escapeHtml(event.body||'')}</div><div class="hint">Passive World announcement · no focus or input captured</div></div></div></body></html>`;
  announcementWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`); announcementWindow.once('ready-to-show',()=>announcementWindow?.showInactive());
  announcementWindow.on('closed',()=>{announcementWindow=null}); announcementTimer=setTimeout(()=>{if(announcementWindow&&!announcementWindow.isDestroyed())announcementWindow.destroy();announcementTimer=null},9000);
}
function createTray() {
  if (tray || process.platform === 'linux' && !fs.existsSync(iconPath())) return;
  tray = new Tray(iconPath()); tray.setToolTip('Dragonwilds Sync');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open Dragonwilds Sync', click: () => { const w = createWindow({ show: true }); w.show(); w.focus(); } },
    { type: 'separator' },
    { label: 'Quit', click: () => { forceQuit = true; app.quit(); } },
  ]));
  tray.on('double-click', () => { const w = createWindow({ show: true }); w.show(); w.focus(); });
}

function writeWorldIcon(worldId, iconData, iconAsset = '') {
  const fallback = iconPath(); if (!iconData) return fallback;
  try {
    const image = nativeImage.createFromDataURL(String(iconData).startsWith('data:') ? String(iconData) : `data:image/png;base64,${iconData}`);
    if (image.isEmpty()) return fallback;
    const png = image.resize({ width: 256, height: 256 }).toPNG();
    const dir = path.join(app.getPath('userData'), 'QuickLaunchIcons'); fs.mkdirSync(dir, { recursive: true });
    const target = path.join(dir, `${String(worldId).replace(/[^A-Za-z0-9_-]/g, '_')}.ico`);
    // ICO can embed a PNG payload directly. ICONDIR + one ICONDIRENTRY + PNG bytes.
    const header = Buffer.alloc(22); header.writeUInt16LE(0,0); header.writeUInt16LE(1,2); header.writeUInt16LE(1,4);
    header[6]=0; header[7]=0; header[8]=0; header[9]=0; header.writeUInt16LE(1,10); header.writeUInt16LE(32,12);
    header.writeUInt32LE(png.length,14); header.writeUInt32LE(22,18); fs.writeFileSync(target, Buffer.concat([header,png])); return target;
  } catch (_) { return fallback; }
}
function createWorldShortcut({ worldId, name, iconData, iconAsset, worldKind }) {
  if (process.platform !== 'win32') throw new Error('Send to Desktop is currently a Windows feature.');
  const id = String(worldId || '').trim(); if (!id) throw new Error('World ID is required.');
  const kind = ['world', 'private', 'server'].includes(String(worldKind || '').toLowerCase()) ? String(worldKind).toLowerCase() : 'world';
  const safeName = String(name || 'Dragonwilds World').replace(/[<>:"/\\|?*]/g, '').trim() || 'Dragonwilds World';
  let resolvedIconData = String(iconData || '');
  if (!resolvedIconData && iconAsset) {
    const safeAsset = path.basename(String(iconAsset));
    const assetPath = path.join(projectRoot(), 'renderer', 'assets', safeAsset);
    if (fs.existsSync(assetPath) && fs.statSync(assetPath).isFile()) resolvedIconData = `data:image/png;base64,${fs.readFileSync(assetPath).toString('base64')}`;
  }
  const shortcutPath = path.join(app.getPath('desktop'), `${safeName}.lnk`); const icon = writeWorldIcon(id, resolvedIconData);
  const quickArgs = `--quick-launch --world-id=${id} --world-kind=${kind}`;
  const target = process.execPath; const args = app.isPackaged ? quickArgs : `"${projectRoot()}" ${quickArgs}`;
  const ok = shell.writeShortcutLink(shortcutPath, 'create', { target, args, description: `Quick launch ${safeName} with Dragonwilds Sync`, cwd: app.isPackaged ? path.dirname(process.execPath) : projectRoot(), icon, iconIndex: 0 });
  if (!ok) throw new Error('Windows did not create the desktop shortcut.');
  return { ok: true, path: shortcutPath, icon };
}

ipcMain.handle('dragonwilds:invoke', (_event, method, params, meta) => {
  const policyTimeout=serviceTimeoutFor(method);
  const requested=Number(meta?.timeoutMs);
  const timeoutMs=Number.isFinite(requested)&&requested>0?Math.min(policyTimeout,Math.max(1000,requested)):policyTimeout;
  return serviceInvoke(method,params||{}, {timeoutMs});
});
ipcMain.handle('dragonwilds:admin-status', () => runtimePlatformStatus());
ipcMain.handle('dragonwilds:restart-admin', () => restartElevated());
ipcMain.handle('dragonwilds:pick-image', async () => {
  const r=await dialog.showOpenDialog(mainWindow,{title:'Choose image',properties:['openFile'],filters:[{name:'Images',extensions:['png','jpg','jpeg','webp','ico']}]});
  if(r.canceled||!r.filePaths[0])return null;
  const file=r.filePaths[0];let image=nativeImage.createFromPath(file);
  if(image.isEmpty())throw new Error('The selected image could not be decoded.');
  const size=image.getSize(),scale=Math.min(1,1600/Math.max(1,size.width),1000/Math.max(1,size.height));
  if(scale<1)image=image.resize({width:Math.max(1,Math.round(size.width*scale)),height:Math.max(1,Math.round(size.height*scale)),quality:'best'});
  let bytes=image.toPNG(),mime='image/png';
  if(bytes.length>4*1024*1024){bytes=image.toJPEG(88);mime='image/jpeg';}
  const finalSize=image.getSize();
  return {file,dataUrl:`data:${mime};base64,${bytes.toString('base64')}`,width:finalSize.width,height:finalSize.height};
});
ipcMain.handle('dragonwilds:pick-loading-art', async () => {
  const result=await dialog.showOpenDialog(mainWindow,{title:'Choose loading artwork',properties:['openFile'],filters:[{name:'Animated or static artwork',extensions:['gif','png','jpg','jpeg','webp']} ]});
  if(result.canceled||!result.filePaths[0])return null;
  const source=result.filePaths[0],extension=path.extname(source).toLowerCase();
  const stat=fs.statSync(source);if(!stat.isFile())throw new Error('The selected loading artwork is not a file.');
  if(stat.size>175*1024*1024)throw new Error('Loading artwork is limited to 175 MB. Use the optimized GIF or a static image.');
  const targetDir=path.join(app.getPath('userData'),'Appearance');fs.mkdirSync(targetDir,{recursive:true});
  const target=path.join(targetDir,`custom-loading-art${extension}`);fs.copyFileSync(source,target);
  return {file:target,url:pathToFileURL(target).href,size:stat.size};
});
ipcMain.handle('dragonwilds:pick-directory', async () => { const r=await dialog.showOpenDialog(mainWindow,{properties:['openDirectory','createDirectory']}); return r.canceled?null:r.filePaths[0]||null; });
ipcMain.handle('dragonwilds:pick-executable', async () => { const r=await dialog.showOpenDialog(mainWindow,{properties:['openFile'],filters:[{name:'Executable',extensions:['exe']},{name:'All files',extensions:['*']}]}); return r.canceled?null:r.filePaths[0]||null; });
ipcMain.handle('dragonwilds:pick-file', async (_event, kind) => { const filters=(kind==='zip'||kind==='archive')?[{name:'Mod archives',extensions:['zip','7z']}]:kind==='rsdwl'?[{name:'Dragonwilds Launcher Package',extensions:['rsdwl']}]:kind==='dwsworld'?[{name:'Dragonwilds World Identity Card',extensions:['dwsworld']}]:[{name:'All files',extensions:['*']}]; const r=await dialog.showOpenDialog(mainWindow,{properties:['openFile'],filters}); return r.canceled?null:r.filePaths[0]||null; });
ipcMain.handle('dragonwilds:save-file', async (_event, opts={}) => { const r=await dialog.showSaveDialog(mainWindow,{ title: opts.title || 'Save file', defaultPath: opts.defaultPath || undefined, filters: opts.filters || [{name:'ZIP',extensions:['zip']}] }); return r.canceled?null:r.filePath||null; });
ipcMain.handle('dragonwilds:copy-text', (_event,text) => { clipboard.writeText(String(text||'')); return true; });
ipcMain.handle('dragonwilds:file-sha256', (_event,target) => { const file=path.resolve(String(target||'')); if(!fs.existsSync(file)||!fs.statSync(file).isFile()) throw new Error('File not found.'); return cryptoHashFile(file); });
ipcMain.handle('dragonwilds:create-world-shortcut', (_event, data) => createWorldShortcut(data || {}));
ipcMain.handle('dragonwilds:remove-world-shortcut', (_event, name) => { if (process.platform!=='win32') return false; const safe=String(name||'Dragonwilds World').replace(/[<>:"/\\|?*]/g,'').trim()||'Dragonwilds World'; const target=path.join(app.getPath('desktop'),`${safe}.lnk`); try { fs.unlinkSync(target); return true; } catch (_) { return false; } });
ipcMain.handle('dragonwilds:background-settings', async (_event, incoming) => { backgroundSettings={...backgroundSettings,...(incoming||{})}; return backgroundSettings; });
ipcMain.handle('dragonwilds:notify', (_event, evt) => { showPassiveNotification(evt||{}); return true; });
ipcMain.handle('dragonwilds:open-main-window', () => { const w=createWindow({show:true}); w.show(); w.focus(); return true; });
ipcMain.handle('dragonwilds:open-minimal-mode', (_event, worldId) => { createMinimalWindow(worldId); return true; });
ipcMain.handle('dragonwilds:discord-activity', async (_event,activity) => discordPresence.setActivity(activity||null));
ipcMain.handle('dragonwilds:discord-clear', async () => discordPresence.clear());
ipcMain.handle('dragonwilds:discord-status', () => discordPresence.status());
ipcMain.handle('dragonwilds:window-minimize', (event) => { const w=BrowserWindow.fromWebContents(event.sender); if(!w)return false; const id=detachedIdForWindow(w); if(id){w.hide(); if(mainWindow&&!mainWindow.isDestroyed()){mainWindow.show();mainWindow.focus();} notifyDetachedWindows(); return true;} w.minimize(); return true; });
ipcMain.handle('dragonwilds:window-toggle-maximize', (event) => { const w=BrowserWindow.fromWebContents(event.sender); if(!w)return false; if(w.isMaximized())w.unmaximize();else w.maximize(); return w.isMaximized(); });
ipcMain.handle('dragonwilds:window-close', (event) => { BrowserWindow.fromWebContents(event.sender)?.close(); return true; });
ipcMain.handle('dragonwilds:window-state', (event) => ({ maximized:!!BrowserWindow.fromWebContents(event.sender)?.isMaximized() }));
ipcMain.handle('dragonwilds:detached-open', (_event, payload={}) => createDetachedWindow(payload));
ipcMain.handle('dragonwilds:detached-list', () => detachedSnapshot());
ipcMain.handle('dragonwilds:detached-restore', (_event, id) => { const entry=detachedWindows.get(String(id||'')); if(!entry||entry.window.isDestroyed())return false; entry.window.show(); entry.window.focus(); notifyDetachedWindows(); return true; });
ipcMain.handle('dragonwilds:detached-close', (_event, id) => { const entry=detachedWindows.get(String(id||'')); if(!entry||entry.window.isDestroyed())return false; entry.window.close(); return true; });


ipcMain.handle('dragonwilds:capture-webview', async (_event, payload={}) => {
  const id = Number(payload.webContentsId || 0);
  const wc = webContents.fromId(id);
  if (!wc || wc.isDestroyed()) throw new Error('The 3D Avatar surface is not available.');
  let rect = null;
  try {
    rect = await wc.executeJavaScript(`(() => { const c=document.querySelector('canvas'); if(!c)return null; const r=c.getBoundingClientRect(); return {x:Math.max(0,Math.floor(r.x)),y:Math.max(0,Math.floor(r.y)),width:Math.max(1,Math.floor(r.width)),height:Math.max(1,Math.floor(r.height))}; })()`, true);
  } catch (_) {}
  let image = await wc.capturePage(rect && rect.width > 10 && rect.height > 10 ? rect : undefined);
  if (String(payload.mode || '') === 'portrait') {
    const size=image.getSize();
    const side=Math.max(1,Math.min(size.width,size.height));
    const x=Math.max(0,Math.floor((size.width-side)/2));
    // Bias slightly upward for a face-card while retaining upper torso/armour.
    const y=Math.max(0,Math.min(size.height-side,Math.floor((size.height-side)*0.18)));
    image=image.crop({x,y,width:side,height:side}).resize({width:768,height:768,quality:'best'});
  }
  const size=image.getSize();
  return { dataUrl:image.toDataURL(), width:size.width, height:size.height };
});
ipcMain.handle('dragonwilds:managed-dialog-open', (event, payload={}) => createManagedDialog(event.sender, payload));
ipcMain.handle('dragonwilds:managed-dialog-content', (event, id) => {
  const entry=managedDialogs.get(String(id||''));
  if(!entry || entry.window.isDestroyed() || entry.window.webContents.id!==event.sender.id) throw new Error('Managed dialog was not found.');
  return { id:entry.id, title:entry.title, html:entry.html, theme:entry.theme };
});
ipcMain.handle('dragonwilds:managed-dialog-event', (event, payload={}) => {
  const entry=managedDialogs.get(String(payload.id||''));
  if(!entry || entry.window.isDestroyed() || entry.window.webContents.id!==event.sender.id) return false;
  const owner=managedDialogOwner(entry); if(!owner || owner.isDestroyed()) return false;
  owner.send('dragonwilds:managed-dialog-event', payload); return true;
});
ipcMain.handle('dragonwilds:managed-dialog-update', (event, payload={}) => {
  const entry=managedDialogs.get(String(payload.id||'')); if(!entry) return false;
  if(Number(entry.ownerId)!==event.sender.id) return false;
  if(payload.html!=null) entry.html=String(payload.html);
  if(payload.theme!=null) entry.theme=String(payload.theme);
  if(!entry.window.isDestroyed()) entry.window.webContents.send('dragonwilds:managed-dialog-update',{id:entry.id,html:entry.html,theme:entry.theme,fields:payload.fields||{}});
  return true;
});
ipcMain.handle('dragonwilds:managed-dialog-close', (event, id) => {
  const entry=managedDialogs.get(String(id||'')); if(!entry) return false;
  if(Number(entry.ownerId)!==event.sender.id && entry.window.webContents.id!==event.sender.id) return false;
  if(!entry.window.isDestroyed()) entry.window.close(); return true;
});

ipcMain.handle('dragonwilds:nexus-status', () => nexus.status());
ipcMain.handle('dragonwilds:nexus-connect-sso', () => nexus.connectSSO());
ipcMain.handle('dragonwilds:nexus-connect-dev-key', (_event, key) => nexus.connectDevelopmentKey(key));
ipcMain.handle('dragonwilds:nexus-disconnect', () => nexus.disconnect());
ipcMain.handle('dragonwilds:nexus-search', (_event, query) => nexus.search(query));
ipcMain.handle('dragonwilds:nexus-mod', (_event, modId) => nexus.getMod(modId));
ipcMain.handle('dragonwilds:nexus-files', (_event, modId) => nexus.getFiles(modId));
ipcMain.handle('dragonwilds:nexus-download-descriptor', (_event, data={}) => nexus.downloadDescriptor(data.modId, data.fileId));
ipcMain.handle('dragonwilds:nexus-download-stage', (_event, data={}) => nexus.downloadToStaging(data.url, data.name));
ipcMain.handle('dragonwilds:nexus-prepare-archive', (_event, target) => nexus.prepareArchive(target));
ipcMain.handle('dragonwilds:app-update-mode', () => ({ mode: detectMode(app), version: app.getVersion(), packaged: app.isPackaged }));
ipcMain.handle('dragonwilds:app-update-check', async (_event, opts={}) => checkForUpdates({ repositoryUrl: opts.repositoryUrl || '', currentVersion: app.getVersion(), mode: detectMode(app), etag: opts.etag || '' }));
ipcMain.handle('dragonwilds:app-update-apply', async (_event, opts={}) => stageAndApply({ app, release: opts.release || {}, repositoryUrl: opts.repositoryUrl || '' }));
ipcMain.handle('dragonwilds:app-update-result', () => readAppliedUpdate(app));
ipcMain.handle('dragonwilds:app-update-dismiss-result', () => dismissAppliedUpdate(app));

ipcMain.handle('dragonwilds:rsdw-webview-preload', () => pathToFileURL(rsdwGuestPreload).toString());
ipcMain.handle('dragonwilds:legal-text', () => { try { return fs.readFileSync(path.join(projectRoot(), 'LICENSE.txt'), 'utf8'); } catch (_) { return ''; } });
ipcMain.handle('dragonwilds:rsdw-toolkit-root', async (_event, incoming) => {
  const candidate = path.resolve(String(incoming || ''));
  const required = path.join(candidate, 'tools', 'character-editor', 'index.html');
  if (!candidate || !fs.existsSync(required)) { rsdwToolkitRoot = ''; stopRsdwToolkitServer(); return { ok:false, mode:'remote', baseUrl:'https://rsdwtools.com/' }; }
  try { const baseUrl = await startRsdwToolkitServer(candidate); return { ok:true, mode:'local', baseUrl }; }
  catch (_) { rsdwToolkitRoot=''; stopRsdwToolkitServer(); return { ok:false, mode:'remote', baseUrl:'https://rsdwtools.com/' }; }
});

ipcMain.handle('dragonwilds:open-external', async (_event,target) => { try { const raw=String(target||'').trim(); const url=new URL(raw); const safeWeb=['http:','https:'].includes(url.protocol); const safeSteam=/^steam:\/\/(?:run|rungameid|validate|install)\/(?:1374490|4019830)$/i.test(raw); if(!safeWeb&&!safeSteam)return false; await shell.openExternal(url.toString()); return true; } catch(_){return false;} });
ipcMain.handle('dragonwilds:open-in-app-browser', (event,target) => createExternalBrowserWindow(target, event.sender));
ipcMain.handle('dragonwilds:open-path', async (_event,target) => { if(!target)return false; return !(await shell.openPath(target)); });

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) app.quit();
else app.on('second-instance', (_event, argv) => { const join=parseJoinArgs(argv); if(join)deliverJoinRequest(join); else { const q=parseQuickArgs(argv); if(q.minimal&&q.worldId)createMinimalWindow(q.worldId,q.autoStart);else if(q.quick&&q.worldId)createQuickWindow(q.worldId,q.worldKind,q.autoStart); else { const w=createWindow({show:true}); w.show(); w.focus(); } } });

app.on('open-url', (event, url) => { event.preventDefault(); const request=parseJoinArgs([url]); if(request)deliverJoinRequest(request); });

app.whenReady().then(async () => {
  if (process.defaultApp && process.argv[1]) app.setAsDefaultProtocolClient('dragonwilds-sync', process.execPath, [path.resolve(process.argv[1])]);
  else app.setAsDefaultProtocolClient('dragonwilds-sync');
  app.on('web-contents-created', (_event, contents) => {
    if (contents.getType() !== 'webview') return;
    const preview = contents.session === session.fromPartition('persist:webhost-preview');
    contents.on('before-input-event', (event, input) => {
      if (!preview) return;
      const key=String(input.key||'').toLowerCase();
      if (key==='f12' || (input.control && input.shift && ['i','j','c'].includes(key)) || (input.control && ['u','s','p'].includes(key))) event.preventDefault();
    });
    if (preview) contents.on('context-menu', (event)=>event.preventDefault());
    contents.setWindowOpenHandler(({ url }) => {
      if (preview) return { action:'deny' };
      // Keep locally served RSDWTools navigation inside the embedded guest. Opening
      // loopback URLs in the OS is both surprising and was the source of the old
      // rsdw-local:// Windows protocol popup. Remote links still open normally.
      if (allowedToolkitNavigation(url) && /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\//i.test(url)) {
        contents.loadURL(url).catch(()=>{});
        return { action:'deny' };
      }
      if (/^https?:/i.test(url)) shell.openExternal(url).catch(()=>{});
      return { action:'deny' };
    });
    contents.on('will-navigate', (event, url) => {
      if (preview) { if (!allowedWebhostPreviewNavigation(url)) event.preventDefault(); return; }
      if (allowedToolkitNavigation(url)) return;
      event.preventDefault();
      if (/^https?:/i.test(url)) shell.openExternal(url).catch(()=>{});
    });
  });
  startService(); await refreshBackgroundSettings(); createTray();
  const q=parseQuickArgs(process.argv);
  const startupJoin=pendingJoinRequest||parseJoinArgs(process.argv);
  if(startupJoin) deliverJoinRequest(startupJoin); else if(q.minimal&&q.worldId)createMinimalWindow(q.worldId,q.autoStart);else if(q.quick&&q.worldId) createQuickWindow(q.worldId,q.worldKind,q.autoStart); else createWindow({show:!backgroundSettings.start_minimized});
  const maybeBenchmark=()=>serviceInvoke('server.network.benchmark.maybe',{}).catch(()=>{}); setTimeout(maybeBenchmark,20000); benchmarkTimer=setInterval(maybeBenchmark,60*60*1000);
  const backgroundTick=()=>{serviceInvoke('world.discovery.heartbeat',{}).catch(()=>{});return serviceInvoke('client.background.tick',{}).then((r)=>{ for(const evt of r.events||[])showPassiveNotification(evt); }).catch(()=>{});}; setTimeout(backgroundTick,8000); backgroundTimer=setInterval(backgroundTick,30*1000);
  const schedulerTick=()=>serviceInvoke('server.scheduler.tick',{}).then((r)=>{ for(const evt of r.events||[]) if(evt.type==='warning') showPassiveNotification({key:`scheduler:${evt.minutes}:${evt.action}`,title:'Dragonwilds Server',body:evt.message,kind:evt.action==='backup'?'info':'restart'}); }).catch(()=>{}); setTimeout(schedulerTick,15000); schedulerTimer=setInterval(schedulerTick,15*1000);
  const rsdwModuleTick=()=>serviceInvoke('application.rsdw.maybe',{}).catch(()=>{}); setTimeout(rsdwModuleTick,30000); rsdwModuleTimer=setInterval(rsdwModuleTick,60*60*1000);
  app.on('activate',()=>{ if(BrowserWindow.getAllWindows().length===0)createWindow({show:true}); else if(mainWindow){mainWindow.show();mainWindow.focus();} });
});
app.on('window-all-closed',()=>{ if(process.platform==='darwin')return; if(!backgroundSettings.close_to_tray){forceQuit=true;app.quit();} });

function stopLauncherOwnedShellServices(){
  stopRsdwToolkitServer();
  for(const entry of detachedWindows.values()){try{entry.window.destroy();}catch(_){}}
  detachedWindows.clear();
  if(benchmarkTimer)clearInterval(benchmarkTimer);
  if(backgroundTimer)clearInterval(backgroundTimer);
  if(schedulerTimer)clearInterval(schedulerTimer);
  if(rsdwModuleTimer)clearInterval(rsdwModuleTimer);
  benchmarkTimer=backgroundTimer=schedulerTimer=rsdwModuleTimer=null;
  discordPresence.destroy();
}

function terminateBackendProcessTree(){
  const owned=service;
  if(!owned||owned.killed||owned.exitCode!==null)return;
  const pid=Number(owned.pid||0);
  if(pid<=0)return;
  try{
    if(process.platform==='win32')execFileSync('taskkill.exe',['/PID',String(pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
    else{
      try{execFileSync('pkill',['-TERM','-P',String(pid)],{stdio:'ignore'});}catch(_){}
      owned.kill('SIGTERM');
    }
  }catch(_){try{owned.kill('SIGKILL');}catch(__){}}
}

function beginVisualApplicationExit(){
  if(visualShutdownStarted)return;
  visualShutdownStarted=true;forceQuit=true;
  // A verified backend shutdown can take several seconds when a dedicated
  // server is stopping. Remove the launcher UI immediately while that bounded
  // authority-preserving cleanup continues in the background.
  for(const win of BrowserWindow.getAllWindows()){try{win.hide();}catch(_){}}
  if(tray){try{tray.destroy();}catch(_){}tray=null;}
}

async function performFullApplicationExit(){
  if(shutdownInProgress||shutdownComplete)return;
  shutdownInProgress=true;beginVisualApplicationExit();
  try{
    if(service&&!service.killed){
      let timeoutId;
      const timeout=new Promise((_,reject)=>{timeoutId=setTimeout(()=>reject(new Error('Backend shutdown verification timed out.')),30000);});
      try{await Promise.race([serviceInvoke('application.shutdown',{}, {timeoutMs:30000}),timeout]);}
      finally{if(timeoutId)clearTimeout(timeoutId);}
    }
  }catch(error){console.error(`[shutdown] ${error?.stack||error}`);}
  finally{
    stopLauncherOwnedShellServices();
    // The graceful RPC is authoritative. This final bounded tree termination
    // is the containment fallback for a wedged Core/worker IPC path; unlike a
    // plain child.kill(), it cannot leave launcher-owned grandchildren alive.
    terminateBackendProcessTree();
    shutdownComplete=true;shutdownInProgress=false;
    app.quit();
  }
}

app.on('before-quit',(event)=>{
  forceQuit=true;
  if(shutdownComplete){stopLauncherOwnedShellServices();return;}
  event.preventDefault();
  beginVisualApplicationExit();
  void performFullApplicationExit();
});
