const fs = require("fs");
const path = require("path");
const dbm = require("./db");
const ini = require("./ini");

const SETTING_KEY = "activeServerWorldId";
const PROFILE_PREFIX = "serverProfileIni:";

function markerPath(world) {
  return path.join(world.install_dir, "RSDragonwilds", "activeworld.txt");
}
function profileKey(worldId) {
  return PROFILE_PREFIX + String(worldId);
}
function liveSettingsPath(world) {
  return world.install_dir ? ini.settingsIniPath(world.install_dir, world.platform) : null;
}
function readActiveId() {
  const id = String(dbm.getSetting(SETTING_KEY, "") || "").trim();
  return id && dbm.getWorld(id) ? id : null;
}
function worldOf(worldOrId) {
  if (worldOrId && typeof worldOrId === "object") return worldOrId;
  const world = dbm.getWorld(String(worldOrId || ""));
  if (!world) throw new Error("Server profile not found");
  return world;
}
function normalizeRecord(world, raw, opts = {}) {
  const values = ini.withWorldNetworkSettings(ini.parseOptionSettings(raw), world, opts);
  return { content: ini.patchRawSettings(raw, values), values };
}

// DedicatedServer.ini on disk is a launch target, not the profile database.
// Each Server profile keeps its own raw snapshot so editing one World cannot
// silently inherit settings written by another profile or by a previous launch.
function settingsFor(worldOrId) {
  const world = worldOf(worldOrId);
  const stored = dbm.getSetting(profileKey(world.world_id), null);
  let raw = "";
  let existed = false;

  if (stored && typeof stored === "object" && typeof stored.raw === "string") {
    raw = stored.raw;
    existed = true;
  } else if (typeof stored === "string") {
    // Early experimental builds may have stored the profile text directly.
    raw = stored;
    existed = true;
  } else {
    // Lazy migration: capture the legacy live file once, then stop treating it
    // as this profile's source of truth.
    if (world.install_dir) {
      const disk = ini.readRawSettings(world.install_dir, world.platform);
      raw = disk.content || "";
      existed = disk.exists;
    }
  }

  const normalized = normalizeRecord(world, raw);
  dbm.setSetting(profileKey(world.world_id), { schema: 1, raw: normalized.content });
  return {
    path: liveSettingsPath(world),
    exists: existed || !!normalized.content,
    content: normalized.content,
    values: normalized.values,
  };
}

function saveSettings(worldId, options, { baseRaw = null, syncPublicPort = false } = {}) {
  const world = worldOf(worldId);
  const current = settingsFor(world);
  const values = ini.withWorldNetworkSettings(options || {}, world, { syncPublicPort });
  const content = ini.patchRawSettings(baseRaw == null ? current.content : baseRaw, values);
  dbm.setSetting(profileKey(world.world_id), { schema: 1, raw: content });
  return { path: current.path, exists: true, content, values };
}

function saveRawSettings(worldId, raw, { syncPublicPort = false } = {}) {
  const world = worldOf(worldId);
  const values = ini.withWorldNetworkSettings(ini.parseOptionSettings(raw), world, { syncPublicPort });
  const content = ini.patchRawSettings(raw, values);
  dbm.setSetting(profileKey(world.world_id), { schema: 1, raw: content });
  return {
    path: liveSettingsPath(world),
    exists: true,
    content,
    values,
  };
}

// Materialization is the only place the profile snapshot is pushed into the
// game's live DedicatedServer.ini. startWorld() calls activate() immediately
// before spawning the dedicated server, so launch always receives the saved
// World identity and settings.
function materialize(worldOrId, opts = {}) {
  const world = worldOf(worldOrId);
  const ownerId = String(world.owner_id || "").trim();
  if (!ownerId) {
    throw new Error("Owner ID is required before this Server profile can start. Copy your Player ID from Dragonwilds Settings and save it in the Server profile.");
  }
  const current = settingsFor(world);
  const values = ini.withWorldNetworkSettings(current.values, world, opts);
  const content = ini.patchRawSettings(current.content, values);
  dbm.setSetting(profileKey(world.world_id), { schema: 1, raw: content });
  ini.writeRawSettings(world.install_dir, content, world.platform);
  const persisted = ini.readSettings(world.install_dir, world.platform).options;
  const savedOwnerId = Object.entries(persisted).find(([key]) => key.toLowerCase() === "ownerid")?.[1] ?? "";
  if (savedOwnerId !== ownerId) {
    throw new Error(`Owner ID could not be verified in ${ini.settingsIniPath(world.install_dir, world.platform)}. Check folder permissions or security software, then try again.`);
  }
  return {
    path: ini.settingsIniPath(world.install_dir, world.platform),
    content,
    values,
  };
}

function writeMarker(world) {
  const target = markerPath(world);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const temporary = `${target}.dwsync.tmp`;
  fs.writeFileSync(temporary, JSON.stringify({
    profile_id: world.world_id,
    world_type: "dedicated",
    selected_at: Date.now() / 1000,
    managed_by: "RSDW Sync",
  }, null, 2) + "\n", "utf8");
  fs.renameSync(temporary, target);
  return target;
}

function activate(worldId) {
  const world = worldOf(worldId);
  if (!String(world.owner_id || "").trim()) {
    throw new Error("Owner ID is required before this Server profile can start. Copy your Player ID from Dragonwilds Settings and save it in the Server profile.");
  }
  const sup = require("./supervisor");
  const runningOther = dbm.listWorlds().find((candidate) =>
    candidate.world_id !== world.world_id &&
    (sup.isRunning(candidate.world_id) || sup.pidAlive(candidate.process_id))
  );
  if (runningOther) {
    throw new Error(`Stop ${runningOther.display_name} before activating another Server profile.`);
  }

  const profileSettings = materialize(world);
  const marker = writeMarker(world);
  dbm.setSetting(SETTING_KEY, world.world_id);
  dbm.logEvent(world.world_id, "settings", "Activated Server profile and materialized its dedicated server settings");
  return { world: dbm.getWorld(world.world_id), profileSettings, marker };
}

module.exports = {
  readActiveId,
  settingsFor,
  saveSettings,
  saveRawSettings,
  materialize,
  activate,
  markerPath,
  profileKey,
};
