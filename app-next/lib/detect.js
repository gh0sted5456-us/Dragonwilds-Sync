// lib/detect.js
// Detect and validate an existing Dragonwilds dedicated server install so users can
// register a server they already downloaded (via SteamCMD, Steam client, or a host)
// instead of installing a fresh copy.
const fs = require("fs");
const path = require("path");
const os = require("os");
const steam = require("./steamcmd");

// Given a directory (or a path to RSDragonwildsServer.exe/.sh), resolve the install root.
function resolveInstallDir(inputPath) {
  if (!inputPath) return null;
  let p = inputPath.trim().replace(/["']/g, "");
  if (!fs.existsSync(p)) return null;
  const stat = fs.statSync(p);
  if (stat.isFile()) {
    const base = path.basename(p).toLowerCase();
    if (base === "rsdragonwildsserver.exe" || base === "rsdragonwildsserver.sh") return path.dirname(p);
    return null;
  }
  return p;
}

function serverBinaryIn(dir) {
  const win = path.join(dir, "RSDragonwildsServer.exe");
  const lin = path.join(dir, "RSDragonwildsServer.sh");
  if (fs.existsSync(win)) return { path: win, os: "win32" };
  if (fs.existsSync(lin)) return { path: lin, os: "linux" };
  return null;
}

// Inspect a folder and report whether it's a usable Dragonwilds server install.
function inspect(inputPath) {
  const dir = resolveInstallDir(inputPath);
  if (!dir) return { valid: false, reason: "Path not found." };

  const bin = serverBinaryIn(dir);
  if (!bin) {
    return { valid: false, reason: "No RSDragonwildsServer.exe or RSDragonwildsServer.sh found in that folder." };
  }

  const buildId = steam.readInstalledBuildId(dir); // may be null if no steam manifest
  const projectDir = path.join(dir, "RSDragonwilds");
  const binariesDir = path.join(projectDir, "Binaries");
  const contentDir = path.join(projectDir, "Content");
  const savedDir = path.join(projectDir, "Saved");
  const missing = [
    !fs.existsSync(binariesDir) && "RSDragonwilds/Binaries",
    !fs.existsSync(contentDir) && "RSDragonwilds/Content",
  ].filter(Boolean);
  if (missing.length) {
    return { valid: false, reason: `The server executable was found, but the installation is incomplete (missing ${missing.join(", ")}). Use SteamCMD Validate / Update to repair it.`, installDir: dir, binary: bin.path, platform: bin.os === "win32" ? "windows" : "linux", missing };
  }
  const hasSave = fs.existsSync(path.join(savedDir, "SaveGames"));

  // Same value in the "windows"/"linux" vocabulary used by the worlds.platform
  // column and steamcmd.js, so callers can pass this straight into createProfile.
  // Computed here (not just at the end) so the ini read below looks in the right
  // Config/WindowsServer vs Config/LinuxServer folder for *this* binary — there's
  // no DB row yet at this point, so the binary we just found is the only signal.
  const platform = bin.os === "win32" ? "windows" : "linux";

  // detect existing settings (server name) for a nicer default display name
  let serverName = null;
  try {
    const ini = require("./ini");
    const s = ini.readSettings(dir, platform);
    if (s.exists && s.options.ServerName) {
      serverName = String(s.options.ServerName).replace(/^"|"$/g, "");
    }
  } catch {}

  return {
    valid: true,
    installDir: dir,
    binary: bin.path,
    binaryOs: bin.os,
    platform,
    buildId,
    hasExistingSave: hasSave,
    serverName,
    matchesHostOs: bin.os === (os.platform() === "win32" ? "win32" : "linux"),
    paths: {
      root: dir,
      binary: bin.path,
      project: projectDir,
      binaries: binariesDir,
      content: contentDir,
      saved: savedDir,
      saveGames: path.join(savedDir, "SaveGames"),
    },
  };
}

module.exports = { inspect, resolveInstallDir, serverBinaryIn };
