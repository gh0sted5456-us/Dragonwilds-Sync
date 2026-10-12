const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const zlib = require("zlib");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-profile-saves-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
process.env.LOCALAPPDATA = path.join(sandbox, "LocalAppData");
const dbm = require("../lib/db");
const saves = require("../lib/profile-saves");
const converter = require("../lib/save-converter");

try {
  const publishedHash = "a".repeat(64);
  assert.equal(converter.expectedDigest(`${publishedHash} *RSDWSaveConverter-v1-win-x64.exe`, "RSDWSaveConverter-v1-win-x64.exe"), publishedHash);
  const saved = path.join(process.env.LOCALAPPDATA, "RSDragonwilds", "Saved");
  const worlds = path.join(saved, "SaveGames");
  const players = path.join(saved, "SaveCharacter");
  fs.mkdirSync(worlds, { recursive: true }); fs.mkdirSync(players, { recursive: true });
  fs.writeFileSync(path.join(worlds, "Friends.sav"), "world-a");
  fs.writeFileSync(path.join(players, "Player.json"), '{"player":"agnostic-v1"}');
  for (const profileId of ["world-a", "world-b"]) dbm.upsertProfile({ profile_id: profileId, display_name: profileId, server_world_id: profileId, client_install: null, connection: { service: "steam", savePath: saved } });

  const discovered = saves.scan("world-a");
  const worldSource = discovered.discoveries.find((item) => item.kind === "world");
  const playerSource = discovered.discoveries.find((item) => item.kind === "player");
  assert(worldSource && playerSource, "World and player saves were not detected");
  const managedWorld = saves.adopt({ ...worldSource, scope: "world", profileId: "world-a" });
  const agnostic = saves.adopt({ ...playerSource, scope: "agnostic", profileId: "world-a" });
  assert.equal(agnostic.assignment.scope, "agnostic");
  assert.equal(saves.activateForProfile("world-a").world.id, managedWorld.id);

  const alternate = path.join(sandbox, "alternate", "SaveCharacters");
  fs.mkdirSync(alternate, { recursive: true });
  fs.writeFileSync(path.join(alternate, "Player.json"), '{"player":"world-b"}');
  const specific = saves.adopt({ sourcePath: alternate, kind: "player", scope: "world", profileId: "world-b" });
  fs.writeFileSync(path.join(players, "Player.json"), '{"player":"agnostic-progress"}');
  const b = saves.activateForProfile("world-b");
  assert.equal(b.player.id, specific.id);
  assert.match(fs.readFileSync(path.join(players, "Player.json"), "utf8"), /world-b/, "World-specific player bundle was not activated");
  const a = saves.activateForProfile("world-a");
  assert.equal(a.player.scope, "agnostic");
  assert.match(fs.readFileSync(path.join(players, "Player.json"), "utf8"), /agnostic-progress/, "Outgoing agnostic player progress was not retained");
  assert.equal(fs.readFileSync(path.join(worlds, "Friends.sav"), "utf8"), "world-a");

  const scannedWorld = path.join(worlds, "Scanned World.sav");
  fs.writeFileSync(scannedWorld, "SAVE-scanned-world");
  const created = saves.createProfileFromSave({ sourcePath: scannedWorld, service: "steam" });
  const createdConnection = JSON.parse(created.profile.connection_json);
  assert(createdConnection.localWorld, "Scanned save did not create a local World profile");
  assert.equal(created.save.assignment.profileId, created.profile.profile_id, "Scanned save was not assigned to its new World profile");

  const wgs = path.join(sandbox, "Packages", "Jagex.Dragonwilds", "SystemAppData", "wgs");
  const wgsSlot = path.join(wgs, "account", "0123456789ABCDEF");
  fs.mkdirSync(wgsSlot, { recursive: true }); fs.writeFileSync(path.join(wgs, "container.1"), "opaque");
  const rawWorld = Buffer.from("SAVEgame-pass-world");
  const header = Buffer.alloc(12); header.writeUInt32LE(12, 0); header.writeUInt32LE(65536, 4); header.writeUInt32LE(rawWorld.length, 8);
  fs.writeFileSync(path.join(wgsSlot, "AABBCCDD"), Buffer.concat([header, zlib.deflateSync(rawWorld)]));
  fs.writeFileSync(path.join(wgsSlot, "EEFF0011"), JSON.stringify({ meta_data: { char_name: "GamePass Hero" }, GameProgress: { level: 4 }, Version: 1 }));
  const gamepass = saves.scan("world-a", [wgs]).discoveries.find((item) => item.kind === "wgs");
  assert(gamepass && !gamepass.manageable && gamepass.extractable, "Game Pass WGS container was not safely marked read-only/extractable");
  const extracted = saves.extractWgs(wgs);
  assert.equal(extracted.worlds, 1); assert.equal(extracted.players, 1);
  const extractedWorld = extracted.imported.find((item) => item.kind === "world");
  const extractedPlayer = extracted.imported.find((item) => item.kind === "player");
  assert.equal(extractedWorld.assignment, null); assert.equal(extractedPlayer.assignment, null);
  assert.equal(fs.readFileSync(path.join(extractedWorld.vault, extractedWorld.name), "utf8"), rawWorld.toString("utf8"));
  assert(fs.existsSync(path.join(extractedPlayer.vault, "SaveCharacter", "GamePass Hero.json")));
  console.log("Profile-owned world and player saves: OK");
} finally {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
}
