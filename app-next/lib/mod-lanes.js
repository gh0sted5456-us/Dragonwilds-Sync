const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const dbm = require("./db");
const steamlib = require("./steamlibrary");
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
  return {
    modLanes: LANES.map((lane) => scanLane(lane, laneRoots[lane], selected, pakInstallMode)),
    modSelections,
    modLaneSelections: modSelections.map((item) => item.key),
    pakInstallMode,
  };
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
    .filter((mod) => wanted.has(mod.selectionKey) && mod.syncEligible)
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
    if (destination) copied.push(...copyMod(mod, destination));
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

module.exports = { status, setSelections, selectedMods, browse, readEditableFile, writeEditableFile, setRequiredSource, setPakInstallMode, reapplySelections, readSelections, readPakInstallMode };
