const fs = require("fs");
const path = require("path");
const dbm = require("./db");
const steamlib = require("./steamlibrary");
const { trashPath } = require("./trash");

const LANES = ["server", "steam", "gamepass"];
const selectionKey = (worldId) => `modLaneSelection:${worldId}`;
const ledgerKey = (worldId) => `modLaneLedger:${worldId}`;

function readList(key) {
  const value = dbm.getSetting(key, []);
  if (Array.isArray(value)) return value.map(String);
  try { const parsed = JSON.parse(value || "[]"); return Array.isArray(parsed) ? parsed.map(String) : []; }
  catch { return []; }
}

function roots(worldId) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  return { server: world.install_dir || null, steam: dbm.getSetting("clientInstall:steam", null), gamepass: dbm.getSetting("clientInstall:gamepass", null) };
}

function scanLane(lane, root, selected) {
  const label = lane === "server" ? "Server Host" : lane === "steam" ? "Steam Player" : "PC Game Pass Player";
  const base = { id: lane, label, root, ready: false, mods: [], error: null };
  if (!root) return { ...base, error: "Install folder has not been selected." };
  try {
    const scanned = steamlib.scanGameMods(root);
    return { ...base, root: scanned.installDir, ready: true, mods: scanned.mods.map((mod) => ({ ...mod, lane, selectionKey: `${lane}|${mod.key}`, selected: selected.has(`${lane}|${mod.key}`) })) };
  } catch (e) { return { ...base, error: e.message }; }
}

function status(worldId) {
  const selected = new Set(readList(selectionKey(worldId)));
  const laneRoots = roots(worldId);
  return { modLanes: LANES.map((lane) => scanLane(lane, laneRoots[lane], selected)), modLaneSelections: [...selected] };
}

function serverGameRoot(installDir) { const nested = path.join(installDir, "RSDragonwilds"); return fs.existsSync(nested) ? nested : installDir; }
function destinationFor(serverRoot, mod) {
  const game = serverGameRoot(serverRoot);
  if (mod.type === "pak") return path.join(game, "Content", "Paks", "~mods");
  // Dedicated Windows servers always consume the Win64 tree, even when the
  // source mod was discovered under a Game Pass WinGDK client install.
  const platform = "Win64";
  if (mod.type === "ue4ss") return path.join(game, "Binaries", platform, "ue4ss", "Mods", mod.name);
  if (mod.type === "runeschema") return path.join(game, "Binaries", platform, "ue4ss", "Mods", "RuneSchema", "mods", mod.name);
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

function selectedMods(worldId) {
  const snapshot = status(worldId), wanted = new Set(snapshot.modLaneSelections);
  return snapshot.modLanes.flatMap((lane) => lane.mods.filter((mod) => wanted.has(mod.selectionKey) && mod.syncEligible));
}

function setSelections(worldId, requested) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const snapshot = status(worldId);
  const available = new Map(snapshot.modLanes.flatMap((lane) => lane.mods.filter((mod) => mod.syncEligible).map((mod) => [mod.selectionKey, mod])));
  const keys = [...new Set((requested || []).map(String))];
  const missing = keys.filter((key) => !available.has(key));
  if (missing.length) throw new Error(`Selected mod folders are no longer present: ${missing.join(", ")}`);
  if (keys.some((key) => available.get(key).lane !== "server") && !world.install_dir) {
    throw new Error("Choose the Server Host install before synchronizing player mod folders.");
  }
  const destinations = new Map();
  for (const key of keys) {
    const mod = available.get(key);
    const destination = destinationFor(world.install_dir, mod);
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
    if (mod.lane === "server") continue;
    const destination = destinationFor(world.install_dir, mod);
    if (destination) copied.push(...copyMod(mod, destination));
  }
  const retained = new Set(copied.map((value) => path.resolve(value).toLowerCase()));
  for (const oldTarget of previous) if (!retained.has(path.resolve(oldTarget).toLowerCase()) && fs.existsSync(oldTarget)) trashPath(oldTarget);
  dbm.setSetting(selectionKey(worldId), keys);
  dbm.setSetting(ledgerKey(worldId), copied);
  dbm.logEvent(worldId, "mod", `Saved ${keys.length} selected mod folder${keys.length === 1 ? "" : "s"} across the routed installs`);
  return status(worldId);
}

function browse(worldId, lane, relative = "") {
  if (!LANES.includes(lane)) throw new Error("Unknown mod lane");
  const root = roots(worldId)[lane];
  if (!root) throw new Error("Choose this install folder first.");
  const normalized = steamlib.normalizeGameInstall(root);
  if (!normalized) throw new Error("The routed install folder is no longer valid.");
  const base = path.resolve(normalized);
  const parts = String(relative || "").replace(/\\/g, "/").split("/").filter((part) => part && part !== ".");
  if (parts.some((part) => part === "..")) throw new Error("Folder path escapes the install.");
  const current = path.resolve(base, ...parts);
  if (current !== base && !current.toLowerCase().startsWith((base + path.sep).toLowerCase())) throw new Error("Folder path escapes the install.");
  const directories = fs.readdirSync(current, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => ({ name: entry.name, relative: [...parts, entry.name].join("/") }));
  return { lane, root: base, relative: parts.join("/"), current, breadcrumbs: parts.map((name, index) => ({ name, relative: parts.slice(0, index + 1).join("/") })), directories };
}

module.exports = { status, setSelections, selectedMods, browse };
