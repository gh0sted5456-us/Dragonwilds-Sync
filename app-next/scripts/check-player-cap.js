const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-player-cap-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const cap = require("../lib/player-cap");
const ini = require("../lib/ini");
const supervisor = require("../lib/supervisor");

const install = path.join(sandbox, "server");
const worlds = new Map([
  ["one", { world_id: "one", install_dir: install, platform: "windows", game_port: 7777, query_port: 27016, rest_api_port: 8080, mods_enabled: true }],
  ["two", { world_id: "two", install_dir: install, platform: "windows", game_port: 7778, query_port: 27017, rest_api_port: 8081, mods_enabled: true }],
]);
const settings = new Map([["activeServerWorldId", "one"]]);
dbm.getWorld = (id) => worlds.get(id) || null;
dbm.getSetting = (key, fallback = null) => settings.has(key) ? settings.get(key) : fallback;
dbm.setSetting = (key, value) => settings.set(key, value);

try {
  const gameIni = path.join(ini.serverConfigDir(install, "windows"), "Game.ini");
  fs.mkdirSync(path.dirname(gameIni), { recursive: true });
  fs.writeFileSync(gameIni, "; operator comment\r\n[Other]\r\nKeep=yes\r\n[/Script/Engine.GameSession]\r\nMaxPlayers=8\r\nMaxPlayers=9\r\nKeepToo=yes\r\n", "utf8");
  // Existing duplicate values are normalized when the operator saves a cap.
  assert.throws(() => cap.read(fs.readFileSync(gameIni, "utf8")), /more than one/);
  // Adopt the existing cap after a duplicate has been resolved.
  fs.writeFileSync(gameIni, fs.readFileSync(gameIni, "utf8").replace("MaxPlayers=9\r\n", ""), "utf8");
  assert.equal(cap.settingsFor(worlds.get("one")).maxPlayers, 8);
  assert.equal(cap.settingsFor(worlds.get("two")).maxPlayers, 6, "inactive World inherited another profile's cap");
  cap.save("one", 12);
  cap.materialize(worlds.get("one"));
  const first = fs.readFileSync(gameIni, "utf8");
  assert.equal(cap.read(first), 12);
  assert(first.includes("; operator comment") && first.includes("[Other]\r\nKeep=yes") && first.includes("KeepToo=yes"));
  assert.equal((first.match(/MaxPlayers=/g) || []).length, 1);
  assert(supervisor.buildArgs(worlds.get("one")).includes("-ini:Game:[/Script/Engine.GameSession]:MaxPlayers=12"));
  cap.save("two", 4);
  cap.materialize(worlds.get("two"));
  assert.equal(cap.read(fs.readFileSync(gameIni, "utf8")), 4);
  cap.materialize(worlds.get("one"));
  assert.equal(cap.read(fs.readFileSync(gameIni, "utf8")), 12, "profile rotation lost the first World's cap");
  for (const invalid of [0, 129, true, 1.5, "bad", ""]) assert.throws(() => cap.validate(invalid), /whole number/);
  console.log("Profile-owned Game.ini player cap: OK");
} finally {
  fs.rmSync(sandbox, { recursive: true, force: true });
}
