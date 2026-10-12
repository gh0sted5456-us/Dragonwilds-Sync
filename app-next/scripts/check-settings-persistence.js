const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-settings-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");

const dbm = require("../lib/db");
const ini = require("../lib/ini");
const active = require("../lib/active-server-profile");

try {
  const worldId = "settings-persistence-test";
  dbm.insertWorld({
    world_id: worldId,
    display_name: "Before",
    install_dir: path.join(sandbox, "missing-install"),
    platform: "windows",
    env_vars: "{}",
    wine_binary: "wine",
    wine_prefix: null,
    wine_launch_flags: "",
    game_port: 7777,
    query_port: 27015,
    rest_api_port: 7778,
    rcon_port: 25575,
    admin_password: "old-admin",
    rest_api_enabled: 1,
    owner_id: null,
    default_world_name: null,
    status: "stopped",
    autostart: 0,
    crash_guard: 1,
    build_id: null,
    extra_args: "",
    created_at: Date.now(),
  });

  const updated = active.updateWorldFromSettings(worldId, {
    OwnerId: '"owner-123"',
    ServerName: '"After"',
    DefaultWorldName: '"Persistent World"',
    AdminPassword: '"new-admin"',
    WorldPassword: '"new-world"',
  });
  assert.equal(updated.owner_id, "owner-123");
  assert.equal(updated.display_name, "After");
  assert.equal(updated.default_world_name, "Persistent World");
  assert.equal(updated.admin_password, "new-admin");
  assert.equal(updated.server_password, "new-world");
  const autoUpdated = dbm.updateWorld(worldId, { auto_update: 1 });
  assert.equal(autoUpdated.auto_update, 1, "per-server automatic update preference did not persist");

  const raw = [
    "[/Script/Dominion.DedicatedServerSettings]",
    "OwnerId=raw-owner",
    'ServerName="Raw Server"',
    'DefaultWorldName="Raw World"',
    "AdminPassword=raw-admin",
    "WorldPassword=raw-password",
    "CustomSetting=keep-me",
    "",
  ].join("\n");
  const rawWorld = active.updateWorldFromSettings(updated, ini.parseOptionSettings(raw));
  const saved = active.saveRawSettings(worldId, raw);
  const parsed = ini.parseOptionSettings(saved.content);
  assert.equal(rawWorld.owner_id, "raw-owner");
  assert.equal(rawWorld.default_world_name, "Raw World");
  assert.equal(parsed.OwnerId, "raw-owner");
  assert.equal(parsed.ServerName, "Raw Server");
  assert.equal(parsed.DefaultWorldName, "Raw World");
  assert.equal(parsed.CustomSetting, "keep-me");

  dbm.setSetting("activeServerWorldId", worldId);
  const materialized = active.materializeActiveBestEffort(rawWorld);
  assert.equal(materialized.active, true);
  assert.match(materialized.warning, /Profile saved/);

  console.log("Settings persistence: OK");
} finally {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
}
