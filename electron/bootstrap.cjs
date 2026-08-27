// Dragonwilds Sync Electron bootstrap — V3 Quick-aware.
// Quick is a presentation mode. It keeps the same service/runtime authority;
// main-v2 owns mode-aware background services so a Quick process can promote
// itself into the full application without inheriting permanently suppressed
// timers.
const electron = require('electron');

// Terminal/SSH operation uses the same packaged Python control plane but does
// not load main.cjs, BrowserWindow, a renderer, the tray, or Discord presence.
// The child inherits the caller's terminal so logs and Ctrl+C behave like a
// normal headless server process.
if (process.argv.includes('--headless')) {
  const { spawn } = require('child_process');
  const path = require('path');
  const fs = require('fs');
  const marker = process.argv.indexOf('--headless');
  const headlessArgs = process.argv.slice(marker);
  const packagedService = path.join(process.resourcesPath, 'backend', process.platform === 'win32' ? 'DragonwildsSync.Service.exe' : 'DragonwildsSync.Service');
  const sourceService = path.join(__dirname, '..', 'backend', 'dragonwilds_service.py');
  const command = fs.existsSync(packagedService) ? packagedService : (process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'));
  const args = fs.existsSync(packagedService) ? headlessArgs : [sourceService, ...headlessArgs];
  const child = spawn(command, args, { stdio: 'inherit', windowsHide: false, env: { ...process.env, PYTHONUNBUFFERED: '1' } });
  let forwarded = false;
  const forward = (signal) => {
    if (forwarded || child.killed) return;
    forwarded = true;
    try { child.kill(signal); } catch (_) {}
  };
  process.once('SIGINT', () => forward('SIGINT'));
  process.once('SIGTERM', () => forward('SIGTERM'));
  child.once('error', (error) => { console.error(`Unable to start headless service: ${error.message}`); process.exit(4); });
  child.once('exit', (code, signal) => { process.exit(Number.isInteger(code) ? code : (signal ? 130 : 4)); });
  return;
}

// Preserve the established Minimal Mode detection expression as a compatibility
// contract while extending the same lean bootstrap behavior to V3 Quick modes.
const minimalMode = process.argv.includes('--minimal-mode');
const quickRequested = process.argv.includes('--quick') || process.argv.includes('--quick-launch') || minimalMode;
if (quickRequested) {
  process.env.DWS_V3_QUICK = '1';
}

process.on('uncaughtException', (error) => {
  const text = String(error?.stack || error?.message || error || '');
  if (/object has been destroyed|webcontents.*destroyed/i.test(text)) {
    console.warn('[browser-close] ignored WebContents teardown race:', error?.message || text);
    return;
  }
  console.error('[uncaughtException]', error);
  process.exitCode = 1;
});

try {
  const NativeBrowserWindow = electron.BrowserWindow;
  class DragonwildsBrowserWindow extends NativeBrowserWindow {
    constructor(options = {}) {
      const next = { ...options };
      if (next.frame !== false && !next.titleBarStyle) {
        next.titleBarStyle = 'hidden';
        next.titleBarOverlay = { color: '#111817', symbolColor: '#dfc778', height: 38 };
        next.backgroundColor ||= '#0b0f10';
      }
      super(next);
    }
  }
  electron.BrowserWindow = DragonwildsBrowserWindow;
} catch (error) {
  console.warn('[bootstrap] BrowserWindow theme hook unavailable:', error?.message || error);
}

require('./main.cjs');
