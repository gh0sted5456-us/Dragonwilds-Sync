const assert = require("assert");
const fs = require("fs");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(__dirname, "..", ".rsdw-mod-delete-test-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const forks = require("../lib/server-forks");
const provision = require("../lib/provision");
const mods = require("../lib/mod-lanes");

async function main() {
  const core = path.join(sandbox, "core");
  fs.mkdirSync(path.join(core, "RSDragonwilds", "Binaries"), { recursive: true });
  fs.mkdirSync(path.join(core, "RSDragonwilds", "Content"), { recursive: true });
  fs.writeFileSync(path.join(core, "RSDragonwildsServer.exe"), "binary");
  dbm.setSetting("applicationSetup:serverDir", core);
  dbm.setSetting("applicationSetup:ownerId", "mod-delete-owner");
  const worldId = "55555555-5555-4555-8555-555555555555";
  const fork = await forks.forkInstall(core, worldId);
  provision.createProfile({ world_id: worldId, display_name: "Deletion test", install_dir: fork.installDir, platform: fork.platform });
  const game = path.join(fork.installDir, "RSDragonwilds");
  const paks = path.join(game, "Content", "Paks", "~mods");
  fs.mkdirSync(paks, { recursive: true });
  const pak = ["Example.pak", "Example.utoc", "Example.ucas"].map((file) => path.join(paks, file));
  pak.forEach((file) => fs.writeFileSync(file, file));
  const nested = path.join(paks, "Nested", "Example.pak");
  fs.mkdirSync(path.dirname(nested));
  fs.writeFileSync(nested, "different mod, same basename");
  const runeMods = path.join(game, "Binaries", "Win64", "ue4ss", "Mods");
  const rune = path.join(runeMods, "RuneSchema", "mods", "ExampleRune");
  fs.mkdirSync(rune, { recursive: true });
  fs.writeFileSync(path.join(rune, "config.json"), "{}");
  const runeList = path.join(runeMods, "RuneSchema", "mods", "runeschema.txt");
  fs.writeFileSync(runeList, "ExampleRune : 1\nOtherRune : 0\n");
  const unrelated = path.join(paks, "Unrelated.pak");
  fs.writeFileSync(unrelated, "leave me");
  const trashed = [];
  const fakeTrash = (stage) => {
    const destination = path.join(sandbox, `trashed-${trashed.length}`);
    fs.renameSync(stage, destination);
    trashed.push(destination);
  };
  let snapshot = mods.status(worldId);
  assert(snapshot.canDeleteServerMods);
  const pakMod = snapshot.modLanes[0].mods.find((mod) => mod.key === "pak:~mods:example");
  const nestedMod = snapshot.modLanes[0].mods.find((mod) => mod.key === "pak:~mods:example:nested");
  const runeMod = snapshot.modLanes[0].mods.find((mod) => mod.key === "runeschema:win64:examplerune");
  assert(pakMod && nestedMod && runeMod);
  dbm.setSetting(`modLaneSelection:${worldId}`, [{ key: pakMod.selectionKey, scope: "both" }, { key: runeMod.selectionKey, scope: "server" }]);
  dbm.setSetting(`modLaneLedger:${worldId}`, [pak[0], rune]);
  const pakResult = mods.deleteServerMod(worldId, pakMod.selectionKey, { trash: fakeTrash });
  assert.equal(pakResult.removedFiles, 3);
  pak.forEach((file) => assert(!fs.existsSync(file), `PAK file survived: ${file}`));
  assert(fs.existsSync(nested), "same-basename PAK in a different folder must survive");
  assert(fs.existsSync(unrelated));
  assert(!mods.readSelections(worldId).some((item) => item.key === pakMod.selectionKey));
  snapshot = mods.deleteServerMod(worldId, runeMod.selectionKey, { trash: fakeTrash });
  assert.equal(snapshot.removedFiles, 1);
  assert(!fs.existsSync(rune));
  assert(!fs.readFileSync(runeList, "utf8").includes("ExampleRune"));
  assert(fs.readFileSync(runeList, "utf8").includes("OtherRune"));
  assert(!mods.readSelections(worldId).some((item) => item.key === runeMod.selectionKey));
  const rollbackMod = path.join(runeMods, "RuneSchema", "mods", "RollbackRune");
  fs.mkdirSync(rollbackMod);
  fs.writeFileSync(path.join(rollbackMod, "config.json"), "{}");
  fs.appendFileSync(runeList, "RollbackRune : 1\n");
  const rollbackKey = mods.status(worldId).modLanes[0].mods.find((mod) => mod.key === "runeschema:win64:rollbackrune").selectionKey;
  assert.throws(() => mods.deleteServerMod(worldId, rollbackKey, { trash: () => { throw new Error("trash unavailable"); } }), /trash unavailable/);
  assert(fs.existsSync(rollbackMod), "failed trash must restore the mod folder");
  assert(fs.readFileSync(runeList, "utf8").includes("RollbackRune"), "failed trash must restore its loader entry");
  assert.equal(trashed.length, 2);
  console.log("Managed Server mod file deletion: OK");
}

main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
