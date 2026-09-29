// lib/provision.js  (spec §2 provisioning, §3 import, §8 update, duplicate)
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const AdmZip = require("adm-zip");
const { P } = require("./paths");
const dbm = require("./db");
const ini = require("./ini");
const serverProfiles = require("./active-server-profile");
const { suggestPorts } = require("./ports");
const { createBackup } = require("./backups");
const os = require("os");

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
function validateSaveZip(zipPath) {
  const zip = new AdmZip(zipPath);
  const entries = zip.getEntries().map((e) => e.entryName.replace(/\\/g, "/"));
  const hasIni = entries.some((e) => /Config\/(Windows|Linux)Server\/DedicatedServer\.ini$/i.test(e));
  const hasLevel = entries.some((e) => /SaveGames\/.+\/Level\.sav$/i.test(e));
  const players = entries.filter((e) => /SaveGames\/.+\/Players\/.+\.sav$/i.test(e));
  const worldGuid = (() => {
    const m = entries.find((e) => /SaveGames\/[^/]+\/([^/]+)\/Level\.sav$/i.test(e));
    return m ? m.match(/SaveGames\/[^/]+\/([^/]+)\/Level\.sav$/i)[1] : null;
  })();
  return { valid: hasLevel || hasIni, hasIni, hasLevel, playerCount: players.length, worldGuid, entries };
}

// Import a validated save zip into a world's Saved folder.
async function importSave(worldId, zipPath, { backupFirst = true } = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const check = validateSaveZip(zipPath);
  if (!check.valid) throw new Error("Zip does not contain a recognizable Dragonwilds save (no Level.sav / settings ini)");

  const saved = path.join(world.install_dir, "RSDragonwilds", "Saved");
  if (backupFirst && fs.existsSync(saved)) {
    try { await createBackup(worldId, "pre-import-safety"); } catch {}
  }

  // extract to staging first
  const stage = path.join(P.staging(), crypto.randomUUID());
  fs.mkdirSync(stage, { recursive: true });
  new AdmZip(zipPath).extractAllTo(stage, true);

  // find the Saved root inside staging (zip may wrap it)
  const savedRoot = findSavedRoot(stage);
  if (!savedRoot) { fs.rmSync(stage, { recursive: true, force: true }); throw new Error("Could not locate Saved contents in archive"); }

  if (fs.existsSync(saved)) fs.rmSync(saved, { recursive: true, force: true });
  fs.mkdirSync(saved, { recursive: true });
  copyDir(savedRoot, saved);
  fs.rmSync(stage, { recursive: true, force: true });

  // Re-apply identity, then make the imported settings the selected profile's
  // durable snapshot before another Server profile can be materialized.
  ini.applyWorldNetworkSettings(world.install_dir, world, { syncPublicPort: true });
  serverProfiles.saveRawSettings(
    worldId,
    ini.readRawSettings(world.install_dir, world.platform).content,
    { syncPublicPort: true }
  );
  dbm.logEvent(worldId, "import", `Imported save (${check.playerCount} players, guid ${check.worldGuid || "?"})`);
  return check;
}

function findSavedRoot(dir) {
  // Look for a folder that directly contains "SaveGames" or "Config".
  const stack = [dir];
  while (stack.length) {
    const d = stack.pop();
    const items = fs.readdirSync(d, { withFileTypes: true });
    const names = items.filter((i) => i.isDirectory()).map((i) => i.name);
    if (names.includes("SaveGames") || names.includes("Config")) return d;
    for (const n of names) stack.push(path.join(d, n));
  }
  return null;
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
  validateSaveZip, importSave, copyDir,
};
