const assert = require("assert");
const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-player-cache-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const client = require("../lib/sync/client");
const syncManifest = require("../lib/sync/manifest");
const syncAuth = require("../lib/sync/auth");

const install = path.join(sandbox, "game");
let hostA = null, hostB = null;
fs.mkdirSync(path.join(install, "RSDragonwilds", "Binaries", "Win64"), { recursive: true });
fs.mkdirSync(path.join(install, "RSDragonwilds", "Content"), { recursive: true });
dbm.setSetting("clientInstall:steam", install);

function manifest(worldId, target, content) {
  const sha256 = crypto.createHash("sha256").update(content).digest("hex");
  return {
    protocol: "dragonwilds-world-sync", protocolVersion: 2, revision: `${worldId}-revision`, generatedAt: new Date().toISOString(),
    world: { id: worldId, name: worldId, type: "Private", rules: {}, identity: {} }, prerequisites: {}, clientPlatform: "steam",
    transport: { kind: "http-over-tcp", supportsDirectDownloads: true },
    units: [{ key: `pak:${worldId}`, name: worldId, type: "pak", clientRequired: true, contentHash: sha256, fileCount: 1, bytes: content.length, files: [{ target, size: content.length, sha256 }] }],
  };
}

async function serve(worldId, target, content) {
  const value = manifest(worldId, target, content);
  const server = http.createServer((req, res) => {
    if (req.url.startsWith(`/api/sync/public/${worldId}/file`)) { res.writeHead(200, { "Content-Length": content.length }); return res.end(content); }
    res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify({ ok: true, manifest: value }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return { server, port: server.address().port };
}

(async () => {
  const targetA = "RSDragonwilds/Content/Paks/~mods/ProfileA.pak";
  const targetB = "RSDragonwilds/Content/Paks/~mods/ProfileB.pak";
  hostA = await serve("world-a", targetA, Buffer.from("profile-a"));
  hostB = await serve("world-b", targetB, Buffer.from("profile-b"));
  for (const [id, worldId, port] of [["profile-a", "world-a", hostA.port], ["profile-b", "world-b", hostB.port]]) {
    dbm.upsertProfile({ profile_id: id, display_name: id, server_world_id: worldId, connection: { address: "127.0.0.1", syncPort: port, worldId, platform: "steam" } });
  }

  await client.synchronizeProfile("profile-a");
  assert(fs.existsSync(path.join(install, ...targetA.split("/"))), "profile A was not installed");
  const cachedA = path.join(process.env.APP_MANAGER_DATA_DIR, "player-profiles", "profile-a", ...targetA.split("/"));
  const projectedA = path.join(install, ...targetA.split("/"));
  assert(fs.existsSync(cachedA), "profile A was not cached");
  const [cachedStat, projectedStat] = [fs.statSync(cachedA), fs.statSync(projectedA)];
  assert(cachedStat.dev === projectedStat.dev && cachedStat.ino === projectedStat.ino, "profile A was copied instead of linked on the same filesystem");
  const deployment = JSON.parse(dbm.getProfile("profile-a").connection_json).modDeployment;
  assert.equal(deployment.mode, "linked", "linked deployment was not recorded on the World profile");

  await client.synchronizeProfile("profile-b");
  assert(!fs.existsSync(path.join(install, ...targetA.split("/"))), "profile A extras remained active after switching to B");
  assert(fs.existsSync(path.join(install, ...targetB.split("/"))), "profile B was not installed");

  await new Promise((resolve) => hostA.server.close(resolve));
  const progress = [];
  await client.synchronizeProfile("profile-a", (event) => { if (event.line) progress.push(event.line); });
  assert(fs.existsSync(path.join(install, ...targetA.split("/"))), "cached profile A was not restored offline");
  assert(!fs.existsSync(path.join(install, ...targetB.split("/"))), "profile B extras remained after cached A activation");
  assert(progress.some((line) => line.includes("profile cache")), "offline profile switch did not report cached restoration");
  const activated = await client.activateProfileSnapshot("profile-a");
  assert.equal(activated.changed, 0, "launch activation should be idempotent when the profile is already active");
  const profileA = dbm.getProfile("profile-a");
  dbm.upsertProfile({ profile_id: "profile-a", connection: { ...JSON.parse(profileA.connection_json), shareEnabled: true, shareCode: "SHARE123" } });
  const shared = syncManifest.buildProfileManifest("profile-a");
  assert.equal(shared.world.type, "Player Share", "Player cache was not exposed as a player-owned share");
  assert.equal(shared.world.id, "profile-profile-a", "Player share id was not namespaced");
  const sharedFile = syncManifest.resolveProfileFile("profile-a", targetA);
  assert.equal(fs.readFileSync(sharedFile.source, "utf8"), "profile-a", "Player share did not resolve its verified cached file");
  const request = { headers: new Headers({ "x-rsdw-world-password": "SHARE123" }) };
  assert(syncAuth.authorizeProfileRequest("profile-a", request).ok, "Player share code was rejected");
  await new Promise((resolve) => hostB.server.close(resolve));
  console.log("Client profile cache and switching: OK");
})().finally(async () => {
  for (const host of [hostA, hostB]) if (host?.server?.listening) await new Promise((resolve) => host.server.close(resolve));
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
