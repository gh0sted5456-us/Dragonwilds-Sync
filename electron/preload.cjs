const { contextBridge, ipcRenderer } = require('electron');

// Safe, read-only launch context only. No credential, filesystem or scheduler
// authority is exposed here; all mutable work remains RPC/backend owned.
contextBridge.exposeInMainWorld('dragonwildsV3', {
  createQuickShortcut: (data) => ipcRenderer.invoke('dragonwilds:create-v3-quick-shortcut', data || {}),
  quickContext: () => ({
    enabled: process.env.DWS_V3_QUICK === '1',
    profileId: String(process.env.DWS_V3_QUICK_PROFILE || ''),
    mode: ['player', 'coop', 'server'].includes(String(process.env.DWS_V3_QUICK_MODE || '')) ? String(process.env.DWS_V3_QUICK_MODE) : 'player',
    autoStart: process.env.DWS_V3_QUICK_AUTOSTART === '1',
  }),
});

require('./preload-v2.cjs');
