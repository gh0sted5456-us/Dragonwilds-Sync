// electron/preload.js
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  isElectron: true,
  platform: process.platform,   // "win32" | "linux" | "darwin" — drives the create-world default
  pickDirectory: () => ipcRenderer.invoke("pick-directory"),
  pickServerExecutable: () => ipcRenderer.invoke("pick-server-executable"),
  pickClientExecutable: () => ipcRenderer.invoke("pick-client-executable"),
  pickZip: () => ipcRenderer.invoke("pick-zip"),
  pickWorldSave: () => ipcRenderer.invoke("pick-world-save"),
  getSystemTheme: () => ipcRenderer.invoke("get-theme"),
  openPath: (p) => ipcRenderer.invoke("open-path", p),
  openExternal: (value) => ipcRenderer.invoke("open-external", value),
  launchWorld: (request) => ipcRenderer.invoke("launch-world", request),
  openModProvider: (request) => ipcRenderer.invoke("open-mod-provider", request),
  onModProviderDownloadComplete: (listener) => {
    const handler = (_event, result) => listener(result);
    ipcRenderer.on("mod-provider-download-complete", handler);
    return () => ipcRenderer.removeListener("mod-provider-download-complete", handler);
  },
  installAppUpdate: (asset) => ipcRenderer.invoke("install-app-update", asset),
  onAppUpdateProgress: (listener) => {
    const handler = (_event, progress) => listener(progress);
    ipcRenderer.on("app-update-progress", handler);
    return () => ipcRenderer.removeListener("app-update-progress", handler);
  },
  createProfileShortcut: (profile) => ipcRenderer.invoke("create-profile-shortcut", profile),
  getAutoLaunch: () => ipcRenderer.invoke("get-auto-launch"),
  setAutoLaunch: (enabled) => ipcRenderer.invoke("set-auto-launch", enabled),
  getCloseToTray: () => ipcRenderer.invoke("get-close-to-tray"),
  setCloseToTray: (enabled) => ipcRenderer.invoke("set-close-to-tray", enabled),
  // Remote Access: apply the same-network (LAN) bind by restarting the local server.
  getLanBind: () => ipcRenderer.invoke("remote-get-lanbind"),
  setLanBind: (enabled) => ipcRenderer.invoke("remote-set-lanbind", enabled),
});
