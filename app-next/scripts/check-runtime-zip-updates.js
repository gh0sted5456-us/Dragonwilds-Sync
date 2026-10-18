const assert = require("assert");
const fs = require("fs");
const path = require("path");
const AdmZip = require("adm-zip");
const sandbox = fs.mkdtempSync(path.join(__dirname, "..", ".rsdw-runtime-test-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const files = require("../lib/runtime-files");
const lanes = require("../lib/runtime-lanes");
const packages = require("../lib/runtime-packages");
const isolation = require("../lib/client-isolation");
const provision = require("../lib/provision");
const bin = "Binaries/Win64/";
const options = { processes: [] }; // Deterministic simulated processes, never alter a real installation.
function write(file, value) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, value); }
function archive(name, entries) {
  const zip = new AdmZip(), file = path.join(sandbox, name + ".zip");
  for (const [relative, value] of Object.entries(entries)) zip.addFile(relative, Buffer.from(value));
  zip.writeZip(file); return file;
}
function makeInstall(name, platform) {
  const root = path.join(sandbox, name);
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Binaries", platform === "gamepass" ? "WinGDK" : "Win64"), { recursive: true });
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Content", "Paks"), { recursive: true });
  dbm.setSetting(platform === "server" ? "applicationSetup:serverDir" : "clientInstall:" + platform, root);
  return root;
}
function payload(platform, version, extra = {}) {
  const folder = platform === "gamepass" ? "WinGDK" : "Win64";
  return { [folder + "/" + (platform === "server" ? "version.dll" : "dwmapi.dll")]: "proxy-" + version,
    [folder + "/ue4ss/UE4SS.dll"]: "loader-" + version,
    [folder + "/ue4ss/Mods/mods.txt"]: "RuneSchema : 1\nKeybinds : 1\n", ...extra };
}
function schema(version, extra = {}) {
  return { "RuneSchema/dlls/main.dll": "schema-" + version, "RuneSchema/mods/runeschema.txt": "Example : 1\n", ...extra };
}
function live(root, relative) { return path.join(root, "RSDragonwilds", ...relative.split("/")); }
function contents(root, relative) { return fs.readFileSync(live(root, relative), "utf8"); }

async function main() {
  const steam = makeInstall("steam", "steam"), gamepass = makeInstall("gamepass", "gamepass"), server = makeInstall("core", "server");
  const old = archive("steam-v1", payload("steam", "v1", { "Win64/ue4ss/obsolete.dll": "retired", "Win64/ue4ss/Mods/Keybinds/Scripts/main.lua": "built-in" }));
  await lanes.install("steam", "ue4ss-steam", old, () => {}, options);
  assert.equal(contents(steam, bin + "ue4ss/UE4SS.dll"), "loader-v1");
  assert(fs.existsSync(live(steam, bin + "ue4ss/Mods/mods.txt")), "first install must seed a missing mod list");
  const list = "\uFEFF; keep comments\r\nRuneSchema : 0\r\nCustomMod : 1\r\n";
  write(live(steam, bin + "ue4ss/Mods/mods.txt"), list);
  write(live(steam, bin + "ue4ss/Mods/CustomMod/Scripts/main.lua"), "user mod");
  write(live(steam, "Saved/SaveGames/World.sav"), "save");
  write(live(steam, bin + "ue4ss/unmanaged.dll"), "unknown original");
  const update = archive("steam-v2", payload("steam", "v2", { "Win64/ue4ss/new.dll": "new" }));
  const result = await lanes.install("steam", "ue4ss-steam", update, () => {}, options);
  assert(result.deployment.removed >= 2, "retired bundled files must be removed");
  assert(!fs.existsSync(live(steam, bin + "ue4ss/obsolete.dll")));
  assert(!fs.existsSync(live(steam, bin + "ue4ss/Mods/Keybinds/Scripts/main.lua")));
  assert.equal(contents(steam, bin + "ue4ss/Mods/mods.txt"), list, "mod list bytes changed");
  assert.equal(contents(steam, bin + "ue4ss/Mods/CustomMod/Scripts/main.lua"), "user mod");
  assert.equal(contents(steam, bin + "ue4ss/unmanaged.dll"), "unknown original");
  assert.equal(contents(steam, "Saved/SaveGames/World.sav"), "save");
  assert.equal(contents(steam, bin + "ue4ss/UE4SS.dll"), "loader-v2");
  assert.equal(lanes.status("steam").packages[0].sha256, files.hashFile(update));
  assert(fs.existsSync(lanes.status("steam").packages[0].manifestPath));

  await lanes.install("steam", "runeschema", archive("schema-v1", schema("v1", { "RuneSchema/plugins/plugins.txt": "Plugin : 1\n", "RuneSchema/scripts/old.lua": "old", "RuneSchema/mods/Example/config.json": "must not replace user mods" })), () => {}, options);
  assert(!fs.existsSync(live(steam, bin + "ue4ss/Mods/RuneSchema/enabled.txt")), "a disabled framework was re-enabled");
  const runeList = "; custom state\r\nExample : 0\r\nPlayerMod : 1\r\n";
  write(live(steam, bin + "ue4ss/Mods/RuneSchema/mods/runeschema.txt"), runeList);
  write(live(steam, bin + "ue4ss/Mods/RuneSchema/plugins/plugins.txt"), "Plugin : 0\r\nUserPlugin : 1\r\n");
  write(live(steam, bin + "ue4ss/Mods/RuneSchema/mods/PlayerMod/main.lua"), "user schema mod");
  await lanes.install("steam", "runeschema", archive("schema-v2", schema("v2", { "RuneSchema/scripts/new.lua": "new" })), () => {}, options);
  assert.equal(contents(steam, bin + "ue4ss/Mods/RuneSchema/dlls/main.dll"), "schema-v2");
  assert(!fs.existsSync(live(steam, bin + "ue4ss/Mods/RuneSchema/scripts/old.lua")));
  assert.equal(contents(steam, bin + "ue4ss/Mods/RuneSchema/mods/runeschema.txt"), runeList);
  assert.equal(contents(steam, bin + "ue4ss/Mods/RuneSchema/plugins/plugins.txt"), "Plugin : 0\r\nUserPlugin : 1\r\n");
  assert.equal(contents(steam, bin + "ue4ss/Mods/RuneSchema/mods/PlayerMod/main.lua"), "user schema mod");
  assert(!fs.existsSync(live(steam, bin + "ue4ss/Mods/RuneSchema/mods/Example/config.json")));
  const scanned = isolation.scan(steam, "steam");
  assert(!scanned.entries.some((file) => /RuneSchema\/dlls\/main.dll$/i.test(file.relative)), "Safe Storage mistook a managed framework for an unmanaged mod");
  assert(!scanned.entries.some((file) => /RuneSchema\/plugins\/plugins.txt$/i.test(file.relative)), "a retained list lost its managed-control identity");

  await lanes.install("gamepass", "ue4ss-gamepass", archive("gamepass", payload("gamepass", "gdk")), () => {}, options);
  await lanes.install("gamepass", "runeschema", archive("schema-gdk", schema("gdk")), () => {}, options);
  assert.equal(contents(gamepass, "Binaries/WinGDK/ue4ss/UE4SS.dll"), "loader-gdk");
  assert.equal(contents(gamepass, "Binaries/WinGDK/ue4ss/Mods/RuneSchema/dlls/main.dll"), "schema-gdk");
  assert(!fs.existsSync(live(gamepass, "Binaries/Win64")), "Game Pass leaked files into Win64");
  await assert.rejects(lanes.install("gamepass", "ue4ss-steam", old, () => {}, options), /does not match/);
  await assert.rejects(lanes.install("gamepass", "ue4ss-gamepass", old, () => {}, options), /complete UE4SS/);
  await assert.rejects(lanes.install("steam", "ue4ss-steam", update, () => {}, { processes: [{ pid: 321, path: path.join(steam, "RSDragonwilds.exe") }] }), /still running/);

  const before = files.readPackage(lanes.packageRoot("steam", "ue4ss-steam")).archiveSha256;
  const rollbackZip = archive("rollback", payload("steam", "bad", { "Win64/ue4ss/add.dll": "partial" }));
  await assert.rejects(lanes.install("steam", "ue4ss-steam", rollbackZip, (event) => { if (event.percent >= 80 && event.percent < 100) throw new Error("simulated deployment failure"); }, options), /simulated/);
  assert.equal(contents(steam, bin + "ue4ss/UE4SS.dll"), "loader-v2", "failed update changed the live loader");
  assert.equal(files.readPackage(lanes.packageRoot("steam", "ue4ss-steam")).archiveSha256, before, "failed update replaced its package manifest");
  assert.equal(contents(steam, bin + "ue4ss/Mods/mods.txt"), list);
  assert(!fs.existsSync(live(steam, bin + "ue4ss/add.dll")));
  const corrupt = path.join(lanes.packageRoot("steam", "ue4ss-steam"), "files", bin, "ue4ss/UE4SS.dll");
  write(corrupt, "tampered");
  const manifest = files.readPackage(lanes.packageRoot("steam", "ue4ss-steam"));
  const file = manifest.files.find((item) => /ue4ss\/UE4SS.dll$/i.test(item.relative));
  assert.throws(() => files.applyFiles({ gameRoot: path.join(steam, "RSDragonwilds"), desired: [{ ...file, component: "ue4ss-steam", source: corrupt }], ledgerFile: path.join(sandbox, "tamper-ledger.json") }), /cache verification/);
  await lanes.install("steam", "ue4ss-steam", update, () => {}, options);

  const duplicate = archive("duplicate", { ...payload("steam", "bad"), "Win64/ue4ss/ue4ss.DLL": "collision" });
  await assert.rejects(lanes.install("steam", "ue4ss-steam", duplicate, () => {}, options), /colliding/);
  await assert.rejects(lanes.install("steam", "ue4ss-steam", archive("unsafe-executable", { ...payload("steam", "bad"), "Win64/RSDragonwilds.exe": "game" }), () => {}, options), /outside its loader/);
  assert.throws(() => files.targetFile(sandbox, "../escaped.dll"), /unsafe/);
  assert.throws(() => files.targetFile(sandbox, "/absolute.dll"), /unsafe/);
  assert.throws(() => files.targetFile(sandbox, "folder/NUL.txt"), /unsafe/);
  write(live(steam, bin + "version.dll"), "unmanaged server proxy");
  await assert.rejects(lanes.install("steam", "ue4ss-steam", update, () => {}, options), /unmanaged loader bootstrap/);
  fs.unlinkSync(live(steam, bin + "version.dll"));
  assert.equal(contents(steam, bin + "ue4ss/UE4SS.dll"), "loader-v2");

  // Simulate a killed update: next attempt restores the journal before retrying.
  const deploymentFile = path.join(path.dirname(lanes.packageRoot("steam", "ue4ss-steam")), "installed.json");
  const oldLedger = JSON.parse(fs.readFileSync(deploymentFile, "utf8")), recoveryId = "0011223344556677";
  const interruptedRelative = bin + "ue4ss/UE4SS.dll", newRelative = bin + "ue4ss/incomplete.dll";
  write(path.join(deploymentFile + ".recovery", recoveryId, ...interruptedRelative.split("/")), "loader-v2");
  write(live(steam, interruptedRelative), "partial write");
  write(live(steam, newRelative), "partial new file");
  files.atomicJson(deploymentFile + ".pending", { id: recoveryId, gameRoot: path.join(steam, "RSDragonwilds"), oldLedger, operations: [
    { relative: interruptedRelative, existed: true }, { relative: newRelative, existed: false, sha256: files.hashFile(live(steam, newRelative)) },
  ] });
  await assert.rejects(lanes.install("steam", "ue4ss-steam", update, () => {}, options), /Recovered an interrupted/);
  assert.equal(contents(steam, interruptedRelative), "loader-v2");
  assert(!fs.existsSync(live(steam, newRelative)));
  assert(!fs.existsSync(deploymentFile + ".pending"));
  await lanes.install("steam", "ue4ss-steam", update, () => {}, options);

  const serverV1 = archive("server-v1", payload("server", "server1", { "Win64/ue4ss/old.dll": "old" }));
  await lanes.install("server", "ue4ss-server", serverV1, () => {}, options);
  const fork = path.join(sandbox, "fork");
  fs.mkdirSync(path.join(fork, "RSDragonwilds", "Binaries", "Win64"), { recursive: true });
  const world = provision.createProfile({ display_name: "Loader fork", install_dir: fork, owner_id: "test", platform: "windows" });
  packages.materializeHost(world.world_id);
  assert.equal(contents(fork, bin + "ue4ss/UE4SS.dll"), "loader-server1");
  const forkBootstrap = contents(fork, bin + "version.dll");
  write(live(server, bin + "version.dll"), "retained-core-bootstrap");
  assert(packages.status(world.world_id).ue4ssServer.inherited);
  await lanes.install("server", "ue4ss-server", archive("server-v2", payload("server", "server2")), () => {}, options);
  assert.equal(contents(server, bin + "version.dll"), "retained-core-bootstrap", "an update replaced the retained server proxy");
  assert.equal(contents(fork, bin + "ue4ss/UE4SS.dll"), "loader-server1", "core update changed a profile before its next start");
  packages.materializeHost(world.world_id);
  assert.equal(contents(fork, bin + "version.dll"), forkBootstrap, "a default update replaced a profile's retained proxy");
  assert.equal(contents(fork, bin + "ue4ss/UE4SS.dll"), "loader-server2");
  assert(!fs.existsSync(live(fork, bin + "ue4ss/old.dll")));
  await packages.install(world.world_id, "ue4ss-server", serverV1);
  assert.equal(contents(fork, bin + "version.dll"), forkBootstrap);
  assert(!packages.status(world.world_id).ue4ssServer.inherited, "a World ZIP must override the default");
  assert.equal(contents(fork, bin + "ue4ss/UE4SS.dll"), "loader-server1");
  dbm.updateWorld(world.world_id, { process_id: process.pid });
  assert.throws(() => packages.materializeHost(world.world_id), /Stop the World/);
  dbm.updateWorld(world.world_id, { process_id: null });
  await packages.install(world.world_id, "ue4ss-steam", old);
  await packages.install(world.world_id, "runeschema", archive("world-schema", schema("world")));
  assert(packages.syncFiles(world.world_id, "gamepass").filter((entry) => entry.component === "runeschema").every((entry) => entry.target.includes("WinGDK")));
  assert(!packages.syncFiles(world.world_id, "steam").some((entry) => /mods.txt|runeschema.txt|version.dll/i.test(entry.target)), "client publication leaked mod lists/server-only runtime");
  const [realSteam, realGamepass, realSchema] = process.argv.slice(2);
  if (realSteam && realGamepass && realSchema) {
    for (const [platform, root, zip] of [["steam", steam, realSteam], ["gamepass", gamepass, realGamepass]]) {
      await lanes.install(platform, "ue4ss-" + platform, zip, () => {}, options);
      await lanes.install(platform, "runeschema", realSchema, () => {}, options);
      const folder = platform === "gamepass" ? "WinGDK" : "Win64";
      const custom = "Custom : 0\r\n; real archive preservation check\r\n";
      for (const relative of ["ue4ss/Mods/mods.txt", "ue4ss/Mods/BPModLoaderMod/load_order.txt", "ue4ss/Mods/RuneSchema/mods/runeschema.txt", "ue4ss/Mods/RuneSchema/plugins/plugins.txt"]) write(live(root, "Binaries/" + folder + "/" + relative), custom);
      await lanes.install(platform, "ue4ss-" + platform, zip, () => {}, options);
      await lanes.install(platform, "runeschema", realSchema, () => {}, options);
      for (const relative of ["ue4ss/Mods/mods.txt", "ue4ss/Mods/BPModLoaderMod/load_order.txt", "ue4ss/Mods/RuneSchema/mods/runeschema.txt", "ue4ss/Mods/RuneSchema/plugins/plugins.txt"]) assert.equal(contents(root, "Binaries/" + folder + "/" + relative), custom);
      assert(fs.existsSync(live(root, "Binaries/" + folder + "/ue4ss/Mods/RuneSchema/dlls/main.dll")));
      assert(!fs.existsSync(live(root, "Binaries/" + folder + "/Readme.txt")), "top-level packaging notes leaked into the loader directory");
      console.log("Real archives validated without executing binaries: " + platform + " " + JSON.stringify(lanes.status(platform).packages.map((item) => ({ component: item.component, files: item.files, sha256: item.sha256 }))));
    }
    await lanes.install("server", "ue4ss-server", realSteam, () => {}, options);
    assert.equal(contents(server, bin + "version.dll"), "retained-core-bootstrap", "the Steam ZIP replaced the server proxy");
    assert(!fs.existsSync(live(server, bin + "dwmapi.dll")), "the Steam bootstrap leaked into the server lane");
    console.log("Real Steam ZIP accepted for server payload while retaining version.dll: OK");
  }
  console.log("Runtime ZIP manifests, Steam/Server/Game Pass routing, stale-file removal, mod-list preservation, loader isolation, rollback, and server defaults: OK");
}
main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
