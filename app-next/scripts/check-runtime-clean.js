const assert = require("assert");
const fs = require("fs");
const path = require("path");
const AdmZip = require("adm-zip");
const sandbox = fs.mkdtempSync(path.join(__dirname, "..", ".rsdw-runtime-clean-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const lanes = require("../lib/runtime-lanes");
const packages = require("../lib/runtime-packages");
const provision = require("../lib/provision");
const runtime = require("../lib/runtime-files");
const options = { processes: [] };
function write(file, value) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, value); }
function game(name, platform) {
  const root = path.join(sandbox, name);
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Binaries", platform === "gamepass" ? "WinGDK" : "Win64"), { recursive: true });
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Content"), { recursive: true });
  dbm.setSetting(platform === "server" ? "applicationSetup:serverDir" : "clientInstall:" + platform, root);
  return root;
}
const live = (root, rel) => path.join(root, "RSDragonwilds", ...rel.split("/"));
const read = (file) => fs.readFileSync(file, "utf8");
function zip(name, server = false, version = "one") {
  const archive = new AdmZip(), file = path.join(sandbox, name + ".zip");
  for (const [rel, value] of Object.entries({
    ["Win64/" + (server ? "version.dll" : "dwmapi.dll")]: "proxy",
    "Win64/ue4ss/UE4SS.dll": version,
    "Win64/ue4ss/UE4SS-settings.ini": "settings",
    "Win64/ue4ss/Mods/mods.txt": "RuneSchema : 1\nCustom : 1\n",
    "Win64/ue4ss/Mods/Builtin/Scripts/main.lua": "builtin",
    ...(version === "one" ? { "Win64/ue4ss/old.dll": "retired" } : {}),
  })) archive.addFile(rel, Buffer.from(value));
  archive.writeZip(file); return file;
}
function fileInPreview(preview, entry) { return path.join(preview.targets.find((target) => target.id === entry.target).root, ...entry.relative.split("/")); }

async function main() {
  const steam = game("steam", "steam"), bin = "Binaries/Win64/", ue = live(steam, bin + "ue4ss");
  const originalZip = zip("steam");
  await lanes.install("steam", "ue4ss-steam", originalZip, () => {}, options);
  write(path.join(ue, "unknown/config.ini"), "unknown");
  fs.mkdirSync(path.join(ue, "empty/nested"), { recursive: true });
  const mod = path.join(ue, "Mods/Custom/file.lua");
  const runeCore = path.join(ue, "Mods/RuneSchema/dlls/main.dll");
  const runeMod = path.join(ue, "Mods/RuneSchema/mods/MyMod/config.json");
  write(mod, "my mod"); write(runeCore, "old schema"); write(runeMod, "rune mod");
  write(path.join(ue, "Mods/RuneSchema/mods/runeschema.txt"), "MyMod : 1\r\n");
  write(path.join(ue, "Mods/RuneSchema/plugins/plugins.txt"), "Plugin : 1\r\n");
  write(path.join(ue, "Mods/RuneSchema/plugins/Plugin/code.lua"), "plugin");
  write(live(steam, bin + "version.dll"), "retained");
  const preview = await lanes.cleanupPreview("steam", "ue4ss-steam");
  assert(preview.files > 0);
  assert(!preview.entries.some((entry) => /^mods\//i.test(entry.relative)), "preview traversed preserved Mods");
  write(path.join(ue, "late.log"), "changed since preview");
  await assert.rejects(lanes.clean("steam", "ue4ss-steam", preview.fingerprint, () => {}, options), /changed since review/);
  assert(fs.existsSync(path.join(ue, "UE4SS.dll")));
  const current = await lanes.cleanupPreview("steam", "ue4ss-steam");
  await assert.rejects(lanes.clean("steam", "ue4ss-steam", current.fingerprint, () => {}, { processes: [{ pid: 42, path: path.join(steam, "RSDragonwilds.exe") }] }), /still running/);
  write(mod, "edited after preview"); // Mods are deliberately excluded from fingerprints and backups.
  const cleaned = await lanes.clean("steam", "ue4ss-steam", current.fingerprint, () => {}, options);
  assert(!fs.existsSync(path.join(ue, "UE4SS.dll")));
  assert(!fs.existsSync(path.join(ue, "unknown/config.ini")));
  assert(fs.existsSync(path.join(ue, "unknown")) && fs.existsSync(path.join(ue, "empty/nested")), "directory structure was deleted");
  assert.equal(read(mod), "edited after preview");
  assert.equal(read(runeCore), "old schema", "UE4SS cleanup touched RuneSchema inside Mods");
  assert.equal(read(runeMod), "rune mod");
  assert.equal(read(path.join(ue, "Mods/mods.txt")), "RuneSchema : 1\nCustom : 1\n");
  assert.equal(read(live(steam, bin + "version.dll")), "retained");
  assert.equal(read(live(steam, bin + "dwmapi.dll")), "proxy");
  const status = lanes.status("steam").packages[0];
  assert(status.cleaned && !status.installed, "a cleaned package was resurrected from cache");
  const cached = path.join(lanes.packageRoot("steam", "ue4ss-steam"), "files/Binaries/Win64/ue4ss");
  assert(!fs.existsSync(path.join(cached, "UE4SS.dll")));
  assert(fs.existsSync(path.join(cached, "Mods/Builtin/Scripts/main.lua")));
  write(mod, "keep newest mod edit");
  const realRename = fs.renameSync, failTarget = fileInPreview(current, current.entries[1]);
  let failedRestore = false;
  fs.renameSync = (from, to) => {
    if (!failedRestore && String(from).endsWith(".rsdw-clean-restore") && to === failTarget) { failedRestore = true; throw new Error("simulated restore interruption"); }
    return realRename(from, to);
  };
  try { await assert.rejects(lanes.restoreClean("steam", "ue4ss-steam", cleaned.recovery.id, () => {}, options), /simulated restore/); }
  finally { fs.renameSync = realRename; }
  assert(failedRestore, "the restoration failure hook was not exercised");
  await assert.rejects(lanes.install("steam", "ue4ss-steam", originalZip, () => {}, options), /Restore the interrupted/);
  await lanes.restoreClean("steam", "ue4ss-steam", cleaned.recovery.id, () => {}, options);
  assert.equal(read(path.join(ue, "UE4SS.dll")), "one");
  assert.equal(read(path.join(ue, "unknown/config.ini")), "unknown");
  assert.equal(read(mod), "keep newest mod edit", "restore overwrote a preserved mod");
  assert(lanes.status("steam").packages[0].installed);
  await assert.rejects(lanes.restoreClean("steam", "ue4ss-steam", cleaned.recovery.id, () => {}, options), /not available/);

  const failure = await lanes.cleanupPreview("steam", "ue4ss-steam");
  await assert.rejects(lanes.clean("steam", "ue4ss-steam", failure.fingerprint, (event) => { if (event.phase === "cleanup") throw new Error("simulated deletion failure"); }, options), /simulated/);
  assert.equal(read(path.join(ue, "UE4SS.dll")), "one");
  assert(lanes.status("steam").packages[0].installed);
  const raced = await lanes.cleanupPreview("steam", "ue4ss-steam"), second = raced.entries[1], changed = fileInPreview(raced, second), original = read(changed);
  let racedOnce = false;
  await assert.rejects(lanes.clean("steam", "ue4ss-steam", raced.fingerprint, (event) => {
    if (event.phase === "cleanup" && !racedOnce) { racedOnce = true; write(changed, "concurrent edit"); }
  }, options), /changed while cleaning/);
  assert.equal(read(changed), "concurrent edit", "rollback overwrote the file which caused a changed-preview abort");
  write(changed, original);

  const rs = await lanes.cleanupPreview("steam", "runeschema");
  const rsCleaned = await lanes.clean("steam", "runeschema", rs.fingerprint, () => {}, options);
  assert(!fs.existsSync(runeCore));
  assert.equal(read(runeMod), "rune mod");
  assert.equal(read(path.join(ue, "Mods/RuneSchema/mods/runeschema.txt")), "MyMod : 1\r\n");
  assert(!fs.existsSync(path.join(ue, "Mods/RuneSchema/plugins/plugins.txt")), "explicit cleanup failed to clear a control list outside its Mods folder");
  assert(fs.existsSync(path.join(ue, "Mods/RuneSchema/plugins/Plugin")));
  assert.equal(read(path.join(ue, "UE4SS.dll")), "one");
  await lanes.restoreClean("steam", "runeschema", rsCleaned.recovery.id, () => {}, options);
  assert.equal(read(runeCore), "old schema");
  assert.equal(read(path.join(ue, "Mods/RuneSchema/plugins/plugins.txt")), "Plugin : 1\r\n");

  const after = await lanes.cleanupPreview("steam", "ue4ss-steam");
  const cleanAgain = await lanes.clean("steam", "ue4ss-steam", after.fingerprint, () => {}, options);
  fs.unlinkSync(live(steam, bin + "version.dll")); // Remove test-only opposing proxy before reinstalling Steam.
  await lanes.install("steam", "ue4ss-steam", originalZip, () => {}, options);
  await assert.rejects(lanes.restoreClean("steam", "ue4ss-steam", cleanAgain.recovery.id, () => {}, options), /changed after cleanup/);

  const gdk = game("gamepass", "gamepass");
  write(live(gdk, "Binaries/WinGDK/ue4ss/UE4SS.dll"), "gdk");
  write(live(gdk, "Binaries/WinGDK/ue4ss/mods/Kept/data.txt"), "keep");
  write(live(gdk, "Binaries/Win64/ue4ss/leave.dll"), "other platform");
  const gp = await lanes.cleanupPreview("gamepass", "ue4ss-gamepass");
  await lanes.clean("gamepass", "ue4ss-gamepass", gp.fingerprint, () => {}, options);
  assert(!fs.existsSync(live(gdk, "Binaries/WinGDK/ue4ss/UE4SS.dll")));
  assert.equal(read(live(gdk, "Binaries/WinGDK/ue4ss/mods/Kept/data.txt")), "keep");
  assert.equal(read(live(gdk, "Binaries/Win64/ue4ss/leave.dll")), "other platform");

  const outside = path.join(sandbox, "outside"); write(path.join(outside, "valuable.dll"), "do not touch");
  const linked = path.join(ue, "linked");
  fs.symlinkSync(outside, linked, process.platform === "win32" ? "junction" : "dir");
  await assert.rejects(lanes.cleanupPreview("steam", "ue4ss-steam"), /linked/);
  assert.equal(read(path.join(outside, "valuable.dll")), "do not touch");
  fs.unlinkSync(linked);

  const core = game("server", "server"), serverZip = zip("server", true), fork = path.join(sandbox, "fork");
  await lanes.install("server", "ue4ss-server", serverZip, () => {}, options);
  fs.mkdirSync(live(fork, bin), { recursive: true });
  const world = provision.createProfile({ display_name: "Clean fork", install_dir: fork, platform: "windows", owner_id: "test" });
  packages.materializeHost(world.world_id);
  const serverPlan = await lanes.cleanupPreview("server", "ue4ss-server");
  await lanes.clean("server", "ue4ss-server", serverPlan.fingerprint, () => {}, options);
  assert.equal(read(live(core, bin + "version.dll")), "proxy");
  const legacy = provision.createProfile({ display_name: "Shared-core legacy", install_dir: core, platform: "windows", owner_id: "test" });
  assert.throws(() => packages.materializeHost(legacy.world_id), /no runtime to keep/);
  assert.throws(() => packages.cleanupPreview(legacy.world_id, "ue4ss-server"), /shared Core/);
  packages.materializeHost(world.world_id); // Cleaning the default must not sweep other profiles.
  assert.equal(read(live(fork, bin + "ue4ss/UE4SS.dll")), "one");
  assert.equal(read(live(fork, bin + "ue4ss/Mods/Builtin/Scripts/main.lua")), "builtin");
  await lanes.install("server", "ue4ss-server", zip("server-two", true, "two"), () => {}, options);
  packages.materializeHost(world.world_id);
  assert.equal(read(live(fork, bin + "ue4ss/UE4SS.dll")), "two");
  assert(!fs.existsSync(live(fork, bin + "ue4ss/old.dll")), "default cleanup lost another profile's stale-file ownership");
  const host = await packages.cleanupPreview(world.world_id, "ue4ss-server");
  const hostCleaned = await packages.clean(world.world_id, "ue4ss-server", host.fingerprint);
  assert(!fs.existsSync(live(fork, bin + "ue4ss/UE4SS.dll")));
  assert.equal(read(live(fork, bin + "version.dll")), "proxy");
  assert.equal(read(live(core, bin + "ue4ss/UE4SS.dll")), "two", "a profile cleaned the shared core");
  assert.throws(() => packages.materializeHost(world.world_id), /intentionally cleaned/);
  await packages.restoreClean(world.world_id, "ue4ss-server", hostCleaned.recovery.id);
  packages.materializeHost(world.world_id);
  assert.equal(read(live(fork, bin + "ue4ss/UE4SS.dll")), "two");
  assert(packages.status(world.world_id).ue4ssServer.inherited);
  console.log("Runtime cleanup: preserved Mods/proxies/directories, preview fingerprints, rollback, restore guards, Game Pass, link safety, profile isolation and default ownership: OK");
}
main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
