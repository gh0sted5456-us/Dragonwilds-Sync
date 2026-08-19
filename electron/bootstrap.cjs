// Dragonwilds Sync Electron bootstrap — V3 Quick-aware.
// Quick is a presentation mode. It keeps the same service/runtime authority but
// suppresses desktop-only periodic work before the retained main module starts.
const electron = require('electron');

const argv = process.argv.slice(1);
const quickRequested = argv.includes('--quick') || argv.includes('--quick-launch') || argv.includes('--minimal-mode');
if (quickRequested) {
  process.env.DWS_V3_QUICK = '1';
  const suppressedBackgroundCallbacks = new Set(['maybeBenchmark', 'backgroundTick', 'rsdwModuleTick']);
  const nativeSetTimeout = global.setTimeout;
  const nativeSetInterval = global.setInterval;
  global.setTimeout = function dragonwildsQuickTimeout(callback, delay, ...args) {
    if (suppressedBackgroundCallbacks.has(String(callback?.name || ''))) return null;
    return nativeSetTimeout(callback, delay, ...args);
  };
  global.setInterval = function dragonwildsQuickInterval(callback, delay, ...args) {
    if (suppressedBackgroundCallbacks.has(String(callback?.name || ''))) return null;
    return nativeSetInterval(callback, delay, ...args);
  };
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
