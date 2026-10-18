// electron/preload.js
const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  isElectron: true,
  nativeSplash: true,
  getStartupState: () => ipcRenderer.invoke("startup-state"),
  enterStartup: () => ipcRenderer.invoke("startup-enter"),
  onStartupStatus: (listener) => {
    const handler = (_event, state) => listener(state);
    ipcRenderer.on("startup-status", handler);
    return () => ipcRenderer.removeListener("startup-status", handler);
  },
  platform: process.platform,   // "win32" | "linux" | "darwin" — drives the create-world default
  pickDirectory: () => ipcRenderer.invoke("pick-directory"),
  pickServerExecutable: () => ipcRenderer.invoke("pick-server-executable"),
  pickClientExecutable: () => ipcRenderer.invoke("pick-client-executable"),
  pickZip: () => ipcRenderer.invoke("pick-zip"),
  getPathForFile: (file) => webUtils.getPathForFile(file),
  pickWorldSave: () => ipcRenderer.invoke("pick-world-save"),
  getSystemTheme: () => ipcRenderer.invoke("get-theme"),
  setWindowTheme: (theme) => ipcRenderer.invoke("window-theme", theme),
  openPath: (p) => ipcRenderer.invoke("open-path", p),
  cloudAccountStatus: () => ipcRenderer.invoke("cloud-account-status"),
  connectCloudAccount: (request) => ipcRenderer.invoke("cloud-account-connect", request),
  disconnectCloudAccount: (provider) => ipcRenderer.invoke("cloud-account-disconnect", provider),
  publishCloudExport: (request) => ipcRenderer.invoke("cloud-publish", request),
  setCloudAutoPublish: (request) => ipcRenderer.invoke("cloud-auto-publish", request),
  onCloudPublishProgress: (listener) => {
    const handler = (_event, progress) => listener(progress);
    ipcRenderer.on("cloud-publish-progress", handler);
    return () => ipcRenderer.removeListener("cloud-publish-progress", handler);
  },
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
