const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-save-slots-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const provision = require("../lib/provision");

(async () => {
  const worldId = "save-slot-test";
  const install = path.join(sandbox, "server");
  const saves = path.join(install, "RSDragonwilds", "Saved", "SaveGames");
  const config = path.join(install, "RSDragonwilds", "Saved", "Config", "WindowsServer", "DedicatedServer.ini");
  fs.mkdirSync(saves, { recursive: true });
  fs.mkdirSync(path.dirname(config), { recursive: true });
  fs.writeFileSync(config, "AdminPassword=keep-admin\nWorldPassword=keep-login\nOwnerId=keep-owner\n");
  fs.writeFileSync(path.join(saves, "original.sav"), "original-world");
  const incoming = path.join(sandbox, "friends-world.sav");
  fs.writeFileSync(incoming, "friends-world");
  dbm.insertWorld({
    world_id: worldId, display_name: "Friends", install_dir: install, platform: "windows",
    env_vars: "{}", wine_binary: "wine", wine_prefix: null, wine_launch_flags: "",
    game_port: 7777, query_port: 27015, rest_api_port: 7778, rcon_port: 25575,
    admin_password: "keep-admin", rest_api_enabled: 1, owner_id: "keep-owner",
    default_world_name: "keep-world", status: "stopped", autostart: 0, crash_guard: 1,
    build_id: null, extra_args: "", created_at: Date.now(),
  });
  dbm.updateWorld(worldId, { server_password: "keep-login" });

  let result = await provision.importSave(worldId, incoming, { backupFirst: false });
  assert.equal(result.activeSave, "friends-world.sav");
  assert.equal(fs.readFileSync(path.join(saves, "friends-world.sav"), "utf8"), "friends-world");
  assert(result.slots.some((slot) => slot.name === "original.sav"), "original world was not retained as a save slot");

  result = await provision.activateSaveSlot(worldId, "original.sav", { backupFirst: false });
  assert.equal(fs.readFileSync(path.join(saves, "original.sav"), "utf8"), "original-world");
  const world = dbm.getWorld(worldId);
  assert.equal(world.admin_password, "keep-admin");
  assert.equal(world.server_password, "keep-login");
  assert.equal(world.owner_id, "keep-owner");
  assert.equal(world.default_world_name, "keep-world");
  assert.match(fs.readFileSync(config, "utf8"), /WorldPassword=keep-login/, "save-slot swap changed the server login configuration");
  console.log("World save slots: OK");
})().finally(() => {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
