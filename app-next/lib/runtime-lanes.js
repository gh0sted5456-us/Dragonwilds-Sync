const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const dbm = require("./db");
const { P } = require("./paths");
const files = require("./runtime-files");
const cleaner = require("./runtime-clean");
const operations = globalThis.__RSDW_RUNTIME_LANES ||= new Set();
const PLATFORMS = ["server", "steam", "gamepass"];
const label = (platform) => platform === "server" ? "Dedicated Server" : platform === "gamepass" ? "PC Game Pass" : "Steam";

function configuration(platform) {
  if (!PLATFORMS.includes(platform)) throw new Error("Choose the Server, Steam, or PC Game Pass lane.");
  const install = dbm.getSetting(platform === "server" ? "applicationSetup:serverDir" : "clientInstall:" + platform, null);
  if (!install) return null;
  const installDir = path.resolve(install);
  const gameRoot = fs.existsSync(path.join(installDir, "RSDragonwilds")) ? path.join(installDir, "RSDragonwilds") : installDir;
  const location = crypto.createHash("sha256").update(installDir.toLowerCase()).digest("hex").slice(0, 24);
  return { platform, installDir, gameRoot, root: path.join(P.data(), "runtime-lanes", platform, location) };
}
function componentFor(platform) { return "ue4ss-" + platform; }
function isBusy(platform) { const config = configuration(platform); return !!config && operations.has(config.installDir.toLowerCase()); }
function packageRoot(platform, component) {
  const config = configuration(platform);
  if (!config) return null;
  if (![componentFor(platform), "runeschema"].includes(component)) throw new Error("Runtime component does not match this installation lane.");
  return path.join(config.root, component);
}
function status(platform) {
  const config = configuration(platform);
  return { platform, label: label(platform), installDir: config?.installDir || null, packages: [componentFor(platform), "runeschema"].map((component) => {
    const root = config && packageRoot(platform, component), meta = root && files.readPackage(root);
    return { component, installed: !!meta && !meta.cleaned, cleaned: !!meta?.cleaned, archive: meta?.archive || null, files: meta?.files?.length || 0, sha256: meta?.archiveSha256 || null, installedAt: meta?.installedAt || null, manifestPath: meta ? path.join(root, "manifest.json") : null };
  }) };
}
function assertStopped(config, options = {}) {
  if (configuration(config.platform)?.installDir !== config.installDir) throw new Error("The installation lane changed. Retry with its new path.");
  const bin = config.platform === "gamepass" ? "WinGDK" : "Win64";
  if (!fs.existsSync(path.join(config.gameRoot, "Binaries", bin))) throw new Error("This installation does not have the expected " + bin + " loader directory.");
  if (require("./jobs").listJobs().some((job) => job.status === "running" && ["sync", "update", "install", "setup"].includes(job.type))) throw new Error("Wait for game installation, updates, or synchronization to finish before updating loaders.");
  if (config.platform === "server") require("./server-process-guard").assertNoConflictingServer({ install_dir: config.installDir }, { template: config.installDir, ...(options.processes ? { processes: options.processes } : {}) });
  else require("./client-isolation").assertGameStopped(config.installDir, options.processes);
}
function deployment(config, onProgress, options = {}) {
  const desired = [], excluded = new Set(options.excludeComponents || []);
  for (const component of [componentFor(config.platform), "runeschema"]) {
    if (excluded.has(component)) continue;
    const root = packageRoot(config.platform, component), meta = files.readPackage(root);
    for (const file of meta?.files || []) {
      const relative = config.platform === "gamepass" && component === "runeschema" ? file.relative.replace(/^Binaries\/Win64\//i, "Binaries/WinGDK/") : file.relative;
      desired.push({ ...file, relative, component, source: files.targetFile(path.join(root, "files"), file.relative) });
    }
  }
  const ledgerFile = path.join(config.root, "installed.json");
  const previous = fs.existsSync(ledgerFile) ? JSON.parse(fs.readFileSync(ledgerFile, "utf8")).files : [];
  return files.applyFiles({ gameRoot: config.gameRoot, desired, previous: previous.filter((file) => !excluded.has(file.component)).map((file) => file.relative), ledgerFile, assertStopped: () => assertStopped(config, options), onProgress });
}
async function install(platform, component, zipPath, onProgress = () => {}, options = {}) {
  const config = configuration(platform);
  if (!config) throw new Error("Link this installation in Application Setup before adding a loader ZIP.");
  const permanent = packageRoot(platform, component), operationKey = config.installDir.toLowerCase();
  const pendingClean = cleaner.readState(cleanupSpec(platform, component, options).scope);
  if (["pending", "restoring", "needs-recovery"].includes(pendingClean?.state)) throw new Error("Restore the interrupted runtime cleanup before installing a ZIP.");
  if (operations.has(operationKey)) throw new Error("A loader update is already running for this installation.");
  assertStopped(config, options); operations.add(operationKey);
  let candidate;
  try {
    const bootstrap = component === "ue4ss-server" ? files.targetFile(config.gameRoot, "Binaries/Win64/version.dll") : null;
    const cachedBootstrap = component === "ue4ss-server" ? path.join(permanent, "files", "Binaries", "Win64", "version.dll") : null;
    const serverBootstrap = bootstrap && fs.existsSync(bootstrap) ? bootstrap : cachedBootstrap && fs.existsSync(cachedBootstrap) ? cachedBootstrap : null;
    candidate = await files.stagePackage(component, zipPath, config.root, onProgress, { serverBootstrap });
    assertStopped(config, options);
    let result;
    await files.promotePackage(candidate, permanent, () => { result = deployment(config, onProgress, options); });
    onProgress({ phase: "finalizing", percent: 100, message: "Loader update complete", line: "Retired " + result.removed + " owned files. Mod lists and user mods were preserved. Server profiles use changed defaults on their next start; no restart was requested." });
    globalThis.__DWS_COMPONENT_UPDATES = null;
    return { ...status(platform), deployment: result };
  } finally {
    if (candidate && fs.existsSync(candidate)) fs.rmSync(candidate, { recursive: true, force: true });
    operations.delete(operationKey);
  }
}
function ownedTargets(install, platform, hash = files.hashFile) {
  if (!["steam", "gamepass"].includes(platform)) return new Set();
  const config = configuration(platform), owned = new Set();
  if (!config || path.resolve(install).toLowerCase() !== config.installDir.toLowerCase()) return owned;
  const ledgerFile = path.join(config.root, "installed.json");
  if (!fs.existsSync(ledgerFile)) return owned;
  const ledger = JSON.parse(fs.readFileSync(ledgerFile, "utf8"));
  for (const file of ledger.files || []) {
    const target = files.targetFile(config.gameRoot, file.relative);
    if (fs.existsSync(target) && hash(target) === file.sha256) owned.add("RSDragonwilds/" + file.relative);
  }
  for (const relative of ledger.defaults || []) if (files.protectedList(relative) && fs.existsSync(files.targetFile(config.gameRoot, relative))) owned.add("RSDragonwilds/" + relative);
  return owned;
}

function cleanupSpec(platform, component, options = {}) {
  const config = configuration(platform), root = packageRoot(platform, component);
  if (!config) throw new Error("Link an installation before cleaning its runtime.");
  return {
    scope: config.root + ":" + component, component,
    targets: [{ id: "installation", gameRoot: config.gameRoot, platform }, { id: "package", gameRoot: path.join(root, "files"), platform: component === "runeschema" ? "steam" : platform }],
    metadata: [path.join(root, "manifest.json"), path.join(config.root, "installed.json")],
    assertStopped: () => assertStopped(config, options),
  };
}
function cleanupPreview(platform, component) { return cleaner.preview(cleanupSpec(platform, component)); }
async function clean(platform, component, fingerprint, onProgress = () => {}, options = {}) {
  const config = configuration(platform), spec = cleanupSpec(platform, component, options), operationKey = config.installDir.toLowerCase();
  if (operations.has(operationKey)) throw new Error("A loader operation is already running for this installation.");
  operations.add(operationKey);
  try {
    const ledger = fs.existsSync(spec.metadata[1]) ? JSON.parse(fs.readFileSync(spec.metadata[1], "utf8")) : { files: [], defaults: [] };
    const changes = [
      { file: spec.metadata[0], value: { schema: "RSDWSync.RuntimePackage.v2", component, cleaned: true, cleanedAt: Date.now(), files: [] } },
      { file: spec.metadata[1], value: { ...ledger, files: (ledger.files || []).filter((file) => file.component !== component) } },
    ];
    const result = await cleaner.clean(spec, fingerprint, changes, onProgress);
    globalThis.__DWS_COMPONENT_UPDATES = null;
    return result;
  } finally { operations.delete(operationKey); }
}
async function restoreClean(platform, component, id, onProgress = () => {}, options = {}) {
  const config = configuration(platform), spec = cleanupSpec(platform, component, options), operationKey = config.installDir.toLowerCase();
  if (operations.has(operationKey)) throw new Error("A loader operation is already running for this installation.");
  operations.add(operationKey);
  try { return await cleaner.restore(spec, id, onProgress); } finally { operations.delete(operationKey); }
}

module.exports = { configuration, packageRoot, componentFor, status, install, ownedTargets, cleanupPreview, clean, restoreClean, isBusy };
