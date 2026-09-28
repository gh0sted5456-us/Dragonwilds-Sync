const fs = require("fs");
const path = require("path");
const dbm = require("./db");
const ini = require("./ini");

const SETTING_KEY = "activeServerWorldId";

function markerPath(world) {
  return path.join(world.install_dir, "RSDragonwilds", "activeworld.txt");
}

function readActiveId() {
  const id = String(dbm.getSetting(SETTING_KEY, "") || "").trim();
  return id && dbm.getWorld(id) ? id : null;
}

function settingsFor(world) {
  const read = ini.readSettings(world.install_dir, world.platform);
  return { path: read.path, exists: read.exists, values: read.options };
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
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("Server profile not found");
  const sup = require("./supervisor");
  const runningOther = dbm.listWorlds().find((candidate) => candidate.world_id !== worldId && (sup.isRunning(candidate.world_id) || sup.pidAlive(candidate.process_id)));
  if (runningOther) throw new Error(`Stop ${runningOther.display_name} before activating another Server profile.`);
  const diskSettings = settingsFor(world);
  ini.applyWorldNetworkSettings(world.install_dir, world);
  const marker = writeMarker(world);
  dbm.setSetting(SETTING_KEY, worldId);
  dbm.logEvent(worldId, "settings", "Activated Server profile and loaded its dedicated server settings");
  return { world: dbm.getWorld(worldId), diskSettings, marker };
}

module.exports = { readActiveId, settingsFor, activate, markerPath };
