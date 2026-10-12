const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-server-forks-"));
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
  assert.throws(() => forks.validateRoot(path.join(template, "inside"), template), /outside/);
  console.log("Server forks and inherited Owner ID: OK");
}

main().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
