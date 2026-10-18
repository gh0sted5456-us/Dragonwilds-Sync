const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const dbm = require("./db");
const { P } = require("./paths");
const runtimeFiles = require("./runtime-files");
const cleaner = require("./runtime-clean");
const operations = globalThis.__RSDW_RUNTIME_OPERATIONS ||= new Set();

function ownRoot(worldId, component) {
  if (!/^[a-zA-Z0-9_-]+$/.test(String(worldId))) throw new Error("Invalid World runtime folder.");
  if (!dbm.getWorld(worldId) || !runtimeFiles.COMPONENTS.has(component)) throw new Error("Unknown World or runtime component.");
  return path.join(P.data(), "runtime-packages", String(worldId), component);
}
function packageRoot(worldId, component) {
  const own = ownRoot(worldId, component);
  if (runtimeFiles.readPackage(own)) return own;
  // Defaults never force an override of a World's explicitly selected ZIP.
  if (["ue4ss-server", "runeschema"].includes(component)) return require("./runtime-lanes").packageRoot("server", component) || own;
  return own;
}
function readManifest(worldId, component) { return runtimeFiles.readPackage(packageRoot(worldId, component)); }
function filesRoot(worldId, component) { return path.join(packageRoot(worldId, component), "files"); }
function isInstalling(worldId) { return operations.has(String(worldId)); }
function serverGameRoot(installDir) {
  const nested = path.join(installDir, "RSDragonwilds");
  return fs.existsSync(nested) ? nested : installDir;
}
function assertStopped(world) {
  const sup = require("./supervisor");
  if (sup.isRunning(world.world_id) || sup.pidAlive(dbm.getWorld(world.world_id)?.process_id)) throw new Error("Stop the World before replacing its UE4SS or RuneSchema runtime.");
}

async function install(worldId, component, zipPath, onProgress = () => {}) {
  const kind = String(component || "").trim().toLowerCase();
  const permanent = ownRoot(worldId, kind), world = dbm.getWorld(worldId);
  const pendingClean = cleaner.readState(cleanupSpec(worldId, kind).scope);
  if (["pending", "restoring", "needs-recovery"].includes(pendingClean?.state)) throw new Error("Restore the interrupted runtime cleanup before installing a ZIP.");
  if (isInstalling(worldId)) throw new Error("Another loader update is already running for this World.");
  assertStopped(world);
  operations.add(String(worldId));
  let candidate;
  try {
    const bootstrap = kind === "ue4ss-server" ? runtimeFiles.targetFile(serverGameRoot(world.install_dir), "Binaries/Win64/version.dll") : null;
    const cachedBootstrap = kind === "ue4ss-server" ? runtimeFiles.targetFile(filesRoot(worldId, kind), "Binaries/Win64/version.dll") : null;
    const coreRoot = kind === "ue4ss-server" ? require("./runtime-lanes").configuration("server")?.gameRoot : null;
    const coreBootstrap = coreRoot && runtimeFiles.targetFile(coreRoot, "Binaries/Win64/version.dll");
    const serverBootstrap = [bootstrap, cachedBootstrap, coreBootstrap].find((file) => file && fs.existsSync(file)) || null;
    candidate = await runtimeFiles.stagePackage(kind, zipPath, path.dirname(permanent), onProgress, { serverBootstrap });
    assertStopped(world);
    require("./server-process-guard").assertNoConflictingServer(world);
    await runtimeFiles.promotePackage(candidate, permanent, () => {
      if (["ue4ss-server", "runeschema"].includes(kind)) materializeHost(worldId, onProgress);
    });
    onProgress({ phase: "finalizing", percent: 100, message: "Runtime updated", line: "Manifest saved. Retired owned files removed; mod lists and unrelated mods preserved." });
    return status(worldId);
  } finally {
    if (candidate && fs.existsSync(candidate)) fs.rmSync(candidate, { recursive: true, force: true });
    operations.delete(String(worldId));
  }
}

function hostLedgerKey(world) {
  const shared = String(dbm.getSetting("applicationSetup:serverDir", "") || "");
  return shared && path.resolve(world.install_dir).toLowerCase() === path.resolve(shared).toLowerCase()
    ? "applicationSetup:activeServerRuntimeFiles" : "serverRuntimeFiles:" + world.world_id;
}
function materializeHost(worldId, onProgress = () => {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const gameRoot = serverGameRoot(world.install_dir), desired = [], suspended = new Set();
  for (const component of ["ue4ss-server", "runeschema"]) {
    const meta = readManifest(worldId, component);
    const inherited = packageRoot(worldId, component) !== ownRoot(worldId, component);
    const cleanup = cleaner.readState(cleanupSpec(worldId, component).scope);
    if (["pending", "restoring", "needs-recovery"].includes(cleanup?.state)) throw new Error("Restore this World's interrupted runtime cleanup before starting.");
    if (inherited && require("./runtime-lanes").isBusy("server")) throw new Error("Wait for the shared Server loader operation to finish before starting.");
    if (meta?.cleaned) {
      if (!inherited) throw new Error("This World's " + component + " was intentionally cleaned. Install its ZIP before starting.");
      const required = cleaner.loaderRelative(component, "server") + (component === "runeschema" ? "/dlls/main.dll" : "/UE4SS.dll");
      if (!fs.existsSync(runtimeFiles.targetFile(gameRoot, required))) throw new Error("The shared " + component + " default was cleaned and this profile has no runtime to keep. Install its ZIP before starting.");
      suspended.add(component);
    }
    for (const file of meta?.files || []) desired.push({ ...file, component, source: runtimeFiles.targetFile(filesRoot(worldId, component), file.relative) });
  }
  const { ledgerFile, previous } = hostLedger(world);
  const records = ledgerRecords(previous), retained = records.filter((file) => suspended.has(file.component));
  const result = runtimeFiles.applyFiles({ gameRoot, desired, previous: records.map((file) => file.relative), retained, ledgerFile, assertStopped: () => assertStopped(world), onProgress });
  return { worldId, files: desired.length, ...result };
}
function packageStatus(worldId, component) {
  const meta = readManifest(worldId, component);
  if (!meta) return { component, installed: false, files: 0, clientFiles: 0 };
  return { component, installed: !meta.cleaned, cleaned: !!meta.cleaned, inherited: packageRoot(worldId, component) !== ownRoot(worldId, component), archive: meta.archive, sha256: meta.archiveSha256, installedAt: meta.installedAt, files: (meta.files || []).length, clientFiles: (meta.files || []).filter((file) => file.clientEligible && !runtimeFiles.protectedList(file.relative)).length };
}
function status(worldId) {
  return { ue4ssServer: packageStatus(worldId, "ue4ss-server"), ue4ssSteam: packageStatus(worldId, "ue4ss-steam"), ue4ssGamepass: packageStatus(worldId, "ue4ss-gamepass"), runeschema: packageStatus(worldId, "runeschema") };
}
function syncFiles(worldId, platform = "steam") {
  const selectedPlatform = platform === "gamepass" ? "gamepass" : "steam", out = [];
  for (const component of [selectedPlatform === "gamepass" ? "ue4ss-gamepass" : "ue4ss-steam", "runeschema"]) {
    for (const file of readManifest(worldId, component)?.files || []) {
      if (!file.clientEligible || runtimeFiles.protectedList(file.relative)) continue;
      const source = runtimeFiles.targetFile(filesRoot(worldId, component), file.relative);
      if (!fs.existsSync(source)) throw new Error("Managed runtime file is missing; reinstall its ZIP: " + file.relative);
      let relative = file.relative.replace(/\\/g, "/");
      if (selectedPlatform === "gamepass" && component === "runeschema") relative = relative.replace(/^Binaries\/Win64\//i, "Binaries/WinGDK/");
      out.push({ component, target: "RSDragonwilds/" + relative, size: file.size, sha256: file.sha256, source });
    }
  }
  return out;
}
function syncUnits(worldId, platform = "steam") {
  const grouped = new Map();
  for (const file of syncFiles(worldId, platform)) {
    if (!grouped.has(file.component)) grouped.set(file.component, []);
    grouped.get(file.component).push(file);
  }
  return [...grouped.entries()].map(([component, files]) => {
    const identity = crypto.createHash("sha256");
    for (const file of files) identity.update(file.target + "\0" + file.size + "\0" + file.sha256 + "\n");
    return { key: "runtime:" + component, name: component.startsWith("ue4ss-") ? "UE4SS Runtime · " + (component === "ue4ss-gamepass" ? "PC Game Pass" : "Steam") : "RuneSchema Runtime", type: "runtime", runtimeComponent: component, contentHash: identity.digest("hex"), fileCount: files.length, bytes: files.reduce((sum, file) => sum + file.size, 0), files };
  });
}
function resolveSyncFile(worldId, target, platform = "steam") { return syncFiles(worldId, platform).find((file) => file.target === target) || null; }

function hostLedger(world) {
  const gameRoot = serverGameRoot(world.install_dir);
  const location = crypto.createHash("sha256").update(path.resolve(gameRoot).toLowerCase()).digest("hex").slice(0, 24);
  const ledgerFile = path.join(P.data(), "runtime-deployments", "host-" + location + ".json");
  const previous = fs.existsSync(ledgerFile) ? JSON.parse(fs.readFileSync(ledgerFile, "utf8")) : dbm.getSetting(hostLedgerKey(world), { files: [] });
  return { ledgerFile, previous };
}
function ledgerRecords(ledger) {
  return (ledger?.files || []).map((file) => typeof file === "string" ? { relative: file, component: /\/ue4ss\/mods\/runeschema\//i.test(file) ? "runeschema" : "ue4ss-server" } : file);
}
function cleanupSpec(worldId, component) {
  const root = ownRoot(worldId, component), world = dbm.getWorld(worldId);
  const host = ["ue4ss-server", "runeschema"].includes(component);
  return {
    scope: root + ":clean", component,
    targets: [...(host ? [{ id: "installation", gameRoot: serverGameRoot(world.install_dir), platform: "server" }] : []), { id: "package", gameRoot: path.join(root, "files"), platform: component === "ue4ss-gamepass" ? "gamepass" : "steam" }],
    metadata: [path.join(root, "manifest.json"), ...(host ? [hostLedger(world).ledgerFile] : [])],
    assertStopped: () => {
      assertStopped(world);
      if (require("./jobs").listJobs().some((job) => job.status === "running" && ["sync", "update", "install", "setup"].includes(job.type))) throw new Error("Wait for file operations to finish before cleaning a runtime.");
      require("./server-process-guard").assertNoConflictingServer(world);
    },
  };
}
function assertPrivateCleanup(worldId, component) {
  if (!["ue4ss-server", "runeschema"].includes(component)) return;
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const game = path.resolve(serverGameRoot(world.install_dir)).toLowerCase();
  const core = require("./runtime-lanes").configuration("server");
  if (core && game === path.resolve(core.gameRoot).toLowerCase()) throw new Error("This World uses the shared Core. Clean its loader in Application Setup, or migrate this World to a private fork first.");
  if (dbm.listWorlds().some((other) => other.world_id !== worldId && other.install_dir && path.resolve(serverGameRoot(other.install_dir)).toLowerCase() === game)) throw new Error("Other Worlds share this installation. Migrate to private forks before cleaning a single profile.");
}
function cleanupPreview(worldId, component) { assertPrivateCleanup(worldId, component); return cleaner.preview(cleanupSpec(worldId, component)); }
async function clean(worldId, component, fingerprint, onProgress = () => {}) {
  assertPrivateCleanup(worldId, component);
  const spec = cleanupSpec(worldId, component);
  if (isInstalling(worldId)) throw new Error("Another loader operation is already running for this World.");
  operations.add(String(worldId));
  try {
    const changes = [{ file: spec.metadata[0], value: { schema: "RSDWSync.RuntimePackage.v2", component, cleaned: true, cleanedAt: Date.now(), files: [] } }];
    if (spec.metadata[1]) {
      const { previous } = hostLedger(dbm.getWorld(worldId));
      changes.push({ file: spec.metadata[1], value: { ...previous, files: ledgerRecords(previous).filter((file) => file.component !== component) } });
    }
    return await cleaner.clean(spec, fingerprint, changes, onProgress);
  } finally { operations.delete(String(worldId)); }
}
async function restoreClean(worldId, component, id, onProgress = () => {}) {
  assertPrivateCleanup(worldId, component);
  const spec = cleanupSpec(worldId, component);
  if (isInstalling(worldId)) throw new Error("Another loader operation is already running for this World.");
  operations.add(String(worldId));
  try { return await cleaner.restore(spec, id, onProgress); } finally { operations.delete(String(worldId)); }
}

module.exports = { install, status, syncFiles, syncUnits, resolveSyncFile, materializeHost, isInstalling, cleanupPreview, clean, restoreClean };
