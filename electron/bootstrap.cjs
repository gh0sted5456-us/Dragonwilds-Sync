// Dragonwilds Sync Electron bootstrap.
// Keep main.cjs focused on application behavior while this wrapper installs
// process/window guards before the main process creates any BrowserWindow.
const electron = require('electron');

// Electron can surface an uncaught "Object has been destroyed" exception when
// a third-party browser window closes while its download/session cleanup is
// racing the WebContents teardown. It is safe to ignore only this known close
// race; every other uncaught exception is still surfaced normally.
process.on('uncaughtException', (error) => {
  const text = String(error?.stack || error?.message || error || '');
  if (/object has been destroyed|webcontents.*destroyed/i.test(text)) {
    console.warn('[browser-close] ignored WebContents teardown race:', error?.message || text);
    return;
  }
  console.error('[uncaughtException]', error);
  process.exitCode = 1;
});

// Give ordinary framed browser windows a Dragonwilds Sync titlebar. The main
// launcher and custom frameless native dialogs keep their existing chrome.
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
