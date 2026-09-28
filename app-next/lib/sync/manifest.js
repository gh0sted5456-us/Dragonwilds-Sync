const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const dbm = require("../db");
const mods = require("../mods");
const steamlib = require("../steamlibrary");
const runtimePackages = require("../runtime-packages");

const PROTOCOL = "dragonwilds-world-sync";
const PROTOCOL_VERSION = 2;
const prerequisiteKey = (worldId) => `syncPrerequisites:${worldId}`;

function sha256File(file) {
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    let read;
    while ((read = fs.readSync(fd, buffer, 0, buffer.length, null)) > 0) hash.update(buffer.subarray(0, read));
  } finally { fs.closeSync(fd); }
  return hash.digest("hex");
}

function walkFiles(root) {
  if (!fs.existsSync(root)) return [];
  const stat = fs.statSync(root);
  if (stat.isFile()) return [{ source: root, relative: path.basename(root) }];
  const out = [];
  const visit = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.isSymbolicLink()) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.isFile()) out.push({ source: full, relative: path.relative(root, full).replace(/\\/g, "/") });
    }
  };
  visit(root);
  return out;
}

function targetBase(mod) {
  if (mod.type === "pak") return "RSDragonwilds/Content/Paks/~mods";
  if (mod.type === "ue4ss") return `RSDragonwilds/Binaries/Win64/ue4ss/Mods/${safeSegment(mod.name)}`;
  if (mod.type === "runeschema") return `RSDragonwilds/Binaries/Win64/ue4ss/Mods/RuneSchema/mods/${safeSegment(mod.name)}`;
  throw new Error(`Unsupported synchronization lane: ${mod.type}`);
}

function safeSegment(value) {
  const segment = String(value || "").trim();
  if (!segment || segment === "." || segment === ".." || /[\\/:*?"<>|]/.test(segment)) throw new Error("Unsafe mod name");
  return segment;
}

function filesForMod(mod) {
  const base = targetBase(mod);
  const sourceFiles = mod.type === "pak"
    ? (mod.files || []).map((source) => ({ source, relative: path.basename(source) }))
    : walkFiles(mod.path);
  return sourceFiles.map(({ source, relative }) => {
    const target = `${base}/${relative}`.replace(/\\/g, "/");
    const stat = fs.statSync(source);
    return { target, size: stat.size, sha256: sha256File(source), source };
  });
}

function publicFile(file) {
  return { target: file.target, size: file.size, sha256: file.sha256 };
}

function buildWorldManifest(worldId, options = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const inventory = mods.selectedLaneMods(worldId);
  const runtimeUnits = runtimePackages.syncUnits(worldId, options.platform);
  const modUnits = inventory.map((mod) => {
    const files = filesForMod(mod);
    const identity = crypto.createHash("sha256");
    for (const file of files) identity.update(`${file.target}\0${file.size}\0${file.sha256}\n`);
    return {
      key: mod.selectionKey || mod.key,
      name: mod.name,
      type: mod.type,
      contentHash: identity.digest("hex"),
      fileCount: files.length,
      bytes: files.reduce((sum, file) => sum + file.size, 0),
      files: files.map(publicFile),
    };
  });
  const units = [
    ...runtimeUnits.map((unit) => ({ ...unit, files: unit.files.map(publicFile) })),
    ...modUnits,
  ];
  const revisionHash = crypto.createHash("sha256");
  for (const unit of units) revisionHash.update(`${unit.key}\0${unit.contentHash}\n`);
  return {
    protocol: PROTOCOL,
    protocolVersion: PROTOCOL_VERSION,
    world: {
      id: world.world_id,
      name: world.display_name,
      gamePort: world.game_port,
      type: world.community_server ? "Community" : "Private",
      identity: {
        iconData: world.icon_data || null,
        bannerData: world.banner_data || null,
        accentColor: world.accent_color || null,
      },
    },
    revision: revisionHash.digest("hex"),
    generatedAt: new Date().toISOString(),
    prerequisites: getPrerequisites(worldId),
    clientPlatform: options.platform === "gamepass" ? "gamepass" : "steam",
    units,
  };
}

function getPrerequisites(worldId) {
  const saved = dbm.getSetting(prerequisiteKey(worldId), {});
  return {
    ue4ss: String(saved?.ue4ss || "").trim() || null,
    runeSchema: String(saved?.runeSchema || "").trim() || null,
    managedByClient: Object.values(runtimePackages.status(worldId)).some((item) => item.installed),
  };
}

function setPrerequisites(worldId, value = {}) {
  if (!dbm.getWorld(worldId)) throw new Error("World not found");
  const prerequisites = {
    ue4ss: String(value.ue4ss || "").trim() || null,
    runeSchema: String(value.runeSchema || "").trim() || null,
  };
  dbm.setSetting(prerequisiteKey(worldId), prerequisites);
  return prerequisites;
}

function resolveWorldFile(worldId, requestedTarget, options = {}) {
  const target = String(requestedTarget || "").replace(/\\/g, "/");
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const runtimeFile = runtimePackages.resolveSyncFile(worldId, target, options.platform);
  if (runtimeFile) return runtimeFile;
  const inventory = mods.selectedLaneMods(worldId);
  for (const mod of inventory) {
    const match = filesForMod(mod).find((file) => file.target === target);
    if (match) return match;
  }
  throw new Error("Mod file is not declared by this World");
}

function compareManifest(manifest, gameInstall) {
  if (!manifest || manifest.protocol !== PROTOCOL || manifest.protocolVersion !== PROTOCOL_VERSION) throw new Error("Unsupported Dragonwilds Sync manifest");
  const install = steamlib.normalizeGameInstall(gameInstall);
  if (!install) throw new Error("Choose a valid RuneScape: Dragonwilds game installation.");
  const changes = [];
  for (const unit of manifest.units || []) {
    for (const file of unit.files || []) {
      const relative = String(file.target || "").replace(/\\/g, "/");
      if (!relative.startsWith("RSDragonwilds/") || relative.split("/").some((part) => !part || part === "." || part === "..")) throw new Error("Manifest contains an unsafe target path");
      const local = path.resolve(install, ...relative.split("/"));
      const root = path.resolve(install) + path.sep;
      if (!local.toLowerCase().startsWith(root.toLowerCase())) throw new Error("Manifest target escapes the game installation");
      let state = "missing";
      if (fs.existsSync(local) && fs.statSync(local).isFile()) state = sha256File(local) === file.sha256 ? "current" : "changed";
      if (state !== "current") changes.push({ unitKey: unit.key, target: relative, state, size: file.size, sha256: file.sha256 });
    }
  }
  return { revision: manifest.revision, current: changes.length === 0, changes };
}

module.exports = { PROTOCOL, PROTOCOL_VERSION, buildWorldManifest, compareManifest, sha256File, resolveWorldFile, getPrerequisites, setPrerequisites };
