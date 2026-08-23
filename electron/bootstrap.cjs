// Dragonwilds Sync Electron bootstrap — V3 Quick-aware.
// Quick is a presentation mode. It keeps the same service/runtime authority;
// main-v2 owns mode-aware background services so a Quick process can promote
// itself into the full application without inheriting permanently suppressed
// timers.
const electron = require('electron');

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
