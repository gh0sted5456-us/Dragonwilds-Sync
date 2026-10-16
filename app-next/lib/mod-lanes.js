const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const dbm = require("./db");
const steamlib = require("./steamlibrary");
const loaderMods = require("./loader-mods");
const forks = require("./server-forks");
const { trashPath } = require("./trash");

const LANES = ["server", "required", "steam", "gamepass"];
const EDITABLE_EXTENSIONS = new Set([".json", ".jsonc", ".lua"]);
const MAX_EDITABLE_BYTES = 2 * 1024 * 1024;
const selectionKey = (worldId) => `modLaneSelection:${worldId}`;
const ledgerKey = (worldId) => `modLaneLedger:${worldId}`;
const requiredSourceKey = (worldId) => `modRequiredSource:${worldId}`;
const pakInstallModeKey = (worldId) => `pakInstallMode:${worldId}`;

function readPakInstallMode(worldId) {
  return dbm.getSetting(pakInstallModeKey(worldId), "classic") === "runeschema" ? "runeschema" : "classic";
}

function readList(key) {
  const value = dbm.getSetting(key, []);
  if (Array.isArray(value)) return value.map(String);
  try { const parsed = JSON.parse(value || "[]"); return Array.isArray(parsed) ? parsed.map(String) : []; }
  catch { return []; }
}

function roots(worldId) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  return {
    server: world.install_dir || null,
    required: dbm.getSetting(requiredSourceKey(worldId), null),
    steam: dbm.getSetting("clientInstall:steam", null),
    gamepass: dbm.getSetting("clientInstall:gamepass", null),
  };
}

function normalizeSelections(value) {
  let source = value;
  if (typeof source === "string") {
    try { source = JSON.parse(source); } catch { source = []; }
  }
  if (!Array.isArray(source)) source = [];
  const unique = new Map();
  for (const item of source) {
    const key = String(typeof item === "string" ? item : item?.key || "").trim();
    if (!key) continue;
    const legacyRequired = typeof item === "string" ? true : item.clientRequired !== false;
    const requestedScope = typeof item === "object" ? String(item?.scope || "") : "";
    const scope = ["client", "server", "both"].includes(requestedScope) ? requestedScope : (legacyRequired ? "both" : "server");
    unique.set(key, { key, scope, clientRequired: scope !== "server" });
  }
  return [...unique.values()];
}

function readSelections(worldId) {
  return normalizeSelections(dbm.getSetting(selectionKey(worldId), []));
}

function scanLane(lane, root, selected, pakInstallMode) {
  const label = lane === "server" ? "Server Host" : lane === "required" ? "Required Player Mods" : lane === "steam" ? "Steam Player" : "PC Game Pass Player";
  const base = { id: lane, label, root, ready: false, mods: [], error: null };
  if (!root) return { ...base, error: "Install folder has not been selected." };
  try {
    const scanned = steamlib.scanGameMods(root);
    return { ...base, root: scanned.installDir, ready: true, mods: scanned.mods.map((mod) => {
      const key = `${lane}|${mod.key}`;
      const managed = selected.get(key);
      return { ...mod, pakInstallMode: mod.type === "pak" ? pakInstallMode : undefined, lane, selectionKey: key, selected: !!managed, scope: managed?.scope || "both", clientRequired: managed?.scope !== "server" };
    }) };
  } catch (e) { return { ...base, error: e.message }; }
}

function status(worldId) {
  const modSelections = readSelections(worldId);
  const selected = new Map(modSelections.map((item) => [item.key, item]));
  const laneRoots = roots(worldId);
  const pakInstallMode = readPakInstallMode(worldId);
  const world = dbm.getWorld(worldId);
  const coreDir = dbm.getSetting("applicationSetup:serverDir", null);
  return {
    modLanes: LANES.map((lane) => scanLane(lane, laneRoots[lane], selected, pakInstallMode)),
    modSelections,
    modLaneSelections: modSelections.map((item) => item.key),
    pakInstallMode,
    canDeleteServerMods: canDeleteServerFiles(world, coreDir),
  };
}

function canDeleteServerFiles(world, coreDir) {
  if (!coreDir || !forks.managedFork(world, coreDir)) return false;
  const ledger = forks.readLedger(world.install_dir);
  return !!(ledger?.coreDir && path.resolve(ledger.coreDir).toLowerCase() === path.resolve(coreDir).toLowerCase());
}

function checkedDeleteTargets(world, mod) {
  const game = serverGameRoot(world.install_dir);
  const allowed = mod.type === "pak"
    ? [path.join(game, "Content", "Paks", "~mods"), path.join(game, "Content", "Paks", "LogicMods")]
    : mod.type === "ue4ss"
      ? [path.join(game, "Binaries", mod.location, "ue4ss", "Mods")]
      : [path.join(game, "Binaries", mod.location, "ue4ss", "Mods", "RuneSchema", "mods")];
  const targets = mod.type === "pak" ? mod.files || [] : [mod.path];
  if (!targets.length) throw new Error("No mod files remain to delete.");
  const safe = [];
  for (const target of targets) {
    const absolute = path.resolve(target);
    const parent = mod.type === "pak" ? path.dirname(absolute) : path.dirname(absolute);
    if (!allowed.some((base) => {
      const relative = path.relative(base, absolute);
      return relative && relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative)
        && (mod.type !== "pak" || path.dirname(relative) === "." || path.dirname(path.dirname(relative)) === ".");
    })) throw new Error("The detected mod is outside a supported server mod folder.");
    if (!fs.existsSync(absolute)) throw new Error(`Mod file disappeared: ${absolute}`);
    const anchor = allowed.find((base) => {
      const relative = path.relative(base, absolute);
      return relative && relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
    });
    for (let current = absolute; path.resolve(current) !== path.resolve(anchor); current = path.dirname(current)) {
      if (fs.lstatSync(current).isSymbolicLink()) throw new Error("Linked mod paths cannot be deleted by the launcher.");
    }
    if (fs.lstatSync(anchor).isSymbolicLink() || fs.realpathSync(absolute).toLowerCase() !== absolute.toLowerCase()) {
      throw new Error("Linked or redirected mod paths cannot be deleted by the launcher.");
    }
    if (mod.type === "pak" && !/\.(?:pak|utoc|ucas|sig)$/i.test(absolute)) throw new Error("Only PAK triplet files can be deleted here.");
    if (mod.type !== "pak" && path.resolve(parent).toLowerCase() !== path.resolve(allowed[0]).toLowerCase()) {
      throw new Error("Only a detected direct mod entry can be deleted.");
    }
    safe.push(absolute);
  }
  return safe;
}

function deleteServerMod(worldId, key, { trash = trashPath } = {}) {
  const world = dbm.getWorld(worldId);
  const coreDir = dbm.getSetting("applicationSetup:serverDir", null);
  if (!canDeleteServerFiles(world, coreDir)) throw new Error("File deletion is available only for an RSDW-managed Server profile linked to this core.");
  const snapshot = status(worldId);
  const mod = snapshot.modLanes.find((lane) => lane.id === "server")?.mods.find((item) => item.selectionKey === key);
  if (!mod || !mod.syncEligible || !["pak", "ue4ss", "runeschema"].includes(mod.type)) throw new Error("The selected server mod no longer exists or is not deletable.");
  const targets = checkedDeleteTargets(world, mod);
  const stage = path.join(path.dirname(world.install_dir), `.${world.world_id}.mod-delete-${crypto.randomUUID()}`);
  const moved = [];
  let removedEntry = null;
  try {
    fs.mkdirSync(stage);
    for (let index = 0; index < targets.length; index++) {
      const parked = path.join(stage, `${index}-${path.basename(targets[index])}`);
      fs.renameSync(targets[index], parked);
      moved.push({ original: targets[index], parked });
    }
    if (mod.type !== "pak") {
      const modsDir = mod.type === "ue4ss" ? path.dirname(mod.path) : path.dirname(path.dirname(path.dirname(mod.path)));
      removedEntry = loaderMods.removeEntry(modsDir, mod.type, mod.loaderEntryName);
    }
    trash(stage);
  } catch (error) {
    try { loaderMods.restoreRemovedEntry(removedEntry); } catch {}
    for (const item of moved.reverse()) {
      try { if (fs.existsSync(item.parked)) fs.renameSync(item.parked, item.original); } catch {}
    }
    try { if (fs.existsSync(stage) && !fs.readdirSync(stage).length) fs.rmdirSync(stage); } catch {}
    throw error;
  }
  const removed = new Set(targets.map((target) => path.resolve(target).toLowerCase()));
  const selections = snapshot.modSelections.filter((item) => {
    if (item.key === key) return false;
    if (item.scope === "client") return true;
    const source = snapshot.modLanes.flatMap((lane) => lane.mods).find((row) => row.selectionKey === item.key);
    if (!source) return true;
    const destination = destinationFor(world.install_dir, source, worldId);
    const destinations = source.type === "pak" ? (source.files || []).map((file) => path.join(destination, path.basename(file))) : [destination];
    return !destinations.some((target) => removed.has(path.resolve(target).toLowerCase()));
  });
  dbm.setSetting(selectionKey(worldId), selections);
  dbm.setSetting(ledgerKey(worldId), readList(ledgerKey(worldId)).filter((target) => !removed.has(path.resolve(target).toLowerCase())));
  dbm.logEvent(worldId, "mod", `Moved ${mod.name} (${targets.length} file${targets.length === 1 ? "" : "s"}) from this Server profile to the OS trash`);
  return { removedFiles: targets.length, name: mod.name, ...status(worldId) };
}

function serverGameRoot(installDir) { const nested = path.join(installDir, "RSDragonwilds"); return fs.existsSync(nested) ? nested : installDir; }
function safeModFolder(value) {
  const name = String(value || "").trim();
  if (!name || name === "." || name === ".." || /[\\/:*?"<>|]/.test(name)) throw new Error("ID.txt contains an unsafe ModID");
  return name;
}
function destinationFor(serverRoot, mod, worldId) {
  const game = serverGameRoot(serverRoot);
  if (mod.type === "pak") {
    if (readPakInstallMode(worldId) === "runeschema") return path.join(game, "Binaries", "Win64", "ue4ss", "Mods", "RuneSchema", "mods", safeModFolder(mod.modId || mod.folderName || mod.name), "paks");
    return path.join(game, "Content", "Paks", "~mods");
  }
  // Dedicated Windows servers always consume the Win64 tree, even when the
  // source mod was discovered under a Game Pass WinGDK client install.
  const platform = "Win64";
  if (mod.type === "ue4ss") return path.join(game, "Binaries", platform, "ue4ss", "Mods", safeModFolder(mod.folderName || mod.name));
  if (mod.type === "runeschema") return path.join(game, "Binaries", platform, "ue4ss", "Mods", "RuneSchema", "mods", safeModFolder(mod.folderName || mod.name));
  return null;
}
function copyDir(source, destination) {
  fs.mkdirSync(destination, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const src = path.join(source, entry.name), dst = path.join(destination, entry.name);
    if (entry.isDirectory()) copyDir(src, dst); else if (entry.isFile()) fs.copyFileSync(src, dst);
  }
}
function copyMod(mod, destination) {
  if (mod.type === "pak") {
    fs.mkdirSync(destination, { recursive: true });
    return (mod.files || []).map((source) => {
      const target = path.join(destination, path.basename(source));
      if (path.resolve(source).toLowerCase() !== path.resolve(target).toLowerCase()) fs.copyFileSync(source, target);
      return target;
    });
  }
  if (path.resolve(mod.path).toLowerCase() === path.resolve(destination).toLowerCase()) return [destination];
  fs.rmSync(destination, { recursive: true, force: true });
  if (fs.statSync(mod.path).isDirectory()) copyDir(mod.path, destination);
  else { fs.mkdirSync(path.dirname(destination), { recursive: true }); fs.copyFileSync(mod.path, destination); }
  return [destination];
}

function selectedMods(worldId, { clientRequiredOnly = true } = {}) {
  const snapshot = status(worldId);
  const wanted = new Map(snapshot.modSelections.map((item) => [item.key, item]));
  return snapshot.modLanes.flatMap((lane) => lane.mods
    .filter((mod) => wanted.has(mod.selectionKey) && mod.syncEligible && mod.loaderEnabled !== false && !mod.loaderBlockedByFramework)
    .map((mod) => ({ ...mod, scope: wanted.get(mod.selectionKey).scope, clientRequired: wanted.get(mod.selectionKey).scope !== "server" })))
    .filter((mod) => !clientRequiredOnly || mod.clientRequired);
}

function setSelections(worldId, requested) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const snapshot = status(worldId);
  const available = new Map(snapshot.modLanes.flatMap((lane) => lane.mods.filter((mod) => mod.syncEligible).map((mod) => [mod.selectionKey, mod])));
  const selections = normalizeSelections(requested);
  const keys = selections.map((item) => item.key);
  const missing = keys.filter((key) => !available.has(key));
  if (missing.length) throw new Error(`Selected mod folders are no longer present: ${missing.join(", ")}`);
  if (keys.some((key) => available.get(key).lane !== "server") && !world.install_dir) {
    throw new Error("Choose the Server Host install before synchronizing player mod folders.");
  }
  const destinations = new Map();
  for (const key of keys) {
    const mod = available.get(key);
    const selection = selections.find((item) => item.key === key);
    if (selection.scope === "client") continue;
    const destination = destinationFor(world.install_dir, mod, worldId);
    const targets = mod.type === "pak"
      ? (mod.files || []).map((source) => path.join(destination, path.basename(source)))
      : [destination];
    for (const target of targets) {
      const normalized = target && path.resolve(target).toLowerCase();
      if (normalized && destinations.has(normalized)) {
        throw new Error(`Two selected folders target the same server file or folder: ${destinations.get(normalized)} and ${mod.selectionKey}. Keep only one source selected.`);
      }
      if (normalized) destinations.set(normalized, mod.selectionKey);
    }
  }
  const previous = readList(ledgerKey(worldId)), copied = [];
  for (const key of keys) {
    const mod = available.get(key);
    const selection = selections.find((item) => item.key === key);
    if (mod.lane === "server" || selection.scope === "client") continue;
    const destination = destinationFor(world.install_dir, mod, worldId);
    if (destination) {
      copied.push(...copyMod(mod, destination));
      if (["ue4ss", "runeschema"].includes(mod.type) && mod.loaderEnabled !== null) {
        const modsDir = mod.type === "ue4ss" ? path.dirname(destination) : path.dirname(path.dirname(path.dirname(destination)));
        loaderMods.setEnabled(modsDir, mod.type, mod.loaderEntryName, destination, mod.loaderEnabled);
      }
    }
  }
  const retained = new Set(copied.map((value) => path.resolve(value).toLowerCase()));
  for (const oldTarget of previous) if (!retained.has(path.resolve(oldTarget).toLowerCase()) && fs.existsSync(oldTarget)) trashPath(oldTarget);
  dbm.setSetting(selectionKey(worldId), selections);
  dbm.setSetting(ledgerKey(worldId), copied);
  const clientCount = selections.filter((item) => item.scope !== "server").length;
  const serverCount = selections.filter((item) => item.scope !== "client").length;
  dbm.logEvent(worldId, "mod", `Saved ${keys.length} managed mod folder${keys.length === 1 ? "" : "s"}; ${clientCount} client / ${serverCount} server`);
  return status(worldId);
}

function setLoaderEnabled(worldId, lane, key, enabled) {
  if (!LANES.includes(lane)) throw new Error("Unknown mod lane");
  if (typeof enabled !== "boolean") throw new Error("Enabled must be true or false");
  const snapshot = status(worldId);
  const item = snapshot.modLanes.find((row) => row.id === lane)?.mods.find((mod) => mod.selectionKey === key);
  if (!item || !["ue4ss", "runeschema", "framework"].includes(item.type)) throw new Error("Mod is not a detected loader-managed mod");
  const kind = item.type === "framework" ? "ue4ss" : item.type;
  const modsDir = kind === "ue4ss" ? path.dirname(item.path) : path.dirname(path.dirname(path.dirname(item.path)));
  const name = item.loaderEntryName;
  loaderMods.setEnabled(modsDir, kind, name, item.path, enabled);
  const selection = snapshot.modSelections.find((row) => row.key === key);
  if (lane !== "server" && selection && selection.scope !== "client" && item.syncEligible) {
    const serverRoot = roots(worldId).server;
    if (serverRoot) {
      const destination = destinationFor(serverRoot, item, worldId);
      if (destination && fs.existsSync(destination)) {
        const targetModsDir = kind === "ue4ss" ? path.dirname(destination) : path.dirname(path.dirname(path.dirname(destination)));
        loaderMods.setEnabled(targetModsDir, kind, name, destination, enabled);
      }
    }
  }
  dbm.logEvent(worldId, "mod", `${enabled ? "Enabled" : "Disabled"} ${item.name} in ${lane} ${kind} loader list`);
  return status(worldId);
}

function reapplySelections(worldId) {
  const selections = readSelections(worldId);
  if (!selections.length) return status(worldId);
  const snapshot = status(worldId);
  const available = new Set(snapshot.modLanes.flatMap((lane) => lane.mods.filter((mod) => mod.syncEligible).map((mod) => mod.selectionKey)));
  const retained = selections.filter((item) => available.has(item.key));
  const missing = selections.filter((item) => !available.has(item.key));
  if (missing.length) dbm.logEvent(worldId, "mod", `Dropped ${missing.length} managed mod selection${missing.length === 1 ? "" : "s"} that no longer exist after the server update`);
  return setSelections(worldId, retained);
}

function setRequiredSource(worldId, requestedPath) {
  if (!dbm.getWorld(worldId)) throw new Error("World not found");
  const raw = String(requestedPath || "").trim();
  const normalized = raw ? steamlib.normalizeGameInstall(raw) : null;
  if (raw && !normalized) throw new Error("Required mod source must be a Dragonwilds installation containing RSDragonwilds\\Binaries and RSDragonwilds\\Content.");

  // Remove selections and server copies owned by the old source before switching.
  const retained = readSelections(worldId).filter((item) => !item.key.startsWith("required|"));
  setSelections(worldId, retained);
  dbm.setSetting(requiredSourceKey(worldId), normalized);
  dbm.logEvent(worldId, "mod", normalized ? `Set required player mod source to ${normalized}` : "Cleared required player mod source");
  return status(worldId);
}

function setPakInstallMode(worldId, requestedMode) {
  if (!dbm.getWorld(worldId)) throw new Error("World not found");
  const mode = requestedMode === "runeschema" ? "runeschema" : "classic";
  dbm.setSetting(pakInstallModeKey(worldId), mode);
  dbm.logEvent(worldId, "mod", mode === "runeschema" ? "PAK destination changed to RuneSchema-managed mod folders" : "PAK destination changed to Content/Paks/~mods");
  return setSelections(worldId, readSelections(worldId));
}

function browse(worldId, lane, relative = "") {
  if (!LANES.includes(lane)) throw new Error("Unknown mod lane");
  const root = roots(worldId)[lane];
  if (!root) throw new Error("Choose this install folder first.");
  const normalized = steamlib.normalizeGameInstall(root);
  if (!normalized) throw new Error("The routed install folder is no longer valid.");
  const base = fs.realpathSync(path.resolve(normalized));
  const parts = String(relative || "").replace(/\\/g, "/").split("/").filter((part) => part && part !== ".");
  if (parts.some((part) => part === "..")) throw new Error("Folder path escapes the install.");
  const requested = path.resolve(base, ...parts);
  const current = fs.realpathSync(requested);
  if (current !== base && !current.toLowerCase().startsWith((base + path.sep).toLowerCase())) throw new Error("Folder path escapes the install.");
  const directories = fs.readdirSync(current, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => ({ name: entry.name, relative: [...parts, entry.name].join("/") }));
  const scanned = steamlib.scanGameMods(base);
  const editableRoots = scanned.mods.map((mod) => {
    try { return { mod, root: fs.realpathSync(mod.path) }; } catch { return null; }
  }).filter(Boolean);
  const files = fs.readdirSync(current, { withFileTypes: true })
    .filter((entry) => entry.isFile() && EDITABLE_EXTENSIONS.has(path.extname(entry.name).toLowerCase()))
    .map((entry) => {
      const file = path.join(current, entry.name);
      const owner = editableRoots.find(({ root }) => file === root || file.toLowerCase().startsWith((root + path.sep).toLowerCase()));
      if (!owner) return null;
      return {
        name: entry.name,
        relative: [...parts, entry.name].join("/"),
        language: path.extname(entry.name).toLowerCase() === ".lua" ? "lua" : "json",
        modName: owner.mod.name,
        hotload: owner.mod.identity?.hotload === true,
      };
    }).filter(Boolean);
  return { lane, root: base, relative: parts.join("/"), current, breadcrumbs: parts.map((name, index) => ({ name, relative: parts.slice(0, index + 1).join("/") })), directories, files };
}

function editableTarget(worldId, lane, relative) {
  if (!LANES.includes(lane)) throw new Error("Unknown mod lane");
  const root = roots(worldId)[lane];
  const normalized = root && steamlib.normalizeGameInstall(root);
  if (!normalized) throw new Error("The routed install folder is no longer valid.");
  const parts = String(relative || "").replace(/\\/g, "/").split("/").filter((part) => part && part !== ".");
  if (!parts.length || parts.some((part) => part === "..")) throw new Error("Editor path escapes the install.");
  const base = fs.realpathSync(path.resolve(normalized));
  const requested = path.resolve(base, ...parts);
  if (requested === base || !requested.toLowerCase().startsWith((base + path.sep).toLowerCase())) throw new Error("Editor path escapes the install.");
  const extension = path.extname(requested).toLowerCase();
  if (!EDITABLE_EXTENSIONS.has(extension)) throw new Error("Only JSON, JSONC, and Lua mod files can be edited.");
  const stat = fs.lstatSync(requested);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error("The selected editor target is not a regular file.");
  if (stat.size > MAX_EDITABLE_BYTES) throw new Error("This mod file is larger than the 2 MiB editor limit.");
  const file = fs.realpathSync(requested);
  if (!file.toLowerCase().startsWith((base + path.sep).toLowerCase())) throw new Error("Editor path escapes the install.");
  const scanned = steamlib.scanGameMods(base);
  const owner = scanned.mods.find((mod) => {
    try {
      const modRoot = fs.realpathSync(mod.path);
      return file === modRoot || file.toLowerCase().startsWith((modRoot + path.sep).toLowerCase());
    } catch { return false; }
  });
  if (!owner) throw new Error("Only files beneath detected mod directories can be edited.");
  return { file, relative: parts.join("/"), extension, owner, hotload: owner.identity?.hotload === true };
}

function readEditableFile(worldId, lane, relative) {
  const target = editableTarget(worldId, lane, relative);
  const content = fs.readFileSync(target.file, "utf8");
  return {
    relative: target.relative,
    name: path.basename(target.file),
    language: target.extension === ".lua" ? "lua" : "json",
    content,
    etag: crypto.createHash("sha256").update(content).digest("hex"),
    modName: target.owner.name,
    hotload: target.hotload,
  };
}

function writeEditableFile(worldId, lane, relative, content, expectedEtag) {
  const target = editableTarget(worldId, lane, relative);
  const value = String(content ?? "");
  if (Buffer.byteLength(value, "utf8") > MAX_EDITABLE_BYTES) throw new Error("This mod file is larger than the 2 MiB editor limit.");
  const current = fs.readFileSync(target.file, "utf8");
  const currentEtag = crypto.createHash("sha256").update(current).digest("hex");
  if (expectedEtag && expectedEtag !== currentEtag) throw new Error("This file changed on disk. Reopen it before saving your edits.");
  if (target.extension === ".json") {
    try { JSON.parse(value); } catch (error) { throw new Error(`JSON is not valid: ${error.message}`); }
  }
  const temp = `${target.file}.rsdw-edit-${process.pid}-${crypto.randomBytes(4).toString("hex")}`;
  const previous = `${target.file}.rsdw-previous-${process.pid}-${crypto.randomBytes(4).toString("hex")}`;
  try {
    fs.writeFileSync(temp, value, { encoding: "utf8", flag: "wx" });
    // Keep a rollback copy because Windows game folders and antivirus filters can
    // deny rename-over-existing even when ordinary writes are allowed.
    fs.copyFileSync(target.file, previous, fs.constants.COPYFILE_EXCL);
    try { fs.copyFileSync(temp, target.file); }
    catch (error) { fs.copyFileSync(previous, target.file); throw error; }
    fs.rmSync(previous, { force: true });
  } finally {
    try { if (fs.existsSync(temp)) fs.rmSync(temp, { force: true }); } catch {}
    try { if (fs.existsSync(previous) && !fs.existsSync(target.file)) fs.copyFileSync(previous, target.file); } catch {}
    try { if (fs.existsSync(previous)) fs.rmSync(previous, { force: true }); } catch {}
  }
  dbm.logEvent(worldId, "mod", `Edited ${target.owner.name}: ${target.relative}`);
  return readEditableFile(worldId, lane, relative);
}

module.exports = { status, setSelections, setLoaderEnabled, deleteServerMod, selectedMods, browse, readEditableFile, writeEditableFile, setRequiredSource, setPakInstallMode, reapplySelections, readSelections, readPakInstallMode };
