const path = require('path');
const { app, BrowserWindow } = require('electron');

let settled = false;
function finish(code, message) {
  if (settled) return;
  settled = true;
  if (code === 0) console.log(message);
  else console.error(message);
  app.exit(code);
}

app.commandLine.appendSwitch('disable-gpu');
app.whenReady().then(async () => {
  const window = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: path.join(__dirname, '..', 'electron', 'preload-v2.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.webContents.on('preload-error', (_event, preloadPath, error) => {
    finish(1, `Sandbox preload failed (${preloadPath}): ${error?.stack || error}`);
  });
  await window.loadURL('data:text/html;charset=utf-8,%3Ctitle%3EDragonwilds%20preload%20smoke%3C%2Ftitle%3E');
  const bridges = await window.webContents.executeJavaScript(`({
    dragonwilds: typeof window.dragonwilds,
    dragonwildsV3: typeof window.dragonwildsV3,
    invoke: typeof window.dragonwilds?.invoke,
    quickContext: typeof window.dragonwildsV3?.quickContext
  })`);
  window.destroy();
  if (bridges.dragonwilds !== 'object' || bridges.dragonwildsV3 !== 'object' || bridges.invoke !== 'function' || bridges.quickContext !== 'function') {
    finish(1, `Sandbox preload bridge is incomplete: ${JSON.stringify(bridges)}`);
    return;
  }
  finish(0, 'Sandbox preload bridge smoke test passed');
}).catch((error) => finish(1, `Sandbox preload bridge smoke test failed: ${error?.stack || error}`));

setTimeout(() => finish(1, 'Sandbox preload bridge smoke test timed out'), 15000);
