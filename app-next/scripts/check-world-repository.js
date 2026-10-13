const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-world-repository-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const repository = require("../lib/world-repository");
const supervisor = require("../lib/supervisor");
const provision = require("../lib/provision");

function saveFixture(name, mode) {
  const file = path.join(sandbox, name);
  const data = Buffer.alloc(128);
  data.write("SAVE", 0, "ascii");
  data.write("L_World\0", 32, "ascii");
  data.writeUInt32LE(mode, 41);
  data.write(name, 60, "ascii");
  fs.writeFileSync(file, data);
  return file;
}

function world(id) {
  const install = path.join(sandbox, id);
  const saves = path.join(install, "RSDragonwilds", "Saved", "SaveGames");
  fs.mkdirSync(saves, { recursive: true });
  dbm.insertWorld({
    world_id: id, display_name: id, install_dir: install, platform: "windows",
    env_vars: "{}", wine_binary: "wine", wine_prefix: null, wine_launch_flags: "",
    game_port: 7777, query_port: 27015, rest_api_port: 7778, rcon_port: 25575,
    admin_password: "admin", rest_api_enabled: 0, owner_id: "owner",
    default_world_name: "old-name", status: "stopped", autostart: 0, crash_guard: 0,
    build_id: null, extra_args: "", created_at: Date.now(),
  });
  dbm.updateWorld(id, { server_password: "keep-login" });
  return saves;
}

(async () => {
  const standard = repository.importWorld(saveFixture("Standard.sav", 0));
  const hard = repository.importWorld(saveFixture("Hard.sav", 1));
  const custom = repository.importWorld(saveFixture("Custom.sav", 3));
  const unknown = repository.importWorld(saveFixture("Unknown.sav", 2));
  assert.equal(standard.worldType, "Standard");
  assert.equal(hard.worldType, "HardMode");
  assert.equal(custom.worldType, "Custom");
  assert.equal(unknown.worldType, null, "Unknown mode must not be guessed as Creative");
  assert.equal(repository.setWorldType(unknown.id, "Creative").typeSource, "manual");
  assert.equal(repository.listWorlds().length, 4);
  assert.equal(repository.importWorld(path.join(sandbox, "Standard.sav")).id, standard.id, "identical saves should deduplicate");
  const sameName = repository.importWorld(saveFixture("Standard.sav", 3));
  assert.notEqual(sameName.id, standard.id, "distinct saves with the same filename must remain separate repository items");
  assert.throws(() => repository.importWorld(path.join(sandbox, "missing.sav")), /not found/);

  const savesA = world("server-a");
  const savesB = world("server-b");
  const first = await supervisor.selectWorldSave("server-a", { repositoryId: standard.id });
  assert.equal(first.queued, false);
  assert.deepStrictEqual(fs.readdirSync(savesA).filter((name) => name.endsWith(".sav")), ["Standard.sav"]);
  assert.equal(dbm.getWorld("server-a").default_world_name, "Standard");
  assert.equal(dbm.getWorld("server-a").server_password, "keep-login");
  assert.equal(provision.assertSelectedSaveReady("server-a").activeSave, "Standard.sav");

  // A live process must not be stopped, restarted, or have its SaveGames changed.
  dbm.updateWorld("server-a", { process_id: process.pid, status: "running" });
  const queued = await supervisor.selectWorldSave("server-a", { repositoryId: custom.id });
  assert.equal(queued.queued, true);
  assert.equal(queued.restarted, false);
  assert.deepStrictEqual(fs.readdirSync(savesA).filter((name) => name.endsWith(".sav")), ["Standard.sav"]);
  assert.equal(dbm.getWorld("server-a").default_world_name, "Standard");
  assert.equal(supervisor.pendingWorldSave("server-a").repositoryId, custom.id);

  dbm.updateWorld("server-a", { process_id: null, status: "stopped" });
  await supervisor.stopWorld("server-a", { graceful: false });
  assert.deepStrictEqual(fs.readdirSync(savesA).filter((name) => name.endsWith(".sav")), ["Custom.sav"]);
  assert.equal(dbm.getWorld("server-a").default_world_name, "Custom");
  assert.equal(supervisor.pendingWorldSave("server-a"), null);
  assert.equal(provision.assertSelectedSaveReady("server-a").activeSave, "Custom.sav");

  await supervisor.selectWorldSave("server-b", { repositoryId: standard.id });
  assert.deepStrictEqual(fs.readdirSync(savesB).filter((name) => name.endsWith(".sav")), ["Standard.sav"]);
  const sameNameSelection = await supervisor.selectWorldSave("server-b", { repositoryId: sameName.id });
  assert.equal(sameNameSelection.activeSave, `Standard-${sameName.id.slice(0, 8)}.sav`);
  assert(fs.existsSync(path.join(process.env.APP_MANAGER_DATA_DIR, "save-slots", "server-b", "Standard.sav")), "original same-named slot was lost");
  assert.deepStrictEqual(fs.readdirSync(savesB).filter((name) => name.endsWith(".sav")), [sameNameSelection.activeSave]);
  assert.deepStrictEqual(fs.readdirSync(savesA).filter((name) => name.endsWith(".sav")), ["Custom.sav"], "server profiles must retain independent saves");
  console.log("World Repository and no-restart swap: OK");
})().finally(() => {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
