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
function createProfile({ world_id, display_name, install_dir, ports, admin_password, platform, owner_id, default_world_name, wine_binary, wine_prefix, wine_launch_flags }) {
  const p = ports || suggestPorts();
  const effectiveOwnerId = String(owner_id || dbm.getSetting("applicationSetup:ownerId", "") || "").trim();
  if (!effectiveOwnerId) throw new Error("Set a default Owner ID in Application Setup → Dedicated Server, or enter an Owner ID override for this profile.");
  const plat = platform === "windows" || platform === "linux"
  ? platform
  : (os.platform() === "win32" ? "windows" : "linux");
  const world = {
    world_id: world_id || crypto.randomUUID(),
    display_name: display_name || "New World",
    install_dir,
    owner_id: effectiveOwnerId,
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

// Repository/slot names are aliases. The dedicated server must see only its
// own stable profile name, regardless of the imported world's original name.
function profileSaveName(world) {
  let stem = String(world.display_name || "").trim().replace(/[\\/:*?"<>|\x00-\x1f]/g, "_").replace(/[. ]+$/g, "").slice(0, 120);
  if (!stem) throw new Error("Give this Server profile a name before selecting a world save");
  if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i.test(stem)) stem = `_${stem}`;
  return `${stem}.sav`;
}

function isWorldSaveName(name) {
  return /\.sav$/i.test(name) && !/^EnhancedInputUserSettings\.sav$/i.test(name);
}

function activeSaveKey(worldId) {
  return `activeWorldSave:${worldId}`;
}

function fileDigest(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function liveSaveEntries(world) {
  try {
    return fs.readdirSync(saveGamesDir(world), { withFileTypes: true })
      .filter((entry) => entry.isFile() && isWorldSaveName(entry.name))
      .map((entry) => {
        const filePath = path.join(saveGamesDir(world), entry.name);
        return { name: entry.name, path: filePath, stat: fs.statSync(filePath) };
      })
      .sort((a, b) => b.stat.mtimeMs - a.stat.mtimeMs);
  } catch {
    return [];
  }
}

function captureActiveSaves(world) {
  const vault = P.worldSaveSlots(world.world_id);
  const entries = liveSaveEntries(world);
  const selection = dbm.getSetting(activeSaveKey(world.world_id), null);
  const selected = selection?.name?.toLowerCase();
  const currentName = selected && entries.some((entry) => entry.name.toLowerCase() === selected)
    ? selected
    : entries[0]?.name?.toLowerCase();
  for (const entry of entries) {
    const isCurrent = entry.name.toLowerCase() === currentName;
    const alias = isCurrent && selected === currentName ? selection?.slotName || entry.name : entry.name;
    const destination = path.join(vault, safeSaveName(alias));
    // The game loads the newest save. Refresh that slot on every clean stop so
    // progress made since the previous activation is not lost. Legacy folders
    // may contain several saves; retain those without overwriting their vault
    // copies unless they are the explicitly selected slot.
    if (isCurrent || !fs.existsSync(destination)) fs.copyFileSync(entry.path, destination);
  }
}

function listSaveSlots(worldId) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  // Reading this tab must not synchronously copy a large save while the game
  // may be writing it. Capture the final copy once the process is down.
  if (!require("./supervisor").isAlive(worldId)) captureActiveSaves(world);
  const live = liveSaveEntries(world);
  const selection = dbm.getSetting(activeSaveKey(worldId), null);
  const selected = selection?.name?.toLowerCase();
  // Existing installs may predate slot state. Dragonwilds loads the newest file,
  // so represent only that file as active instead of marking every .sav active.
  const activeName = selected
    ? (live.some((entry) => entry.name.toLowerCase() === selected) ? (selection.slotName || selection.name).toLowerCase() : null)
    : live[0]?.name?.toLowerCase();
  const vault = P.worldSaveSlots(worldId);
  return fs.readdirSync(vault, { withFileTypes: true })
    .filter((entry) => entry.isFile() && isWorldSaveName(entry.name))
    .map((entry) => {
      const stat = fs.statSync(path.join(vault, entry.name));
      return { name: entry.name, size: stat.size, modifiedAt: stat.mtimeMs, active: entry.name.toLowerCase() === activeName };
    })
    .sort((a, b) => Number(b.active) - Number(a.active) || b.modifiedAt - a.modifiedAt);
}

function removeSaveSlot(worldId, slotName) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const name = safeSaveName(slotName);
  const slot = listSaveSlots(worldId).find((item) => item.name === name);
  if (!slot) throw new Error("Save alias not found");
  if (slot.active || dbm.getSetting(activeSaveKey(worldId), null)?.slotName === name) {
    throw new Error("The active world cannot be deleted. Activate a different world first.");
  }
  if (require("./supervisor").pendingWorldSave(worldId)?.slotName === name) {
    throw new Error("This world is queued for the next server start. Select a different world first.");
  }
  trashPath(path.join(P.worldSaveSlots(worldId), name));
  dbm.logEvent(worldId, "import", `Removed saved world alias ${name} to the OS trash`);
  return { name, recoverable: true };
}

function verifyActiveSaveSlot(worldId, slotName) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const alias = safeSaveName(slotName);
  const activeSave = profileSaveName(world);
  const sourceFile = path.join(P.worldSaveSlots(worldId), alias);
  if (!fs.existsSync(sourceFile)) throw new Error("Save slot not found");
  const live = liveSaveEntries(world);
  if (live.length !== 1 || live[0].name.toLowerCase() !== activeSave.toLowerCase()) {
    throw new Error(`World activation verification failed: expected only ${activeSave} in SaveGames, found ${live.map((entry) => entry.name).join(", ") || "no saves"}`);
  }
  const expectedSize = fs.statSync(sourceFile).size;
  const actualSize = live[0].stat.size;
  const expectedSha256 = fileDigest(sourceFile);
  const actualSha256 = fileDigest(live[0].path);
  if (expectedSize !== actualSize || expectedSha256 !== actualSha256) {
    throw new Error(`World activation verification failed: ${activeSave} did not copy intact`);
  }
  return { activeSave, slotName: alias, size: actualSize, sha256: actualSha256, path: live[0].path };
}

// Once a server profile has an explicitly selected save, every subsequent
// launch must still point at that save. A missing or second .sav would let the
// game create/load a different world, so fail closed before spawning it.
function assertSelectedSaveReady(worldId) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const selected = dbm.getSetting(activeSaveKey(worldId), null)?.name;
  if (!selected) return null; // Existing unmanaged servers keep their legacy behavior.
  const activeSave = safeSaveName(selected);
  const live = liveSaveEntries(world);
  if (live.length !== 1 || live[0].name.toLowerCase() !== activeSave.toLowerCase()) {
    throw new Error(`Selected world save ${activeSave} is not the only .sav in SaveGames. Open Server Settings → World save to activate it again before starting.`);
  }
  if (!live[0].stat.size) throw new Error(`Selected world save ${activeSave} is empty; server start was blocked to prevent a Standard world.`);
  if (dbm.getSetting(activeSaveKey(worldId), null)?.slotName) {
    if (activeSave.toLowerCase() !== profileSaveName(world).toLowerCase()) {
      throw new Error(`This profile was renamed. Re-activate its world save so SaveGames uses ${profileSaveName(world)} before starting.`);
    }
    if (world.default_world_name !== path.basename(activeSave, ".sav")) {
      throw new Error(`DefaultWorldName must match ${activeSave}. Re-activate the selected world before starting.`);
    }
  }
  return { activeSave, size: live[0].stat.size, path: live[0].path };
}

function moveDirectory(source, destination) {
  try {
    fs.renameSync(source, destination);
    return;
  } catch (error) {
    if (error.code !== "EPERM" && error.code !== "EXDEV") throw error;
  }
  // Windows package redirection and cross-volume server storage can reject an
  // otherwise valid directory rename. The server is stopped for this entire
  // operation, so copy + remove is a safe compatibility fallback; verification
  // and rollback still run before any launch is allowed.
  copyDir(source, destination);
  fs.rmSync(source, { recursive: true, force: true });
}

// Replace only Saved/SaveGames. Config, passwords, owner identity, ports and the
// selected Server profile remain untouched. The directory swap ensures the game
// never sees a half-copied world.
async function activateSaveSlot(worldId, slotName, { backupFirst = true } = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  if (require("./supervisor").isAlive(worldId)) throw new Error("Stop the server before replacing its world save");
  const alias = safeSaveName(slotName);
  const activeSave = profileSaveName(world);
  const sourceFile = path.join(P.worldSaveSlots(worldId), alias);
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
  const priorSelection = dbm.getSetting(activeSaveKey(worldId), null);
  const priorWorldName = world.default_world_name;
  const destination = path.join(incoming, activeSave);

  try {
    fs.mkdirSync(incoming, { recursive: true });
    // Keep game-owned non-world data, including EnhancedInputUserSettings.sav.
    // Other world saves stay recoverable in the vault and pre-swap backup.
    if (fs.existsSync(saveGames)) {
      for (const entry of fs.readdirSync(saveGames, { withFileTypes: true })) {
        if (isWorldSaveName(entry.name) || entry.isSymbolicLink()) continue;
        const from = path.join(saveGames, entry.name);
        const to = path.join(incoming, entry.name);
        if (entry.isDirectory()) fs.cpSync(from, to, { recursive: true });
        else if (entry.isFile()) fs.copyFileSync(from, to);
      }
    }
    fs.copyFileSync(sourceFile, destination);
    if (fs.statSync(sourceFile).size !== fs.statSync(destination).size || fileDigest(sourceFile) !== fileDigest(destination)) {
      throw new Error(`Could not verify staged world save ${activeSave}`);
    }
    const now = new Date();
    fs.utimesSync(destination, now, now);

    if (fs.existsSync(saveGames)) moveDirectory(saveGames, previous);
    try {
      moveDirectory(incoming, saveGames);
    } catch (error) {
      if (fs.existsSync(previous) && !fs.existsSync(saveGames)) moveDirectory(previous, saveGames);
      throw error;
    }
    try {
      const verified = verifyActiveSaveSlot(worldId, alias);
      // Dragonwilds also uses DefaultWorldName when choosing a save. Keeping
      // the old name can make a correctly copied file appear to be ignored.
      dbm.updateWorld(worldId, { default_world_name: path.basename(activeSave, path.extname(activeSave)) });
      dbm.setSetting(activeSaveKey(worldId), { schema: 2, name: activeSave, slotName: alias, ...verified, activatedAt: Date.now() });
    } catch (error) {
      fs.rmSync(saveGames, { recursive: true, force: true });
      if (fs.existsSync(previous)) moveDirectory(previous, saveGames);
      try {
        dbm.updateWorld(worldId, { default_world_name: priorWorldName });
        dbm.setSetting(activeSaveKey(worldId), priorSelection);
      } catch {}
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

  serverProfiles.materializeActiveBestEffort(worldId);
  dbm.logEvent(worldId, "import", `Activated world save alias ${alias} as ${activeSave}; Server profile identity retained`);
  return { valid: true, activeSave, slotName: alias, slots: listSaveSlots(worldId) };
}

function stageSaveSlot(worldId, sourcePath) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const check = validateSaveSource(sourcePath);
  captureActiveSaves(world);
  const destination = path.join(P.worldSaveSlots(worldId), safeSaveName(check.activeSave));
  const temporary = `${destination}.incoming-${crypto.randomUUID()}`;
  try {
    if (check.kind === "sav") fs.copyFileSync(sourcePath, temporary);
    else {
      const entry = new AdmZip(sourcePath).getEntry(check.entryName);
      if (!entry) throw new Error("The selected save disappeared from its archive");
      fs.writeFileSync(temporary, entry.getData());
    }
    if (!fs.statSync(temporary).size) throw new Error("The selected world save is empty");
    // Packaged Windows apps can reject file renames inside their redirected
    // LocalAppData sandbox even on the same volume. The vault is not live game
    // state, so a verified copy is safe here; the live SaveGames swap below
    // remains an atomic directory rename with rollback.
    fs.copyFileSync(temporary, destination);
    if (fs.statSync(temporary).size !== fs.statSync(destination).size || fileDigest(temporary) !== fileDigest(destination)) {
      throw new Error(`Could not verify imported world save ${check.activeSave}`);
    }
    fs.rmSync(temporary, { force: true });
  } catch (error) {
    fs.rmSync(temporary, { force: true });
    throw error;
  }
  return { ...check, slotName: check.activeSave };
}

function stageRepositorySave(worldId, repositoryId) {
  if (!dbm.getWorld(worldId)) throw new Error("World not found");
  const item = require("./world-repository").getWorld(repositoryId);
  const vault = P.worldSaveSlots(worldId);
  const original = safeSaveName(item.name);
  const stem = path.basename(original, path.extname(original));
  const existing = path.join(vault, original);
  const slotName = fs.existsSync(existing) && fileDigest(existing) !== item.sha256
    ? safeSaveName(`${stem}-${item.id.slice(0, 8)}.sav`)
    : original;
  const destination = path.join(vault, slotName);
  const temporary = `${destination}.incoming-${crypto.randomUUID()}`;
  try {
    fs.copyFileSync(item.file, temporary);
    if (fileDigest(temporary) !== item.sha256) throw new Error("Repository copy failed verification");
    fs.copyFileSync(temporary, destination);
    if (fileDigest(destination) !== item.sha256) throw new Error("Server save slot failed verification");
  } finally { fs.rmSync(temporary, { force: true }); }
  return { slotName, repositoryId: item.id, worldType: item.worldType };
}

async function importSave(worldId, sourcePath, { backupFirst = true } = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  if (require("./supervisor").isAlive(worldId)) throw new Error("Stop the server before replacing its world save");
  const check = stageSaveSlot(worldId, sourcePath);
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
  validateSaveSource, validateSaveZip: validateSaveSource, stageSaveSlot, importSave,
  stageRepositorySave, listSaveSlots, activateSaveSlot, verifyActiveSaveSlot, assertSelectedSaveReady, copyDir,
  profileSaveName,
  removeSaveSlot,
};
