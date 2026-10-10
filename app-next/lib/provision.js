// lib/provision.js  (spec §2 provisioning, §3 import, §8 update, duplicate)
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const AdmZip = require("adm-zip");
const dbm = require("./db");
const ini = require("./ini");
const serverProfiles = require("./active-server-profile");
const { suggestPorts } = require("./ports");
const { createBackup } = require("./backups");
const { trashPath } = require("./trash");
const os = require("os");
const { P } = require("./paths");

// Create a world profile record (no install yet).
function createProfile({ display_name, install_dir, ports, admin_password, platform, owner_id, default_world_name, wine_binary, wine_prefix, wine_launch_flags }) {
  const p = ports || suggestPorts();
  const plat = platform === "windows" || platform === "linux"
  ? platform
  : (os.platform() === "win32" ? "windows" : "linux");
  const world = {
    world_id: crypto.randomUUID(),
    display_name: display_name || "New World",
    install_dir,
    owner_id: owner_id || null,
    default_world_name: default_world_name || null,
    platform: plat,
    env_vars: "{}",
    wine_binary: (wine_binary && wine_binary.trim()) || "wine",
    wine_prefix: wine_prefix || null,
    wine_launch_flags: wine_launch_flags || "",
    game_port: p.game_port,
    query_port: p.query_port,
    rest_api_port: p.rest_api_port,
    rcon_port: p.rcon_port,
    admin_password: admin_password || crypto.randomBytes(6).toString("hex"),
    rest_api_enabled: 1,
    status: "stopped",
    autostart: 0,
    crash_guard: 1,
    build_id: null,
    extra_args: "",
    created_at: Date.now(),
  };
  return dbm.insertWorld(world);
}

// Register an already-installed server (no SteamCMD). Points a new profile at an
// existing install dir, captures its build id, and writes this world's own
// ports/password into its ini (preserving any existing settings/saves).
function adoptExistingInstall({ display_name, install_dir, ports, admin_password, keepExistingPassword }) {
  const detect = require("./detect");
  const info = detect.inspect(install_dir);
  if (!info.valid) throw new Error(info.reason || "Not a valid Dragonwilds server install");

  const world = createProfile({
    display_name: display_name || info.serverName || "Existing World",
    install_dir: info.installDir,
    ports,
    admin_password,
    platform: info.platform,
  });

  // If the user wants to keep the server's current admin password, read it from ini.
  if (keepExistingPassword) {
    try {
      const s = ini.readSettings(info.installDir, info.platform);
      const raw = s.options.AdminPassword;
      if (raw) {
        const pw = String(raw).replace(/^"|"$/g, "");
        if (pw) dbm.updateWorld(world.world_id, { admin_password: pw });
      }
    } catch {}
  }

  if (info.buildId) dbm.updateWorld(world.world_id, { build_id: info.buildId });

  // Apply this world's network identity and immediately capture a profile-owned
  // snapshot. The shared live INI is never allowed to be the only durable copy.
  try {
    const adopted = dbm.getWorld(world.world_id);
    ini.applyWorldNetworkSettings(info.installDir, adopted);
    serverProfiles.saveRawSettings(
      world.world_id,
      ini.readRawSettings(info.installDir, adopted.platform).content
    );
  } catch {}

  dbm.logEvent(world.world_id, "provision", `Adopted existing install (build ${info.buildId || "unknown"})`);
  return { world: dbm.getWorld(world.world_id), info };
}

// ---- Save import (spec §3) ----
// Dragonwilds uses a flat SaveGames directory and loads the newest .sav file.
// Accept one unambiguous save only, preserving its original filename.
function validateSaveSource(sourcePath) {
  if (!sourcePath || !fs.existsSync(sourcePath)) throw new Error("Save file not found");
  if (/\.sav$/i.test(sourcePath)) {
    return { valid: true, kind: "sav", activeSave: path.basename(sourcePath), entryName: null, saveCount: 1 };
  }
  if (!/\.zip$/i.test(sourcePath)) throw new Error("Choose a Dragonwilds .sav file or a .zip containing exactly one .sav file");

  const zip = new AdmZip(sourcePath);
  const saves = zip.getEntries().filter((entry) => !entry.isDirectory && /\.sav$/i.test(entry.entryName));
  if (saves.length !== 1) {
    throw new Error(`Archive must contain exactly one Dragonwilds .sav file (found ${saves.length})`);
  }
  return {
    valid: true,
    kind: "zip",
    activeSave: path.basename(saves[0].entryName.replace(/\\/g, "/")),
    entryName: saves[0].entryName,
    saveCount: 1,
  };
}

function saveGamesDir(world) {
  return path.join(world.install_dir, "RSDragonwilds", "Saved", "SaveGames");
}

function safeSaveName(value) {
  const name = path.basename(String(value || ""));
  if (!name || !/^[^\\/:*?"<>|]+\.sav$/i.test(name)) throw new Error("Invalid Dragonwilds save-slot name");
  return name;
}

function captureActiveSaves(world) {
  const saveGames = saveGamesDir(world);
  const vault = P.worldSaveSlots(world.world_id);
  let entries = [];
  try { entries = fs.readdirSync(saveGames, { withFileTypes: true }); } catch { return; }
  for (const entry of entries) {
    if (!entry.isFile() || !/\.sav$/i.test(entry.name)) continue;
    const destination = path.join(vault, safeSaveName(entry.name));
    if (!fs.existsSync(destination)) fs.copyFileSync(path.join(saveGames, entry.name), destination);
  }
}

function listSaveSlots(worldId) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  captureActiveSaves(world);
  const active = new Set();
  try {
    for (const entry of fs.readdirSync(saveGamesDir(world), { withFileTypes: true })) {
      if (entry.isFile() && /\.sav$/i.test(entry.name)) active.add(entry.name.toLowerCase());
    }
  } catch {}
  const vault = P.worldSaveSlots(worldId);
  return fs.readdirSync(vault, { withFileTypes: true })
    .filter((entry) => entry.isFile() && /\.sav$/i.test(entry.name))
    .map((entry) => {
      const stat = fs.statSync(path.join(vault, entry.name));
      return { name: entry.name, size: stat.size, modifiedAt: stat.mtimeMs, active: active.has(entry.name.toLowerCase()) };
    })
    .sort((a, b) => Number(b.active) - Number(a.active) || b.modifiedAt - a.modifiedAt);
}

// Replace only Saved/SaveGames. Config, passwords, owner identity, ports and the
// selected Server profile remain untouched. The directory swap ensures the game
// never sees a half-copied world.
async function activateSaveSlot(worldId, slotName, { backupFirst = true } = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  if (require("./supervisor").isAlive(worldId)) throw new Error("Stop the server before replacing its world save");
  const activeSave = safeSaveName(slotName);
  const sourceFile = path.join(P.worldSaveSlots(worldId), activeSave);
  if (!fs.existsSync(sourceFile)) throw new Error("Save slot not found");

  const saveGames = saveGamesDir(world);
  if (backupFirst && fs.existsSync(saveGames)) {
    await createBackup(worldId, "pre-import-safety");
  }
  captureActiveSaves(world);

  fs.mkdirSync(path.dirname(saveGames), { recursive: true });
  const nonce = crypto.randomUUID();
  const incoming = path.join(path.dirname(saveGames), `.SaveGames.incoming-${nonce}`);
  const previous = path.join(path.dirname(saveGames), `.SaveGames.previous-${nonce}`);
  fs.mkdirSync(incoming, { recursive: true });
  const destination = path.join(incoming, activeSave);

  try {
    fs.copyFileSync(sourceFile, destination);
    const now = new Date();
    fs.utimesSync(destination, now, now);

    if (fs.existsSync(saveGames)) fs.renameSync(saveGames, previous);
    try {
      fs.renameSync(incoming, saveGames);
    } catch (error) {
      if (fs.existsSync(previous) && !fs.existsSync(saveGames)) fs.renameSync(previous, saveGames);
      throw error;
    }
  } catch (error) {
    fs.rmSync(incoming, { recursive: true, force: true });
    throw error;
  }

  // A normal backup exists above; the swapped directory is also recoverable.
  if (fs.existsSync(previous)) {
    try { trashPath(previous); } catch {}
  }

  dbm.logEvent(worldId, "import", `Activated world save slot ${activeSave}; Server profile identity retained`);
  return { valid: true, activeSave, slots: listSaveSlots(worldId) };
}

async function importSave(worldId, sourcePath, { backupFirst = true } = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  if (require("./supervisor").isAlive(worldId)) throw new Error("Stop the server before replacing its world save");
  const check = validateSaveSource(sourcePath);
  captureActiveSaves(world);
  const destination = path.join(P.worldSaveSlots(worldId), safeSaveName(check.activeSave));
  if (check.kind === "sav") fs.copyFileSync(sourcePath, destination);
  else {
    const entry = new AdmZip(sourcePath).getEntry(check.entryName);
    if (!entry) throw new Error("The selected save disappeared from its archive");
    fs.writeFileSync(destination, entry.getData());
  }
  return activateSaveSlot(worldId, check.activeSave, { backupFirst });
}

function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const item of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, item.name), d = path.join(dst, item.name);
    if (item.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

module.exports = {
  createProfile, adoptExistingInstall,
  validateSaveSource, validateSaveZip: validateSaveSource, importSave, listSaveSlots, activateSaveSlot, copyDir,
};
