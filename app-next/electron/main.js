// electron/main.js
const { app, BrowserWindow, ipcMain, dialog, shell, nativeTheme, Menu, Tray, nativeImage, utilityProcess } = require("electron");

// Run without Chromium's sandbox on Linux (issue #32). The AppImage mounts read-only,
// so its bundled chrome-sandbox can't be setuid-root, and server distros often restrict
// unprivileged user namespaces and/or run as root — all of which make Chromium abort
// with "The SUID sandbox helper binary ... is not configured correctly". Disabling the
// sandbox is safe here: the renderer only ever loads this app's own 127.0.0.1 UI (external
// links open in the system browser), so there's no untrusted web content to contain. This
// also lets the app run as root, which is common on a headless server.
if (process.platform === "linux") app.commandLine.appendSwitch("no-sandbox");
const path = require("path");
const fs = require("fs");
const os = require("os");
const { spawnSync } = require("child_process");
const http = require("http");
const net = require("net");
const crypto = require("crypto");

const isDev = process.env.NODE_ENV === "development";
let PORT = 4317;
let SHARE_PORT = 4318;
const INSTANCE_TOKEN = crypto.randomBytes(24).toString("hex");

// Per-launch secret proving a request is the trusted desktop app rather than a Remote
// Access guest (lib/remoteauth). Passed to the server as env and pre-set as an HttpOnly
// cookie on this window's session, so a network guest — who has neither — can never be
// mistaken for the admin, even when a raw-TCP tunnel makes their request look like
// 127.0.0.1. Regenerated every launch.
const ADMIN_TOKEN = crypto.randomBytes(24).toString("hex");
let mainWindow = null;
let nextProc = null;
let shareProc = null;
let serverReady = false;
let pendingRoute = null;
let tray = null;
let startupPortsPromise = null;
let startupServerPromise = null;
let nextExit = null;
let startupFailure = "";

// Set the moment a real quit is requested (tray Quit, or before-quit) so the window's
// close handler knows to actually close instead of hiding to the tray.
let quitting = false;
let quitCleanupStarted = false;
let quitCleanupFinished = false;

// True when the app was launched at login rather than opened by hand — used to start
// straight to the tray without a window (feature: autostart to tray). Set in main().
let launchedHidden = false;

// The executable is portable, but application state is deliberately kept in
// Electron's normal per-user local data directory. Never bind Chromium cache,
// SQLite, logs, SteamCMD, or backups to the folder containing the portable EXE.
// This mirrors main and keeps launch speed independent of where the EXE is stored.

// ---------------------------------------------------------------------------
// SINGLE INSTANCE LOCK — prevents the "infinite windows" cascade.
// If a second copy launches, focus the existing window instead of spawning one.
// ---------------------------------------------------------------------------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", (_event, argv) => {
    // A second launch (e.g. clicking the shortcut again) reveals the running app,
    // creating the window if it started to the tray.
    showWindow(null, launchRoute(argv));
  });
  main();
}

function dataDir() {
  return app.getPath("userData");
}

// Which host the Next server should bind to. Loopback by default (unchanged behaviour);
// 0.0.0.0 once the user turns on same-network access in Remote Access. The choice is
// mirrored into a tiny marker file by the /api/remote/config route (the DB is the source
// of truth), so we can read it here without opening sqlite before the server is up.
function sharingEnabled() {
  try {
    const raw = fs.readFileSync(path.join(dataDir(), "remote-bind.json"), "utf8");
    return JSON.parse(raw).host === "0.0.0.0";
  } catch {}
  return false;
}

function resourcePath() {
  // In a packaged app, the standalone server lives under resources/app.
  return path.join(process.resourcesPath, "app");
}

function bundledRuntime() {
  const base = resourcePath();
  const serverPath = path.join(base, "server.js");
  const buildIdPath = path.join(base, ".next", "BUILD_ID");
  if (!fs.existsSync(serverPath)) throw new Error(`The packaged interface entry point is missing (${serverPath}). Download the complete portable build; do not copy individual files out of it.`);
  if (!fs.existsSync(buildIdPath)) throw new Error(`The packaged interface runtime is incomplete (${buildIdPath} is missing). Download a complete portable build.`);
  return { base, serverPath };
}

function logToFile(msg) {
  try {
    fs.appendFileSync(path.join(dataDir(), "launcher.log"), `[${new Date().toISOString()}] ${msg}\n`);
  } catch {}
}

// ---------------------------------------------------------------------------
// LAUNCH ON STARTUP — explicit opt-in. Fresh installs and upgrades that have
// never chosen a value stay off; opening RSDW Sync must never surprise-launch
// itself at Windows/Linux login.
//
// Windows uses Electron's own Run-key API. Linux has no Electron equivalent,
// so we manage a .desktop file under ~/.config/autostart ourselves. (No macOS
// build is shipped, so it's left untouched with a best-effort fallback.)
// ---------------------------------------------------------------------------
const LINUX_AUTOSTART_FILE = path.join(os.homedir(), ".config", "autostart", "com.dwsm.servermanager.desktop");

function autostartConfigPath() {
  return path.join(dataDir(), "autostart.json");
}

function readAutostartPref() {
  try {
    const v = JSON.parse(fs.readFileSync(autostartConfigPath(), "utf8")).enabled;
    return typeof v === "boolean" ? v : null;
  } catch {
    return null; // never chosen yet
  }
}

function writeAutostartPref(enabled) {
  try { fs.writeFileSync(autostartConfigPath(), JSON.stringify({ enabled })); } catch (e) { logToFile(`Failed to persist autostart pref: ${e.message}`); }
}

function applyAutostart(enabled) {
  if (process.platform === "linux") {
    try {
      if (enabled) {
        fs.mkdirSync(path.dirname(LINUX_AUTOSTART_FILE), { recursive: true });
        // Prefer the original AppImage path (electron-builder sets $APPIMAGE at
        // launch) over process.execPath, which for an AppImage points at the
        // extracted runtime binary rather than the file the user actually has.
        const exe = process.env.APPIMAGE || process.execPath;
        // --hidden makes the login launch start straight to the tray (no window). A
        // manual launch from the menu carries no such flag, so it opens normally.
        const entry = [
          "[Desktop Entry]",
          "Type=Application",
          "Name=RSDW Sync",
          `Exec="${exe}" --hidden`,
          "X-GNOME-Autostart-enabled=true",
          "",
        ].join("\n");
        fs.writeFileSync(LINUX_AUTOSTART_FILE, entry);
      } else {
        fs.rmSync(LINUX_AUTOSTART_FILE, { force: true });
      }
    } catch (e) { logToFile(`Linux autostart update failed: ${e.message}`); }
    return;
  }
  // Windows (and, best-effort, any other platform): Electron owns this natively.
  // args:["--hidden"] so the login launch starts to the tray; openAsHidden covers the
  // platforms that honour it. A hand-launched copy gets neither and opens a window.
  try { app.setLoginItemSettings({ openAtLogin: enabled, openAsHidden: enabled, args: ["--hidden"] }); } catch (e) { logToFile(`setLoginItemSettings failed: ${e.message}`); }
}

function initAutostart() {
  let enabled = readAutostartPref();
  if (enabled === null) {
    enabled = false;
    writeAutostartPref(false);
  }
  applyAutostart(enabled);
}

// ---------------------------------------------------------------------------
// CLOSE TO TRAY — when on (the default), the window's close button hides the app
// to the system tray instead of quitting, so servers keep running in the
// background. Off makes the close button quit as before. Persisted next to the
// other launcher prefs so it survives updates.
// ---------------------------------------------------------------------------
function closeToTrayConfigPath() {
  return path.join(dataDir(), "closetotray.json");
}
function readCloseToTrayPref() {
  try {
    const v = JSON.parse(fs.readFileSync(closeToTrayConfigPath(), "utf8")).enabled;
    return typeof v === "boolean" ? v : true;
  } catch {
    return true; // default on
  }
}
function writeCloseToTrayPref(enabled) {
  try { fs.writeFileSync(closeToTrayConfigPath(), JSON.stringify({ enabled: !!enabled })); }
  catch (e) { logToFile(`Failed to persist close-to-tray pref: ${e.message}`); }
}

// ---------------------------------------------------------------------------
// SYSTEM TRAY — a persistent icon whose menu opens the app, jumps straight to a
// specific world, or quits. On Linux tray support depends on a StatusNotifier
// host (libappindicator); if creating it throws, we swallow it and carry on
// without a tray rather than failing to launch.
// ---------------------------------------------------------------------------
function trayIconPath() {
  const base = isDev
    ? path.join(__dirname, "..", "public")
    : path.join(process.resourcesPath, "app", "public");
  return path.join(base, process.platform === "win32" ? "icon.ico" : "icon.png");
}

// Pull the world list from the local server for the tray menu. DB-only endpoint, so
// it's cheap to call on every menu refresh. Never rejects — a failure yields [].
function fetchWorlds() {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${PORT}/api/tray`, (res) => {
      let data = "";
      res.on("data", (d) => (data += d));
      res.on("end", () => {
        try { const j = JSON.parse(data); resolve(Array.isArray(j.worlds) ? j.worlds : []); }
        catch { resolve([]); }
      });
    });
    req.on("error", () => resolve([]));
    req.setTimeout(1500, () => { req.destroy(); resolve([]); });
  });
}

// Show the main window (creating it if the app started to the tray), optionally
// navigating to a specific world first.
function launchRoute(argv = process.argv) {
  const profileArg = argv.find((arg) => String(arg).startsWith("--profile="));
  const roleArg = argv.find((arg) => String(arg).startsWith("--role="));
  if (!profileArg) return null;
  const id = profileArg.slice("--profile=".length);
  const role = roleArg?.slice("--role=".length) === "server" ? "server" : "player";
  const autoplay = argv.includes("--autoplay") && role === "player";
  return `/profiles/${encodeURIComponent(id)}/${role}${autoplay ? "?autoplay=1" : ""}`;
}

function portAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen(port, "127.0.0.1", () => server.close(() => resolve(true)));
  });
}

async function choosePrivatePort() {
  if (isDev) return 4317;
  for (let candidate = 4317; candidate < 4417; candidate++) if (await portAvailable(candidate)) return candidate;
  throw new Error("No available local application port was found.");
}

async function chooseSharePort() {
  if (isDev) return 4318;
  for (let candidate = 4418; candidate < 4518; candidate++) {
    if (candidate !== PORT && await portAvailable(candidate)) return candidate;
  }
  throw new Error("No available sharing port was found.");
}

function showWindow(worldId, route) {
  if (worldId) pendingRoute = `/worlds/${encodeURIComponent(worldId)}`;
  else if (route) pendingRoute = route;
  if (!mainWindow) createWindow();
  const win = mainWindow;
  if (!win) return;
  if (serverReady) loadAppIntoWindow(pendingRoute);
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function loadingPage(message = "Starting RSDW Sync…") {
  const safeMessage = escapeHtml(message);
  const html = `<!doctype html><html><body style="margin:0;background:#202427;color:#eee;font-family:Segoe UI,system-ui,sans-serif;display:grid;place-items:center;height:100vh">
    <div style="text-align:center">
      <div style="font-size:28px;font-weight:700;margin-bottom:10px">RSDW Sync</div>
      <div style="color:#c1a56d;font-size:14px">${safeMessage}</div>
    </div>
  </body></html>`;
  return "data:text/html;charset=utf-8," + encodeURIComponent(html);
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function loadAppIntoWindow(route = null) {
  if (!mainWindow || !serverReady) return;
  const base = isDev ? process.env.ELECTRON_START_URL : `http://127.0.0.1:${PORT}`;
  const target = route || pendingRoute || "";
  pendingRoute = null;
  mainWindow.loadURL(`${base}${target}`).catch((error) => {
    logToFile(`UI navigation failed after readiness check: ${error.message}`);
    if (mainWindow) mainWindow.loadURL(loadingPage("Interface startup failed — see launcher.log"));
  });
}

async function refreshTrayMenu() {
  if (!tray) return;
  const worlds = await fetchWorlds();
  const worldItems = worlds.length
    ? worlds.map((w) => ({
        label: `${w.running ? "● " : "○ "}${w.display_name}`,
        click: () => showWindow(w.world_id),
      }))
    : [{ label: "No worlds yet", enabled: false }];

  const menu = Menu.buildFromTemplate([
    { label: "Open RSDW Sync", click: () => showWindow() },
    { type: "separator" },
    { label: "Worlds", enabled: false },
    ...worldItems,
    { type: "separator" },
    { label: "Quit", click: () => { quitting = true; app.quit(); } },
  ]);
  tray.setContextMenu(menu);
}

function createTray() {
  if (tray) return true;
  try {
    // Prefer the provided icon files (public/icon.ico / public/icon.png). If
    // those were replaced by the user in the repo's public/ folder they will be
    // used here when running from source; packaged apps use the embedded copy.
    let img = nativeImage.createFromPath(trayIconPath());
    if (img.isEmpty()) img = nativeImage.createFromPath(path.join(__dirname, "..", "public", "icon.png"));
    if (img.isEmpty()) img = nativeImage.createEmpty();
    tray = new Tray(img);
  tray.setToolTip("RSDW Sync");
    // Left-click opens the app (Windows/Linux convention); the menu is right-click.
    tray.on("click", () => showWindow());
    setImmediate(() => { refreshTrayMenu().catch(() => {}); });
    // Keep the world list (names, running dots) current without the window open.
    setInterval(() => { refreshTrayMenu().catch(() => {}); }, 20000);
    return true;
  } catch (e) {
    logToFile(`Tray unavailable: ${e.message}`);
    tray = null;
    return false;
  }
}

function startNextServer() {
  if (isDev) return null; // dev uses `next dev` started by the npm script

  const { base, serverPath } = bundledRuntime();

  const env = {
    ...process.env,
    PORT: String(PORT),
    // The desktop UI is always loopback-only. LAN sharing runs in its own subprocess.
    HOSTNAME: "127.0.0.1",
    // The desktop app's proof-of-trust for Remote Access (see ADMIN_TOKEN above).
    DWSM_ADMIN_TOKEN: ADMIN_TOKEN,
    NODE_ENV: "production",
    APP_MANAGER_DATA_DIR: dataDir(),
    // Expose the installed app version to the server so the UI can check for updates.
    APP_MANAGER_APP_VERSION: app.getVersion(),
    APP_MANAGER_PORT: String(PORT),
    APP_MANAGER_SHARE_PORT: String(SHARE_PORT),
    APP_MANAGER_INSTANCE_TOKEN: INSTANCE_TOKEN,
    // Use the pure-WASM SQLite backend, which needs no experimental flag and no
    // specific Node/Electron version — this is what makes the packaged app start
    // reliably regardless of the Electron-bundled Node version.
    PSM_SQLITE_BACKEND: "wasm",
    NODE_OPTIONS: `${process.env.NODE_OPTIONS || ""} --no-warnings`.trim(),
  };

  // Use Electron's Node utility process instead of asking Windows to execute a
  // .js file through process.execPath. This is independent of system JavaScript
  // file associations and avoids relaunching the portable GUI executable.
  nextExit = null;
  const child = utilityProcess.fork(serverPath, [], {
    env,
    cwd: base,
    stdio: "pipe",
    serviceName: "RSDW Sync Interface",
  });
  nextProc = child;
  child.stdout?.on("data", (d) => logToFile(`[next] ${d.toString().trim()}`));
  child.stderr?.on("data", (d) => logToFile(`[next:err] ${d.toString().trim()}`));
  child.on("spawn", () => logToFile(`Interface process started (pid=${child.pid || "unknown"})`));
  child.on("exit", (code) => {
    nextExit = { code, at: Date.now() };
    if (nextProc === child) nextProc = null;
    serverReady = false;
    logToFile(`Interface process exited: ${code}`);
  });
  return child;
}


function startShareServer() {
  if (isDev || shareProc || !sharingEnabled()) return;
  const proxyPath = path.join(__dirname, "share-proxy.js");
  if (!fs.existsSync(proxyPath)) {
    logToFile(`Share proxy missing: ${proxyPath}`);
    return;
  }

  const env = {
    ...process.env,
    RSDW_UI_PORT: String(PORT),
    RSDW_SHARE_PORT: String(SHARE_PORT),
    NODE_OPTIONS: `${process.env.NODE_OPTIONS || ""} --no-warnings`.trim(),
  };

  const child = utilityProcess.fork(proxyPath, [], {
    env,
    cwd: __dirname,
    stdio: "pipe",
    serviceName: "RSDW Sync LAN Proxy",
  });
  shareProc = child;
  child.stdout?.on("data", (d) => logToFile(`[share] ${d.toString().trim()}`));
  child.stderr?.on("data", (d) => logToFile(`[share:err] ${d.toString().trim()}`));
  child.on("exit", (code) => {
    logToFile(`Share proxy exited: ${code}`);
    if (shareProc === child) shareProc = null;
  });
}

async function stopShareServer() {
  const proc = shareProc;
  if (!proc) return true;
  return new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; shareProc = null; resolve(true); } };
    proc.once("exit", finish);
    try { proc.kill(); } catch { finish(); }
    setTimeout(finish, 4000);
  });
}

function bundledRuntimeProblem() {
  if (isDev) return null;
  try { bundledRuntime(); return null; }
  catch (error) { return error.message; }
}

// Restart only the local UI server so a changed bind host (loopback ↔ 0.0.0.0)
 // takes effect. This never boots schedulers, game servers, runtime managers, or
 // any other background engine.
async function restartNextServer() {
  if (isDev) return false;
  await new Promise((resolve) => {
    const p = nextProc;
    if (!p) return resolve();
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    p.once("exit", finish);
    try { p.kill(); } catch { finish(); }
    setTimeout(finish, 4000); // never hang the UI on a stuck child
  });
  nextProc = null;
  startNextServer();
  const base = `http://127.0.0.1:${PORT}`;
  const up = await waitForServer(base, 30000);
  serverReady = up;
  return up;
}

function pingServer(url) {
  return new Promise((resolve) => {
    const req = http.get(`${url}/api/app/instance`, (res) => {
      let body = "";
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        try { resolve(isDev ? res.statusCode === 200 : JSON.parse(body).token === INSTANCE_TOKEN); }
        catch { resolve(false); }
      });
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1000, () => { req.destroy(); resolve(false); });
  });
}

async function waitForServer(url, maxMs = 60000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    if (await pingServer(url)) return true;
    if (!isDev && nextExit) return false;
    await new Promise((r) => setTimeout(r, 150));
  }
  return false;
}

function requestManagedServerShutdown() {
  return new Promise((resolve) => {
    if (!serverReady) return resolve(false);
    const req = http.request({
      hostname: "127.0.0.1",
      port: PORT,
      path: "/api/app/shutdown",
      method: "POST",
      headers: {
        "x-rsdw-admin-token": ADMIN_TOKEN,
        "content-length": "0",
      },
    }, (res) => {
      res.resume();
      res.on("end", () => resolve(res.statusCode >= 200 && res.statusCode < 300));
    });
    req.on("error", (e) => {
      logToFile(`Managed server shutdown request failed: ${e.message}`);
      resolve(false);
    });
    req.setTimeout(12000, () => {
      req.destroy();
      resolve(false);
    });
    req.end();
  });
}

function createWindow() {
  if (mainWindow) { mainWindow.focus(); return; } // never create a second window

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 940,
    minHeight: 640,
    backgroundColor: "#202427",
    title: "RSDW Sync",
    autoHideMenuBar: true,   // hide File/Edit/View menu bar (Discord-like)
    icon: isDev
      ? path.join(__dirname, "..", "public", process.platform === "win32" ? "icon.ico" : "icon.png")
      : path.join(process.resourcesPath, "app", "public", process.platform === "win32" ? "icon.ico" : "icon.png"),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      // Don't throttle timers/rendering when this window is minimized or occluded —
      // the managed game server free-rides on our timer resolution (issue #29).
      backgroundThrottling: false,
    },
  });

  // Remove the application menu entirely (no File/Edit/Window bar).
  Menu.setApplicationMenu(null);
  mainWindow.setMenuBarVisibility(false);

  // Pre-set the admin trust cookie on this window's session BEFORE the first navigation,
  // so the desktop app is recognised as the trusted admin from the very first request.
  // It's HttpOnly (invisible to page JS) and only ever lives in this Electron session —
  // a remote guest's browser has no way to obtain it.
  mainWindow.webContents.session.cookies
    .set({ url: `http://127.0.0.1:${PORT}`, name: "dwsm_admin", value: ADMIN_TOKEN, httpOnly: true, sameSite: "lax" })
    .catch(() => {})
    .finally(() => {
      if (!mainWindow) return;
      mainWindow.loadURL(loadingPage());
    });

  // Don't auto-show when we launched straight to the tray — the window is built so a
  // tray click has something to reveal, but it stays hidden until asked for.
  mainWindow.once("ready-to-show", () => {
    logToFile(`Window ready (hidden=${launchedHidden})`);
    if (!launchedHidden) { mainWindow.show(); mainWindow.focus(); }
  });

  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    logToFile(`Renderer exited: reason=${details.reason || "unknown"} code=${details.exitCode ?? "unknown"}`);
  });
  mainWindow.webContents.on("did-fail-load", (_event, code, description, url, isMainFrame) => {
    if (isMainFrame) logToFile(`Window load failed: code=${code} description=${description} url=${url}`);
  });
  mainWindow.on("unresponsive", () => logToFile("Window became unresponsive"));
  mainWindow.on("responsive", () => logToFile("Window became responsive again"));

  // Close-to-tray: unless a real quit is underway (or the pref is off, or there's no
  // tray to hide into), the close button hides the window and leaves the app running.
  mainWindow.on("close", (e) => {
    if (!quitting && tray && readCloseToTrayPref()) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
  mainWindow.on("closed", () => (mainWindow = null));

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url).catch(() => {});
    return { action: "deny" };
  });
}

function showErrorWindow(message) {
  if (mainWindow) return;
  mainWindow = new BrowserWindow({
    width: 720, height: 420, backgroundColor: "#202427",
    autoHideMenuBar: true, title: "RSDW Sync",
  });
  Menu.setApplicationMenu(null);
  const html = `<!doctype html><html><body style="font-family:Segoe UI,system-ui,sans-serif;background:#0e0e0e;color:#f3efe7;padding:40px;line-height:1.6">
    <h2 style="color:#d4a13d">RSDW Sync couldn't start its interface</h2>
    <p>${escapeHtml(message)}</p>
    <p style="color:#918879;font-size:13px">A log was written to:<br><code>${escapeHtml(path.join(dataDir(), "launcher.log"))}</code></p>
    </body></html>`;
  mainWindow.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(html));
  mainWindow.on("closed", () => (mainWindow = null));
}

function beginUiBootstrap() {
  if (startupServerPromise) return startupServerPromise;
  startupServerPromise = (async () => {
    try {
      startupPortsPromise ||= Promise.all([choosePrivatePort(), chooseSharePort()]);
      const [uiPort, sharePort] = await startupPortsPromise;
      PORT = uiPort;
      SHARE_PORT = sharePort;
      logToFile(`Selected local UI port ${PORT}; share port ${SHARE_PORT}`);

      const runtimeProblem = bundledRuntimeProblem();
      if (runtimeProblem) throw new Error(runtimeProblem);

      startNextServer();
      const base = `http://127.0.0.1:${PORT}`;
      const ready = await waitForServer(base, 30000);
      if (!ready) {
        const suffix = nextExit ? ` (interface process exited with code ${nextExit.code})` : "";
        throw new Error(`The bundled interface server did not become ready${suffix}.`);
      }
      serverReady = true;
      return true;
    } catch (error) {
      startupFailure = error.message;
      logToFile(`UI bootstrap failed: ${error.message}`);
      return false;
    }
  })();
  return startupServerPromise;
}

function devServerPort() {
  try { return Number(new URL(process.env.ELECTRON_START_URL).port || 80); }
  catch { return 4317; }
}

// Port selection can overlap Electron initialization. The actual Node utility
// process starts only after ready, which is required by Electron and prevents a
// packaged .js entry point from ever being handed to the operating system.
if (!isDev) startupPortsPromise = Promise.all([choosePrivatePort(), chooseSharePort()]);

function main() {
  app.whenReady().then(async () => {
    // Ensures Windows uses our icon (not the default Electron one) in the taskbar.
  if (process.platform === "win32") app.setAppUserModelId("com.dwsm.servermanager");
    // Did we launch at login rather than by hand?
    launchedHidden = process.argv.includes("--hidden");
    pendingRoute = launchRoute();

    const started = isDev
      ? await (async () => {
          try {
            PORT = devServerPort();
            const ready = await waitForServer(process.env.ELECTRON_START_URL, 30000);
            serverReady = ready;
            return ready;
          } catch { return false; }
        })()
      : await (async () => {
          try {
            const [uiPort, sharePort] = await startupPortsPromise;
            PORT = uiPort;
            SHARE_PORT = sharePort;
            // The cookie and first navigation must use the final selected port.
            if (!launchedHidden) createWindow();
            return await beginUiBootstrap();
          } catch (error) {
            startupFailure = error.message;
            logToFile(`UI startup failed: ${error.message}`);
            return false;
          }
        })();

    if (isDev && !launchedHidden) createWindow();

    if (!started) {
      const message = startupFailure || "The bundled interface server could not be started.";
      if (mainWindow) mainWindow.loadURL(loadingPage(`${message} See launcher.log for details.`));
      else showErrorWindow(message);
      return;
    }

    // The loading window is already visible; navigate exactly once after the
    // authenticated local server has answered its readiness endpoint.
    loadAppIntoWindow(pendingRoute);

    // Non-critical desktop integration happens after the UI is usable.
    setImmediate(() => {
      try { initAutostart(); } catch (e) { logToFile(`Autostart init failed: ${e.message}`); }
      const hasTray = createTray();
      if (launchedHidden && !hasTray && !mainWindow) {
        createWindow();
        loadAppIntoWindow(pendingRoute);
      }
      startShareServer();
    });

    // On macOS, re-create the window when the dock icon is clicked — but ONLY
    // if there truly is no window AND the server is up. This is the guarded
    // version that prevents the infinite-window cascade.
    app.on("activate", () => {
      if (!mainWindow) createWindow();
      if (serverReady) loadAppIntoWindow();
    });
  });

  app.on("window-all-closed", () => {
    // A real quit flows through before-quit so app-owned server subprocesses get
    // one graceful save/shutdown attempt before the local Next process exits.
    app.quit();
  });

  app.on("before-quit", (event) => {
    quitting = true;
    if (quitCleanupFinished) return;
    event.preventDefault();
    if (quitCleanupStarted) return;
    quitCleanupStarted = true;

    const timeout = new Promise((resolve) => setTimeout(() => resolve(false), 14000));
    Promise.race([requestManagedServerShutdown(), timeout]).finally(() => {
      quitCleanupFinished = true;
      if (tray) { try { tray.destroy(); } catch {} tray = null; }
      if (shareProc) { try { shareProc.kill(); } catch {} shareProc = null; }
      if (nextProc) { try { nextProc.kill(); } catch {} nextProc = null; }
      // Re-enter app.quit(); the finished flag lets this second before-quit pass.
      setTimeout(() => app.quit(), 50);
    });
  });
}

// ---- Native IPC: folder picker + file picker for the renderer ----
ipcMain.handle("pick-directory", async () => {
  const res = await dialog.showOpenDialog(mainWindow, { properties: ["openDirectory", "createDirectory"] });
  return res.canceled ? null : res.filePaths[0];
});
ipcMain.handle("pick-zip", async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile"],
    filters: [{ name: "Zip archives", extensions: ["zip"] }],
  });
  return res.canceled ? null : res.filePaths[0];
});
ipcMain.handle("get-theme", () => (nativeTheme.shouldUseDarkColors ? "dark" : "light"));
ipcMain.handle("get-system-locale", () => app.getLocale() || "en");
ipcMain.handle("open-path", (_e, p) => shell.openPath(p));
ipcMain.handle("open-external", (_e, value) => {
  const target = String(value || "");
  const allowed = /^steam:\/\/run\/1374490$/i.test(target)
    || /^ms-windows-store:\/\/launch\?productId=9P402RWR63H4$/i.test(target);
  if (!allowed) throw new Error("External target is not allowed");
  return shell.openExternal(target);
});
function writeShortcutIcon(profile) {
  const data = String(profile?.iconData || "");
  if (!/^data:image\/(png|jpeg|jpg|webp);base64,/i.test(data)) return null;
  try {
    const image = nativeImage.createFromDataURL(data);
    if (image.isEmpty()) return null;
    const dir = path.join(dataDir(), "profile-shortcut-icons");
    fs.mkdirSync(dir, { recursive: true });
    const safeId = String(profile?.id || "profile").replace(/[^a-zA-Z0-9_.-]/g, "_");
    const pngPath = path.join(dir, `${safeId}.png`);
    fs.writeFileSync(pngPath, image.resize({ width: 128, height: 128, quality: "best" }).toPNG());

    if (process.platform !== "win32") return pngPath;

    // Explorer shortcut icons are most reliable as real ICO files. Convert the
    // synced profile image out-of-process so no image codec work can destabilize
    // the Electron UI process.
    const icoPath = path.join(dir, `${safeId}.ico`);
    const script = [
      "param([string]$src,[string]$dst)",
      "Add-Type -AssemblyName System.Drawing",
      "$bmp = New-Object System.Drawing.Bitmap($src)",
      "$icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())",
      "$fs = [System.IO.File]::Create($dst)",
      "$icon.Save($fs)",
      "$fs.Close(); $icon.Dispose(); $bmp.Dispose()",
    ].join("; ");
    const ps = spawnSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script, pngPath, icoPath], {
      windowsHide: true,
      timeout: 10000,
      stdio: "ignore",
    });
    if (ps.status === 0 && fs.existsSync(icoPath)) return icoPath;
    logToFile("Profile shortcut ICO conversion failed; using application icon fallback.");
    return null;
  } catch (e) {
    logToFile(`Profile shortcut icon write failed: ${e.message}`);
    return null;
  }
}

ipcMain.handle("create-profile-shortcut", (_e, profile) => {
  const id = String(profile?.id || "").trim();
  const role = profile?.role === "server" ? "server" : "player";
  if (!id) throw new Error("Profile id is required");
  const safeName = String(profile?.name || "Dragonwilds World").replace(/[<>:"/\\|?*]/g, "_").trim();
  const label = role === "server" ? `${safeName} - Server` : safeName;
  const args = `--profile=${id} --role=${role}${role === "player" ? " --autoplay" : ""}`;
  const profileIcon = writeShortcutIcon(profile);
  if (process.platform === "win32") {
    const shortcutPath = path.join(app.getPath("desktop"), `${label}.lnk`);
    const ok = shell.writeShortcutLink(shortcutPath, "create", {
      target: process.execPath,
      args,
      cwd: path.dirname(process.execPath),
      description: role === "player"
        ? `Authenticate, sync, confirm and launch ${safeName}`
        : `Open ${safeName} in RSDW Sync server mode`,
      icon: profileIcon || process.execPath,
      iconIndex: 0,
    });
    if (!ok) throw new Error("Windows could not create the desktop shortcut");
    return shortcutPath;
  }
  const shortcutPath = path.join(app.getPath("desktop"), `${label}.desktop`);
  const iconLine = profileIcon ? `Icon=${profileIcon}\n` : "";
  fs.writeFileSync(shortcutPath, `[Desktop Entry]\nType=Application\nName=${label}\nExec="${process.execPath}" ${args}\n${iconLine}Terminal=false\n`, { mode: 0o755 });
  return shortcutPath;
});
ipcMain.handle("get-auto-launch", () => {
  const v = readAutostartPref();
  return v === null ? false : v;
});
ipcMain.handle("set-auto-launch", (_e, enabled) => {
  writeAutostartPref(!!enabled);
  applyAutostart(!!enabled);
  return !!enabled;
});
ipcMain.handle("get-close-to-tray", () => readCloseToTrayPref());
ipcMain.handle("set-close-to-tray", (_e, enabled) => {
  writeCloseToTrayPref(!!enabled);
  return !!enabled;
});

// Remote Access — same-network (LAN) bind toggle. The renderer writes the choice through
// the API (which persists it + the marker file); this applies it by restarting the server
// on the new host. Returns whether the server came back up.
ipcMain.handle("remote-get-lanbind", () => sharingEnabled());
ipcMain.handle("remote-set-lanbind", async (_e, enabled) => {
  const host = enabled ? "0.0.0.0" : "127.0.0.1";
  try { fs.writeFileSync(path.join(dataDir(), "remote-bind.json"), JSON.stringify({ host }), "utf8"); } catch {}
  if (enabled) startShareServer();
  else await stopShareServer();
  return { ok: true, host, port: SHARE_PORT };
});
