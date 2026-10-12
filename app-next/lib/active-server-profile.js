const fs = require("fs");
const path = require("path");
const dbm = require("./db");
const ini = require("./ini");

const SETTING_KEY = "activeServerWorldId";
const PROFILE_PREFIX = "serverProfileIni:";
const WORLD_SETTING_FIELDS = new Map([
  ["AdminPassword", "admin_password"],
  ["WorldPassword", "server_password"],
  ["OwnerId", "owner_id"],
  ["ServerName", "display_name"],
  ["DefaultWorldName", "default_world_name"],
]);

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
function unquote(value) {
  const text = value == null ? "" : String(value);
  if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
    return text.slice(1, -1);
  }
  return text;
}
function isWorldManagedSetting(key) {
  return WORLD_SETTING_FIELDS.has(String(key));
}
function updateWorldFromSettings(worldOrId, values) {
  const world = worldOf(worldOrId);
  const patch = {};
  for (const [iniKey, column] of WORLD_SETTING_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(values || {}, iniKey)) continue;
    const value = unquote(values[iniKey]);
    if (iniKey === "ServerName") {
      const name = value.trim();
      if (!name) {
        const error = new Error("Server name cannot be blank.");
        error.statusCode = 400;
        throw error;
      }
      patch[column] = name;
    } else if (iniKey === "OwnerId" || iniKey === "DefaultWorldName") {
      patch[column] = value.trim() || null;
    } else {
      patch[column] = value;
    }
  }
  return Object.keys(patch).length ? dbm.updateWorld(world.world_id, patch) : world;
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

// Editing a profile is a durable database operation. Mirroring an active profile
// into the shared game tree is best-effort here; launch performs the strict write
// and read-back gate. A locked/missing install must never turn a successful profile
// save into HTTP 500 or make the editor discard the user's content.
function materializeActiveBestEffort(worldOrId, opts = {}) {
  const world = worldOf(worldOrId);
  if (readActiveId() !== world.world_id) return { active: false, warning: null };
  if (!world.install_dir || !fs.existsSync(world.install_dir)) {
    return {
      active: true,
      warning: "Profile saved. The server install folder is unavailable, so DedicatedServer.ini will be written at the next launch.",
    };
  }
  try {
    materialize(world, opts);
    return { active: true, warning: null };
  } catch (error) {
    return {
      active: true,
      warning: `Profile saved, but the live DedicatedServer.ini could not be updated and will be retried at launch: ${error.message}`,
    };
  }
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
  isWorldManagedSetting,
  updateWorldFromSettings,
  materialize,
  materializeActiveBestEffort,
  activate,
  markerPath,
  profileKey,
};
