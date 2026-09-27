// electron/preload.js
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  isElectron: true,
  platform: process.platform,   // "win32" | "linux" | "darwin" — drives the create-world default
  pickDirectory: () => ipcRenderer.invoke("pick-directory"),
  pickZip: () => ipcRenderer.invoke("pick-zip"),
  getSystemTheme: () => ipcRenderer.invoke("get-theme"),
  getSystemLocale: () => ipcRenderer.invoke("get-system-locale"),
  openPath: (p) => ipcRenderer.invoke("open-path", p),
  getAutoLaunch: () => ipcRenderer.invoke("get-auto-launch"),
  setAutoLaunch: (enabled) => ipcRenderer.invoke("set-auto-launch", enabled),
  getCloseToTray: () => ipcRenderer.invoke("get-close-to-tray"),
  setCloseToTray: (enabled) => ipcRenderer.invoke("set-close-to-tray", enabled),
  // Remote Access: apply the same-network (LAN) bind by restarting the local server.
  getLanBind: () => ipcRenderer.invoke("remote-get-lanbind"),
  setLanBind: (enabled) => ipcRenderer.invoke("remote-set-lanbind", enabled),
});
