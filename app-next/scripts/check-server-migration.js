const assert = require("assert");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const sandbox = fs.mkdtempSync(path.join(__dirname, "..", ".rsdw-server-migration-test-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const forks = require("../lib/server-forks");
const migration = require("../lib/server-migration");
const provision = require("../lib/provision");
const ini = require("../lib/ini");
const sup = require("../lib/supervisor");
const processGuard = require("../lib/server-process-guard");
const realGuard = processGuard.assertNoConflictingServer;
const realProcesses = processGuard.runningServerProcesses;
const realAlive = sup.isAlive;
const realCopy = fs.promises.copyFile;
const realUpdate = dbm.updateWorld;
let guardCalls = 0;
// No real game process or live launcher state is touched by these fixtures.
processGuard.assertNoConflictingServer = () => { guardCalls++; };
processGuard.runningServerProcesses = () => [];

function write(root, relative, value) {
  const file = path.join(root, relative);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, value);
  return file;
}
function fixture(name) {
  const root = path.join(sandbox, name);
  write(root, "RSDragonwildsServer.exe", "fixture executable");
  write(root, "RSDragonwilds/Binaries/Win64/fixture.exe", "fixture shipping");
  write(root, "RSDragonwilds/Content/Paks/base.pak", "fixture assets");
  write(root, "steamapps/appmanifest_4019830.acf", '"buildid" "100"');
  return root;
}
function profile(root, name) {
  return provision.createProfile({ world_id: crypto.randomUUID(), display_name: name, install_dir: root, platform: "windows", owner_id: "profile-owner", admin_password: "profile-admin" });
}
function review(id) { return { ...migration.plan(id), confirm: true }; }
function snapshots(root) {
  const result = {};
  function visit(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) visit(file);
      else result[path.relative(root, file)] = crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
    }
  }
  visit(root);
  return result;
}

async function main() {
  const core = fixture("Core");
  dbm.setSetting("applicationSetup:serverDir", core);
  const old = fixture("old-server-profiles/Legacy");
  const world = profile(old, "Legacy");
  const id = world.world_id;
  const save = write(old, "RSDragonwilds/Saved/SaveGames/Legacy.sav", "world identity and player buildings");
  const player = write(old, "RSDragonwilds/Saved/SaveGames/player.sav", "player inventory");
  const mod = write(old, "RSDragonwilds/Binaries/Win64/ue4ss/Mods/RuneSchema/mods/Test/main.lua", "return true");
  write(old, "RSDragonwilds/Binaries/Win64/ue4ss/Mods/mods.txt", "RuneSchema : 1\n");
  write(old, "RSDragonwilds/Binaries/Win64/ue4ss/Mods/RuneSchema/runeschema.txt", "Test : 1\n");
  const raw = "[/Script/Dominion.DedicatedServerSettings]\nServerGuid=original-guid\nOwnerId=ini-owner\nAdminPassword=ini-admin\nWorldPassword=ini-world-password\nDefaultWorldName=Legacy\nServerName=Legacy\n";
  write(old, path.relative(old, ini.settingsIniPath(old, "windows")), raw);
  write(old, "RSDragonwilds/Saved/Config/WindowsServer/Game.ini", "[/Script/Engine.GameSession]\nMaxPlayers=32\n");
  write(old, "RSDragonwilds/activeworld.txt", id);
  dbm.updateWorld(id, { env_vars: JSON.stringify({ MODS_DIR: path.dirname(mod), OTHER_DIR: path.join(sandbox, "outside"), SECRET: save }), wine_prefix: path.join(old, "wine-prefix") });
  dbm.setSetting(`activeWorldSave:${id}`, { path: save, name: "Legacy.sav", sha256: "unchanged-record" });
  dbm.setSetting(`modRequiredSource:${id}`, path.dirname(mod));
  dbm.setSetting(`modLaneLedger:${id}`, [mod]);
  dbm.setSetting(`modLaneSelection:${id}`, { keys: ["server|runeschema:win64:Test"] });
  dbm.setSetting(`serverRuntimeFiles:${id}`, { files: ["RSDragonwilds/Binaries/Win64/ue4ss/Mods/mods.txt"] });
  dbm.insertMod({ id: "fixture-mod", world_id: id, package_name: "Test", display_name: "Test", workshop_id: null, version: "1", source: "local", folder: path.dirname(mod), is_server: 1, enabled: 1, created_at: Date.now() });
  const before = snapshots(old);
  const planned = review(id);
  await assert.rejects(migration.migrate(id, { ...planned, confirm: false }), /Review and confirm/);
  await assert.rejects(migration.migrate(id, { ...planned, destination: path.join(sandbox, "wrong") }), /Review and confirm/);
  sup.isAlive = (candidate) => candidate === id;
  assert.equal(migration.plan(id).canMigrate, false);
  sup.isAlive = realAlive;
  const jobId = require("../lib/jobs").createJob({ type: "update" });
  assert.match(migration.plan(id).reason, /current installation/);
  require("../lib/jobs").finishJob(jobId, true);
  const copyJob = require("../lib/jobs").createJob({ type: "install", worldId: id });
  require("../lib/jobs").setPhase(copyJob, "copy", "fixture migration");
  const updateBlocked = await require("../lib/scheduler").updateWorld(id);
  assert.equal(updateBlocked.ok, false);
  assert.match(updateBlocked.error, /migration or file refresh/);
  require("../lib/jobs").finishJob(copyJob, true);
  const progress = [];
  const result = await migration.migrate(id, planned, { onProgress: (value) => progress.push(value.percent) });
  assert.deepEqual(snapshots(old), before, "migration must leave every original file untouched");
  const newRoot = result.installDir;
  const mapped = (file) => path.join(newRoot, path.relative(old, file));
  for (const file of [save, player, mod, ini.settingsIniPath(old, "windows")]) assert.deepEqual(fs.readFileSync(mapped(file)), fs.readFileSync(file));
  assert.equal(dbm.getWorld(id).install_dir, newRoot);
  assert.equal(dbm.getWorld(id).status, "stopped");
  assert.equal(dbm.getWorld(id).owner_id, "profile-owner", "never overwrite a profile identity override");
  assert.equal(dbm.getWorld(id).admin_password, "profile-admin");
  assert.equal(dbm.getWorld(id).server_password, "ini-world-password", "fill a missing legacy password without changing the INI");
  assert.equal(dbm.getSetting(`serverProfileIni:${id}`).raw, raw, "retain unknown fields such as ServerGuid");
  assert.equal(dbm.getSetting(`activeWorldSave:${id}`).path, mapped(save));
  assert.equal(dbm.getSetting(`modRequiredSource:${id}`), path.dirname(mapped(mod)));
  assert.deepEqual(dbm.getSetting(`modLaneLedger:${id}`), [mapped(mod)]);
  assert.deepEqual(dbm.getSetting(`modLaneSelection:${id}`), { keys: ["server|runeschema:win64:Test"] });
  assert.equal(dbm.listMods(id)[0].folder, path.dirname(mapped(mod)));
  const env = JSON.parse(dbm.getWorld(id).env_vars);
  assert.equal(env.MODS_DIR, path.dirname(mapped(mod)));
  assert.equal(env.OTHER_DIR, path.join(sandbox, "outside"));
  assert.equal(env.SECRET, save, "a credential-like arbitrary value must not be rebased");
  assert.equal(forks.readLedger(newRoot).buildId, "100");
  assert.equal(require("../lib/steamcmd").readInstalledBuildId(newRoot), "100");
  assert.equal(result.stopped, true);
  assert.equal(progress.at(-1), 100);
  assert(guardCalls >= 6, "check for unmanaged processes before and after copying");
  assert.equal(migration.plan(id).canMigrate, false, "repeat migration must be idempotent");
  await assert.rejects(migration.migrate(id, planned), /already uses/);

  const failedRoot = fixture("failed-source"), failed = profile(failedRoot, "Failure");
  write(failedRoot, path.relative(failedRoot, ini.settingsIniPath(failedRoot, "windows")), raw);
  dbm.setSetting(`modRequiredSource:${failed.world_id}`, path.join(failedRoot, "RSDragonwilds/Content/Paks"));
  const failedBefore = snapshots(failedRoot), failedPlan = review(failed.world_id);
  fs.promises.copyFile = async () => { throw new Error("simulated disk full"); };
  await assert.rejects(migration.migrate(failed.world_id, failedPlan), /disk full/);
  fs.promises.copyFile = realCopy;
  assert.equal(dbm.getWorld(failed.world_id).install_dir, failedRoot);
  assert(!fs.existsSync(failedPlan.destination));
  assert.deepEqual(snapshots(failedRoot), failedBefore);
  assert(!fs.readdirSync(path.dirname(failedPlan.destination)).some((name) => name.includes("migration-stage")), "only the disposable failed stage is cleaned up");

  // If database publication fails after a verified copy, retain that copy and
  // resume by verifying both folders; never delete or overwrite either folder.
  dbm.updateWorld = () => { throw new Error("simulated database commit failure"); };
  await assert.rejects(migration.migrate(failed.world_id, failedPlan), /database commit/);
  dbm.updateWorld = realUpdate;
  assert.equal(dbm.getWorld(failed.world_id).install_dir, failedRoot);
  assert.equal(dbm.getSetting(`serverProfileIni:${failed.world_id}`, null), null, "scoped state must roll back with the profile row");
  assert.equal(dbm.getSetting(`modRequiredSource:${failed.world_id}`), path.join(failedRoot, "RSDragonwilds/Content/Paks"), "rebased paths must also roll back");
  assert(fs.existsSync(failedPlan.destination));
  assert.equal(migration.plan(failed.world_id).resume, true);
  write(failedPlan.destination, "RSDragonwilds/Content/Paks/base.pak", "changed retained copy");
  await assert.rejects(migration.migrate(failed.world_id, review(failed.world_id)), /retained destination changed/);
  assert.equal(dbm.getWorld(failed.world_id).install_dir, failedRoot);
  write(failedPlan.destination, "RSDragonwilds/Content/Paks/base.pak", "fixture assets");
  const retainedLedger = fs.readFileSync(path.join(failedPlan.destination, forks.LEDGER));
  fs.writeFileSync(path.join(failedPlan.destination, forks.LEDGER), '{}');
  await assert.rejects(migration.migrate(failed.world_id, review(failed.world_id)), /retained Core ledger changed/);
  fs.writeFileSync(path.join(failedPlan.destination, forks.LEDGER), retainedLedger);
  await migration.migrate(failed.world_id, review(failed.world_id));
  assert.equal(dbm.getWorld(failed.world_id).install_dir, failedPlan.destination);

  const changedRoot = fixture("changed-source"), changed = profile(changedRoot, "Changed");
  const changedPlan = review(changed.world_id);
  let edited = false;
  await assert.rejects(migration.migrate(changed.world_id, changedPlan, { onProgress: ({ percent }) => {
    if (!edited && percent >= 65) { edited = true; write(changedRoot, "RSDragonwilds/Content/Paks/base.pak", "user changed source while copying"); }
  } }), /Source files changed/);
  assert.equal(dbm.getWorld(changed.world_id).install_dir, changedRoot);
  assert(!fs.existsSync(changedPlan.destination));
  fs.mkdirSync(changedPlan.destination);
  write(changedPlan.destination, "keep.txt", "unrelated destination");
  assert.match(migration.plan(changed.world_id).reason, /already exists/);
  assert.equal(fs.readFileSync(path.join(changedPlan.destination, "keep.txt"), "utf8"), "unrelated destination");

  const linkedRoot = fixture("linked-source"), linked = profile(linkedRoot, "Linked");
  fs.symlinkSync(core, path.join(linkedRoot, "linked-files"), process.platform === "win32" ? "junction" : "dir");
  await assert.rejects(migration.migrate(linked.world_id, review(linked.world_id)), /Linked file needs review/);
  assert.equal(dbm.getWorld(linked.world_id).install_dir, linkedRoot);
  dbm.updateWorld(linked.world_id, { extra_args: `-custom="${linkedRoot}"` });
  assert.match(migration.plan(linked.world_id).reason, /Custom launch arguments/);

  const shared = profile(core, "Shared");
  const nestedPrivate = fixture("Core/RSDW/old-private");
  profile(nestedPrivate, "Nested legacy profile");
  assert.match(migration.plan(shared.world_id).reason, /Activate this profile/);
  dbm.setSetting("activeServerWorldId", shared.world_id);
  dbm.setSetting("applicationSetup:activeServerRuntimeFiles", { files: ["loader.dll"] });
  write(core, "RSDW/unrelated-profile/keep.sav", "must not be copied into a shared migration");
  const sharedResult = await migration.migrate(shared.world_id, review(shared.world_id));
  assert(!fs.existsSync(path.join(sharedResult.installDir, "RSDW")));
  assert.deepEqual(dbm.getSetting(`serverRuntimeFiles:${shared.world_id}`), { files: ["loader.dll"] });
  assert.equal(fs.readFileSync(path.join(core, "RSDW/unrelated-profile/keep.sav"), "utf8"), "must not be copied into a shared migration");
  console.log("Reviewed Server migration: file verification, identity, saves, mods, path rebasing, guards, rollback, recovery and no restart: OK");
}

main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => {
  processGuard.assertNoConflictingServer = realGuard;
  processGuard.runningServerProcesses = realProcesses;
  sup.isAlive = realAlive;
  fs.promises.copyFile = realCopy;
  dbm.updateWorld = realUpdate;
  try { dbm.db().close(); } catch {}
  if (path.dirname(sandbox) === path.resolve(__dirname, "..") && path.basename(sandbox).startsWith(".rsdw-server-migration-test-")) fs.rmSync(sandbox, { recursive: true, force: true });
});
