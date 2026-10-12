const assert = require("assert");
const fs = require("fs");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(__dirname, ".client-isolation-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const isolation = require("../lib/client-isolation");
const client = require("../lib/sync/client");
const install = path.join(sandbox, "Dragonwilds");
const pak = path.join(install, "RSDragonwilds", "Content", "Paks", "~mods", "Original.pak");
const loader = path.join(install, "RSDragonwilds", "Binaries", "Win64", "dwmapi.dll");
fs.mkdirSync(path.dirname(pak), { recursive: true });
fs.mkdirSync(path.join(install, "RSDragonwilds", "Binaries", "Win64"), { recursive: true });
fs.writeFileSync(pak, "original-mod");
fs.writeFileSync(loader, "loader-runtime");
dbm.setSetting("clientInstall:steam", install);
dbm.upsertProfile({ profile_id: "local-test", display_name: "Local test", connection: { localWorld: true, service: "steam" }, client_install: install });

(async () => {
  const first = isolation.scan(install, "steam");
  assert.equal(first.entries.length, 1);
  assert(!first.ready);
  await assert.rejects(isolation.archive(install, "steam", "0".repeat(64), { processes: [] }), /inventory changed/i);
  assert(fs.existsSync(pak), "a rejected archive changed the game file");
  const archived = await isolation.archive(install, "steam", first.fingerprint, { processes: [] });
  assert.equal(archived.fileCount, 1);
  assert(!fs.existsSync(pak));
  assert.equal(fs.readFileSync(loader, "utf8"), "loader-runtime", "shared loader was unexpectedly removed");
  assert(isolation.scan(install, "steam").ready);
  const fork = await isolation.ensureLocalProfileSnapshot("local-test");
  assert(fork.created);
  const cached = path.join(fork.snapshot, "RSDragonwilds", "Content", "Paks", "~mods", "Original.pak");
  assert.equal(fs.readFileSync(cached, "utf8"), "original-mod");
  const activation = await client.activateProfileSnapshot("local-test");
  assert.equal(activation.changed, 1);
  assert.equal(fs.readFileSync(pak, "utf8"), "original-mod");
  assert(isolation.scan(install, "steam").ready, "managed projection was mistaken for an unmanaged file");
  fs.writeFileSync(pak, "edited-mod");
  assert(!isolation.scan(install, "steam").ready, "an edited managed file was not detected");
  await assert.rejects(isolation.restore(install, "steam", { processes: [] }), /changed|overwrite/i);
  fs.writeFileSync(pak, "original-mod");
  const restored = await isolation.restore(install, "steam", { processes: [] });
  assert.equal(restored.fileCount, 1);
  assert.equal(fs.readFileSync(pak, "utf8"), "original-mod");
  assert.equal(isolation.scan(install, "steam").entries.length, 1, "native original was not restored");
  console.log("Client Safe Storage and local World fork: OK");
})().finally(() => {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
