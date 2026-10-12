const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const steamlib = require("../lib/steamlibrary");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-client-service-"));

function makeInstall(root, binaryLane = "Win64") {
  const binaries = path.join(root, "RSDragonwilds", "Binaries", binaryLane);
  fs.mkdirSync(binaries, { recursive: true });
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Content"), { recursive: true });
  const executable = path.join(binaries, `RSDragonwilds-${binaryLane}-Shipping.exe`);
  fs.writeFileSync(executable, "test");
  return executable;
}

try {
  const steamRoot = path.join(sandbox, "SteamLibrary", "steamapps", "common", "RuneScape Dragonwilds");
  const epicRoot = path.join(sandbox, "Epic Games", "RuneScape Dragonwilds");
  const gamePassRoot = path.join(sandbox, "XboxGames", "RuneScape- Dragonwilds", "Content");
  const steamExe = makeInstall(steamRoot);
  const epicExe = makeInstall(epicRoot);
  const gamePassExe = makeInstall(gamePassRoot, "WinGDK");
  fs.mkdirSync(path.join(epicRoot, ".egstore"), { recursive: true });

  const steam = steamlib.resolveClientInstallation(steamExe, { preferred: "epic" });
  const epic = steamlib.resolveClientInstallation(epicRoot, { preferred: "steam" });
  const gamepass = steamlib.resolveClientInstallation(gamePassRoot, { savePath: path.join(sandbox, "Packages", "Jagex.Dragonwilds", "SystemAppData", "wgs") });

  assert.equal(steam.service, "steam", "Steam library path should win over a stale manual preference");
  assert.equal(epic.service, "epic", "Epic library path was not detected");
  assert.equal(gamepass.service, "gamepass", "Xbox/WinGDK install was not detected");
  assert.equal(gamepass.modPlatform, "gamepass", "Game Pass should use the WinGDK manifest lane");
  assert.equal(epic.modPlatform, "steam", "Epic should share the Win64 manifest lane");
  assert.equal(path.normalize(steam.executablePath), path.normalize(steamExe));
  assert.equal(path.normalize(epic.executablePath), path.normalize(epicExe));
  assert.equal(path.normalize(gamepass.executablePath), path.normalize(gamePassExe));
  console.log("Client service detection: OK");
} finally {
  fs.rmSync(sandbox, { recursive: true, force: true });
}
