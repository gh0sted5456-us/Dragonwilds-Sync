const assert = require("assert");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const sandbox = fs.mkdtempSync(path.join(__dirname, "..", ".rsdw-server-forks-test-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const forks = require("../lib/server-forks");
const provision = require("../lib/provision");

async function main() {
  const template = path.join(sandbox, "shared-server");
  fs.mkdirSync(path.join(template, "RSDragonwilds", "Binaries"), { recursive: true });
  fs.mkdirSync(path.join(template, "RSDragonwilds", "Content"), { recursive: true });
  fs.mkdirSync(path.join(template, "RSDragonwilds", "Saved", "SaveGames"), { recursive: true });
  fs.writeFileSync(path.join(template, "RSDragonwildsServer.exe"), "binary");
  fs.writeFileSync(path.join(template, "RSDragonwilds", "Content", "base.pak"), "base");
  fs.writeFileSync(path.join(template, "RSDragonwilds", "Saved", "SaveGames", "old-world.sav"), "private");
  fs.writeFileSync(path.join(template, "RSDragonwilds", "activeworld.txt"), "old-profile");
  const manifest = path.join("steamapps", "appmanifest_4019830.acf");
  const logicMod = path.join("RSDragonwilds", "Content", "Paks", "LogicMods", "loader-mod.pak");
  fs.mkdirSync(path.join(template, "steamapps"), { recursive: true });
  fs.mkdirSync(path.dirname(path.join(template, logicMod)), { recursive: true });
  fs.writeFileSync(path.join(template, manifest), '"buildid" "100"\n"LastUpdated" "1"');
  fs.writeFileSync(path.join(template, logicMod), "old logic mod");
  dbm.setSetting("applicationSetup:serverDir", template);
  dbm.setSetting("applicationSetup:ownerId", "owner-shared");
  const firstId = "11111111-1111-4111-8111-111111111111";
  const secondId = "22222222-2222-4222-8222-222222222222";
  const migratedId = "33333333-3333-4333-8333-333333333333";
  const first = await forks.forkInstall(template, firstId);
  const second = await forks.forkInstall(template, secondId);
  assert.notEqual(first.installDir, second.installDir);
  assert.notEqual(first.installDir, template);
  assert.equal(fs.readFileSync(path.join(first.installDir, "RSDragonwilds", "Content", "base.pak"), "utf8"), "base");
  assert(!fs.existsSync(path.join(first.installDir, "RSDragonwilds", "Saved")), "new profile must not inherit the template's save");
  assert(!fs.existsSync(path.join(first.installDir, "RSDragonwilds", "activeworld.txt")), "new profile must not inherit the active-world marker");
  fs.writeFileSync(path.join(first.installDir, "RSDragonwilds", "Content", "base.pak"), "changed");
  assert.equal(fs.readFileSync(path.join(second.installDir, "RSDragonwilds", "Content", "base.pak"), "utf8"), "base");
  assert.equal(fs.readFileSync(path.join(template, "RSDragonwilds", "Content", "base.pak"), "utf8"), "base");
  const migrated = await forks.forkInstall(template, migratedId, { includeSaved: true });
  assert.equal(fs.readFileSync(path.join(migrated.installDir, "RSDragonwilds", "Saved", "SaveGames", "old-world.sav"), "utf8"), "private");
  assert(!fs.existsSync(path.join(migrated.installDir, "RSDragonwilds", "activeworld.txt")));
  const firstWorld = provision.createProfile({ world_id: firstId, display_name: "First", install_dir: first.installDir, platform: first.platform });
  const secondWorld = provision.createProfile({ world_id: secondId, display_name: "Second", install_dir: second.installDir, platform: second.platform, owner_id: "owner-override" });
  assert.equal(firstWorld.owner_id, "owner-shared");
  assert.equal(secondWorld.owner_id, "owner-override");
  // Simulate a previous release that incorrectly indexed Steam metadata and
  // LogicMods as Core files. They must be excluded from both update and deletion.
  const oldLedger = JSON.parse(fs.readFileSync(path.join(second.installDir, forks.LEDGER), "utf8"));
  for (const relative of [manifest, logicMod]) {
    const content = fs.readFileSync(path.join(second.installDir, relative));
    oldLedger.files.push({ relative, size: content.length, sha256: crypto.createHash("sha256").update(content).digest("hex") });
  }
  fs.writeFileSync(path.join(second.installDir, forks.LEDGER), JSON.stringify(oldLedger));
  fs.writeFileSync(path.join(second.installDir, manifest), '"buildid" "100"\n"LastUpdated" "different"');
  fs.writeFileSync(path.join(second.installDir, logicMod), "profile logic mod");
  fs.writeFileSync(path.join(template, manifest), '"buildid" "200"\n"LastUpdated" "2"');
  fs.writeFileSync(path.join(template, logicMod), "updated core logic mod");
  assert.equal(forks.baseFile("steamapps\\appmanifest_4019830.acf"), false);
  assert.equal(forks.baseFile("appmanifest_4019830.acf"), false);
  const metadataOnly = await forks.refreshFork(template, secondWorld);
  assert.equal(metadataOnly.updated, false, "Steam-only changes must not copy or block launch");
  assert.equal(metadataOnly.buildId, "200");
  assert.equal(require("../lib/steamcmd").readInstalledBuildId(second.installDir), "200", "the ledger, not a stale .acf, owns a managed build ID");
  assert.throws(() => forks.validateRoot(path.join(template, "inside"), template), /outside/);
  const secondSave = path.join(second.installDir, "RSDragonwilds", "Saved", "SaveGames", "second.sav");
  const secondMod = path.join(second.installDir, "RSDragonwilds", "Content", "Paks", "~mods", "private.pak");
  fs.mkdirSync(path.dirname(secondSave), { recursive: true });
  fs.mkdirSync(path.dirname(secondMod), { recursive: true });
  fs.writeFileSync(secondSave, "world save");
  fs.writeFileSync(secondMod, "private mod");
  fs.writeFileSync(path.join(template, "RSDragonwilds", "Content", "base.pak"), "new base");
  fs.writeFileSync(path.join(template, "RSDragonwilds", "Content", "added.bin"), "new file");
  const refreshed = await forks.refreshFork(template, secondWorld);
  assert.equal(refreshed.updated, true);
  assert.equal(refreshed.buildId, "200", "staged refresh must validate against its new ledger");
  assert.equal(fs.readFileSync(path.join(second.installDir, manifest), "utf8"), '"buildid" "100"\n"LastUpdated" "different"');
  assert.equal(fs.readFileSync(path.join(second.installDir, logicMod), "utf8"), "profile logic mod");
  assert.equal(fs.readFileSync(path.join(second.installDir, "RSDragonwilds", "Content", "base.pak"), "utf8"), "new base");
  assert.equal(fs.readFileSync(path.join(second.installDir, "RSDragonwilds", "Content", "added.bin"), "utf8"), "new file");
  assert.equal(fs.readFileSync(secondSave, "utf8"), "world save");
  assert.equal(fs.readFileSync(secondMod, "utf8"), "private mod");
  await assert.rejects(() => forks.refreshFork(template, firstWorld), /modified base files were preserved/);
  assert.equal(fs.readFileSync(path.join(first.installDir, "RSDragonwilds", "Content", "base.pak"), "utf8"), "changed");
  console.log("Server forks, legacy Steam-metadata launch regression, build IDs, conflict protection and Owner ID: OK");
}

main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
