const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { EventEmitter } = require("events");
const { createStartupGate, startupHtml } = require("../electron/startup-screen");
const runtime = require("../electron/stable-runtime");

const root = path.resolve(__dirname, "..");

async function checkGate() {
  const states = [];
  let navigations = 0, finish;
  const gate = createStartupGate({ onStatus: (state) => states.push(state), onEnter: () => { navigations++; return new Promise((resolve) => { finish = resolve; }); } });
  assert.equal(await gate.enter(), false, "Enter must wait for the interface to be ready");
  gate.ready();
  assert.equal(navigations, 0, "readiness must never auto-enter");
  const entering = gate.enter();
  assert.equal(await gate.enter(), false, "duplicate Enter events must not navigate twice");
  finish(true);
  assert.equal(await entering, true);
  assert.equal(navigations, 1);
  gate.reset(true);
  assert.equal(gate.snapshot().entered, false, "a new manual window should get its own gate");
  gate.fail("startup failure");
  assert.equal(await gate.enter(), false);
  assert.equal(gate.snapshot().error, "startup failure");
  assert(states.every((state, index) => !index || state.revision > states[index - 1].revision));
  const retryGate = createStartupGate({ onEnter: async () => false });
  retryGate.ready();
  assert.equal(await retryGate.enter(), false);
  assert.equal(retryGate.snapshot().entered, false, "failed navigation must allow retry");
}

async function checkLocalScreen() {
  const html = startupHtml(path.join(root, "public"), { message: '<test & "offline">' });
  assert(html.includes("data:image/png;base64,") && html.includes("data:image/webp;base64,"));
  assert(!/<(?:link|img)[^>]+(?:href|src)=["']https?:/i.test(html), "the native splash must not request network assets");
  assert(html.includes("&lt;test &amp; &quot;offline&quot;&gt;"), "status messages must be escaped");
  assert(/<button id="enter" disabled>Enter<\/button>/.test(html), "Enter must exist even while startup is pending");
  assert(!/button\{[^}]*opacity:0/.test(html), "Enter must remain visible without animations");
  assert(html.includes("prefers-reduced-motion:reduce"));
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const elements = Object.fromEntries(["enter", "status", "error"].map((id) => [id, { disabled: true, textContent: "", addEventListener(name, fn) { this[name] = fn; } }]));
  const keys = {};
  let listener, clicks = 0;
  const desktop = {
    getStartupState: async () => ({ ready: false, entered: false, message: "Preparing…", revision: 1 }),
    onStartupStatus: (fn) => { listener = fn; return () => {}; },
    enterStartup: async () => { clicks++; },
  };
  vm.runInNewContext(script, { document: { getElementById: (id) => elements[id] }, window: { desktop, addEventListener: (name, fn) => { keys[name] = fn; } } });
  await Promise.resolve();
  assert.equal(elements.enter.disabled, true);
  await elements.enter.click();
  assert.equal(clicks, 0);
  listener({ ready: true, entered: false, message: "Ready", revision: 2 });
  listener({ ready: false, entered: false, message: "Stale snapshot", revision: 1 });
  assert.equal(elements.enter.disabled, false, "a stale snapshot must not disable a ready button");
  keys.keydown({ key: "Enter", repeat: false, preventDefault() {} });
  keys.keydown({ key: "Enter", repeat: false, preventDefault() {} });
  await Promise.resolve();
  assert.equal(clicks, 1);
  assert.equal(elements.enter.disabled, true);
}

async function checkElectronNavigation() {
  const folder = fs.mkdtempSync(path.join(root, ".rsdw-startup-test-"));
  try {
    const app = new EventEmitter();
    let onReady;
    Object.assign(app, { requestSingleInstanceLock: () => true, whenReady: () => ({ then: (fn) => { onReady = fn; } }), getPath: () => folder, setAppUserModelId() {}, quit() {} });
    const handlers = new Map(), windows = [];
    class Window extends EventEmitter {
      constructor(options) {
        super(); this.options = options; this.loads = []; this.url = "";
        this.webContents = new EventEmitter();
        Object.assign(this.webContents, { session: { cookies: { set: async () => {} } }, send() {}, getURL: () => this.url, setWindowOpenHandler() {} });
        windows.push(this);
      }
      async loadURL(url) { this.loads.push(url); this.url = url; }
      setMenuBarVisibility() {} isDestroyed() { return false; } isMinimized() { return false; } show() {} focus() {}
    }
    const electron = { app, BrowserWindow: Window, ipcMain: { handle: (name, fn) => handlers.set(name, fn) }, Menu: { setApplicationMenu() {} } };
    const fakeHttp = {
      get(_url, callback) {
        const request = new EventEmitter(); request.setTimeout = () => {}; request.destroy = () => {};
        queueMicrotask(() => { const response = new EventEmitter(); response.statusCode = 200; callback(response); response.emit("data", '{}'); response.emit("end"); });
        return request;
      },
    };
    const main = fs.readFileSync(path.join(root, "electron/main.js"), "utf8");
    const localRequire = (id) => id === "electron" ? electron : id === "http" ? fakeHttp : require(id.startsWith(".") ? path.join(root, "electron", id) : id);
    vm.runInNewContext(main, {
      require: localRequire, __dirname: path.join(root, "electron"),
      process: { env: { NODE_ENV: "development", ELECTRON_START_URL: "http://127.0.0.1:4317" }, argv: ["electron"], platform: process.platform },
      URL, Buffer, setImmediate: () => {}, setTimeout: () => ({ unref() {} }), setInterval: () => ({ unref() {} }), clearTimeout() {}, clearInterval() {},
    });
    await onReady();
    assert.equal(windows.length, 1);
    const win = windows[0], event = { sender: win.webContents };
    assert.equal(win.loads.length, 1, "the app must remain on its local splash after readiness");
    assert(win.loads[0].startsWith("data:text/html"));
    assert.equal(handlers.get("startup-state")(event).ready, true);
    assert.equal(await handlers.get("startup-enter")(event), true);
    assert.equal(win.loads[1], "http://127.0.0.1:4317");
    assert.equal(await handlers.get("startup-enter")(event), false);
    app.emit("second-instance", null, ["electron"]);
    assert.equal(win.loads.length, 2, "revealing the existing window must not reload its app or replay splash");
    assert.throws(() => handlers.get("startup-enter")({ sender: {} }), /main window/);
  } finally { fs.rmSync(folder, { recursive: true, force: true }); }
}

async function checkWorkerCache() {
  const folder = fs.mkdtempSync(path.join(root, ".rsdw-startup-worker-test-"));
  try {
    const source = path.join(folder, "source"), data = path.join(folder, "data");
    for (const relative of runtime.REQUIRED) {
      const file = path.join(source, relative);
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, relative.endsWith("BUILD_ID") ? "build-one" : "module.exports = {};");
    }
    fs.writeFileSync(path.join(source, "build-info.json"), JSON.stringify({ version: "test", commit: "same-commit" }));
    const failedData = path.join(folder, "failed-copy-data");
    const originalLink = fs.linkSync, originalCopy = fs.copyFileSync;
    let copied = 0;
    fs.linkSync = () => { throw new Error("test forces copy fallback"); };
    fs.copyFileSync = (from, to) => {
      if (++copied === 2) throw new Error("simulated interrupted staging");
      return originalCopy(from, to);
    };
    try { assert.throws(() => runtime.materializeRuntime(source, failedData), /interrupted staging/); }
    finally { fs.linkSync = originalLink; fs.copyFileSync = originalCopy; }
    assert(!fs.existsSync(path.join(failedData, "interface-runtime", runtime.runtimeIdentity(source))), "failed staging must never become a reusable cache");
    const abandoned = path.join(data, "interface-runtime", `${runtime.runtimeIdentity(source)}.staging-abandoned`);
    fs.mkdirSync(abandoned, { recursive: true });
    fs.writeFileSync(path.join(abandoned, "server.js"), "partial copy");
    let ticks = 0;
    const timer = setInterval(() => ticks++, 1);
    let first;
    try { first = await runtime.materializeRuntimeAsync(source, data); }
    finally { clearInterval(timer); }
    assert(ticks > 0, "first-run staging must leave the caller's event loop responsive");
    assert(!first.includes(".staging-"), "only a fully published runtime may start the interface");
    assert(!fs.existsSync(abandoned), "a verified cold launch should clear abandoned cache staging");
    assert.equal(await runtime.materializeRuntimeAsync(source, data), first, "a warm launch must reuse its verified cache");
    fs.writeFileSync(path.join(source, ".next", "BUILD_ID"), "build-two");
    const second = await runtime.materializeRuntimeAsync(source, data);
    assert.notEqual(first, second, "a new build at the same commit must get a fresh runtime");
    assert.equal(fs.readFileSync(path.join(second, ".next", "BUILD_ID"), "utf8"), "build-two");
    await assert.rejects(runtime.materializeRuntimeAsync(path.join(folder, "missing"), data), /runtime is incomplete/);
  } finally { fs.rmSync(folder, { recursive: true, force: true }); }
}

async function checkPackagedWorker() {
  if (process.platform !== "win32") return;
  const { createPackage } = require("@electron/asar");
  const { spawnSync } = require("child_process");
  const folder = fs.mkdtempSync(path.join(root, ".rsdw-startup-asar-test-"));
  try {
    const bundle = path.join(folder, "bundle"), archive = path.join(folder, "app.asar");
    fs.mkdirSync(bundle);
    for (const file of ["stable-runtime.js", "runtime-worker.js"]) fs.copyFileSync(path.join(root, "electron", file), path.join(bundle, file));
    const archiveStream = await createPackage(bundle, archive);
    // This installed ASAR version returns its write stream before final flush.
    if (archiveStream?.on) await require("stream/promises").finished(archiveStream);
    const source = path.join(folder, "source");
    for (const relative of runtime.REQUIRED) {
      const file = path.join(source, relative);
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, relative.endsWith("BUILD_ID") ? "asar-test" : "module.exports = {};");
    }
    const runner = path.join(folder, "runner.cjs");
    fs.writeFileSync(runner, `require(${JSON.stringify(path.join(archive, "stable-runtime.js"))}).materializeRuntimeAsync(${JSON.stringify(source)}, ${JSON.stringify(path.join(folder, "data"))}).then(() => console.log('Packaged worker: OK')).catch(error => { console.error(error); process.exitCode = 1; });`);
    const checked = spawnSync(require("electron"), [runner], { env: { ...process.env, ELECTRON_RUN_AS_NODE: "1" }, windowsHide: true, encoding: "utf8", timeout: 15000 });
    assert.equal(checked.status, 0, `Electron ASAR worker failed: ${checked.error?.message || checked.stderr}`);
    assert(checked.stdout.includes("Packaged worker: OK"));
  } finally { fs.rmSync(folder, { recursive: true, force: true }); }
}

(async () => {
  await checkGate(); await checkLocalScreen(); await checkElectronNavigation(); await checkWorkerCache(); await checkPackagedWorker();
  const layout = fs.readFileSync(path.join(root, "app/layout.js"), "utf8");
  assert(!layout.includes("fonts.googleapis.com"), "offline startup must not block on remote font stylesheets");
  assert(layout.includes("rsdwNativeSplash"), "native startup must suppress the second splash before first app paint");
  console.log("Offline splash, visible Enter, startup navigation guards and background runtime staging: OK");
})().catch((error) => { console.error(error); process.exitCode = 1; });
