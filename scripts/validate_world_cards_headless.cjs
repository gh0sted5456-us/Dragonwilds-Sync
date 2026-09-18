'use strict';

const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '..');
const outputDir = path.join(root, 'Codex Outputs', 'GUI Validation');
const candidates = process.platform === 'win32'
  ? [process.env['ProgramFiles(x86)'] && path.join(process.env['ProgramFiles(x86)'], 'Microsoft/Edge/Application/msedge.exe'),
     process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Microsoft/Edge/Application/msedge.exe')]
  : ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
const browser = candidates.filter(Boolean).find(candidate => fs.existsSync(candidate));
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const types = {'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.svg':'image/svg+xml'};
const server = http.createServer((request, response) => {
  try {
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname === '/__validation') { response.writeHead(204); response.end(); return; }
    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '');
    const target = path.resolve(root, relative || 'scripts/fixtures/world_cards.html');
    if (target !== root && !target.startsWith(root + path.sep)) { response.writeHead(403); response.end(); return; }
    const data = fs.readFileSync(target);
    response.writeHead(200, {'Content-Type': types[path.extname(target).toLowerCase()] || 'application/octet-stream'});
    response.end(data);
  } catch (_) { response.writeHead(404); response.end(); }
});

// The DevTools pipe is local to this child: no debugging port or remote listener.
// Capture explicitly AFTER validation instead of killing Chromium on a page
// callback before --screenshot has actually written its output.
function connect(child) {
  let nextId = 0, buffer = '', stopped = false;
  const pending = new Map();
  function close(error = new Error('Browser closed')) {
    stopped = true;
    for (const request of pending.values()) { clearTimeout(request.timer); request.reject(error); }
    pending.clear();
  }
  child.once('error', close);
  child.once('exit', () => close());
  child.stdio[3].on('error', close);
  child.stdio[4].on('error', close);
  child.stdio[4].setEncoding('utf8');
  child.stdio[4].on('data', chunk => {
    buffer += chunk;
    let end;
    while ((end = buffer.indexOf('\0')) !== -1) {
      const raw = buffer.slice(0, end); buffer = buffer.slice(end + 1);
      if (!raw) continue;
      let message;
      try { message = JSON.parse(raw); } catch (error) { close(error); return; }
      const request = pending.get(message.id);
      if (!request) continue;
      pending.delete(message.id); clearTimeout(request.timer);
      if (message.error) request.reject(new Error(message.error.message));
      else request.resolve(message.result);
    }
  });
  return (method, params = {}, sessionId, timeoutMs = 10000) => new Promise((resolve, reject) => {
    if (stopped) { reject(new Error('Browser connection is closed')); return; }
    const id = ++nextId;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Browser command timed out: ${method}`)); }, timeoutMs);
    pending.set(id, {resolve, reject, timer});
    child.stdio[3].write(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}) + '\0');
  });
}

async function runCase(testCase, port) {
  const screenshot = path.join(outputDir, `world-cards-${testCase.name}.png`);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'dwsync-gui-'));
  fs.rmSync(screenshot, {force:true}); // A stale capture must never satisfy this run.
  const args = ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
    '--remote-debugging-pipe', `--user-data-dir=${profile}`, 'about:blank'];
  if (process.env.CI === 'true' && process.platform !== 'win32') args.unshift('--no-sandbox');
  const child = spawn(browser, args, {windowsHide:true, detached:process.platform !== 'win32', stdio:['ignore','ignore','pipe','pipe','pipe']});
  let stderr = '', exited = false;
  child.stderr.on('data', chunk => { stderr = (stderr + String(chunk)).slice(-4000); });
  const closed = new Promise(resolve => { child.once('exit', () => { exited = true; resolve(); }); child.once('error', () => { exited = true; resolve(); }); });
  const send = connect(child);
  try {
    // Cold CI browser startup is separate from the bounded page-validation budget.
    const version = await send('Browser.getVersion', {}, undefined, 45000);
    console.log(`[BROWSER] ${browser} · ${version.product}`);
    const {targetInfos} = await send('Target.getTargets');
    const blank = targetInfos.find(target => target.type === 'page' && target.url === 'about:blank');
    const {targetId} = blank || await send('Target.createTarget', {url:'about:blank'}, undefined, 30000);
    const {sessionId} = await send('Target.attachToTarget', {targetId, flatten:true});
    await send('Emulation.setDeviceMetricsOverride', {width:testCase.width, height:testCase.height, deviceScaleFactor:1, mobile:false}, sessionId);
    await send('Page.enable', {}, sessionId);
    const fixture = testCase.fixture || 'scripts/fixtures/world_cards.html';
    const navigation = await send('Page.navigate', {url:`http://127.0.0.1:${port}/${fixture}?theme=${encodeURIComponent(testCase.theme)}&case=${encodeURIComponent(testCase.name)}`}, sessionId);
    if (navigation.errorText) throw new Error(`Navigation failed: ${navigation.errorText}`);
    const deadline = Date.now() + 25000;
    let validation;
    while (Date.now() < deadline) {
      const result = await send('Runtime.evaluate', {expression:"({status:document.documentElement.dataset.validation,detail:document.querySelector('#validation-result')?.textContent})", returnByValue:true}, sessionId);
      if (result.exceptionDetails) throw new Error('Layout fixture evaluation failed');
      validation = result.result?.value;
      if (validation?.status === 'pass' || validation?.status === 'fail') break;
      await wait(100);
    }
    // Save failures too, so CI evidence shows the offending layout.
    const capture = await send('Page.captureScreenshot', {format:'png', fromSurface:true, captureBeyondViewport:false}, sessionId);
    const png = Buffer.from(capture.data || '', 'base64');
    if (png.length < 24 || !png.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])) || png.readUInt32BE(16) !== testCase.width || png.readUInt32BE(20) !== testCase.height) throw new Error('Screenshot is missing, invalid, or the wrong viewport size');
    fs.writeFileSync(screenshot, png);
    if (validation?.status !== 'pass') throw new Error(validation?.detail || 'Browser did not return a layout result');
    return {screenshot, detail:validation.detail};
  } catch (error) {
    throw new Error(`${testCase.name}: ${error.message}${stderr ? ` · ${stderr.slice(-800)}` : ''}`);
  } finally {
    if (!exited) {
      await send('Browser.close').catch(() => {});
      await Promise.race([closed, wait(3000)]);
    }
    if (!exited) {
      if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], {windowsHide:true, timeout:5000});
      else { try { process.kill(-child.pid, 'SIGKILL'); } catch (_) { child.kill('SIGKILL'); } }
      await Promise.race([closed, wait(2000)]);
    }
    try { fs.rmSync(profile, {recursive:true, force:true, maxRetries:5, retryDelay:100}); }
    catch (error) { console.warn(`[WARN] Browser profile cleanup: ${error.message}`); }
  }
}

async function main() {
  if (!browser) throw new Error('Edge/Chromium was not found for GUI validation.');
  fs.mkdirSync(outputDir, {recursive:true});
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const cases = [{name:'dark-desktop',theme:'dark',width:1100,height:900}, {name:'light-desktop',theme:'light',width:1100,height:900}, {name:'light-mobile',theme:'light',width:430,height:1100}, {name:'placard-flip',theme:'glass',width:720,height:720,fixture:'scripts/fixtures/website_placard_flip.html'}];
  try {
    for (const testCase of cases) {
      const result = await runCase(testCase, server.address().port);
      console.log(`[OK] ${testCase.name}: ${result.detail}; verified screenshot ${result.screenshot}`);
    }
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}
if (require.main === module) main().catch(error => { console.error(`[ERROR] ${error.message}`); process.exitCode = 1; });
module.exports = {connect};
