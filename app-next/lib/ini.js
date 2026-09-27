// lib/ini.js
// Dragonwilds uses a simple DedicatedServer.ini file under the game's Saved
// folder. This module locates that file per-OS and provides read/write access
// for the in-app editor and programmatic updates (ports, passwords, REST API).
const fs = require("fs");
const path = require("path");
const os = require("os");

function serverConfigDir(installDir, platform) {
  // New Dragonwilds layout: installDir/RSDragonwilds/Saved/Config/WindowsServer|LinuxServer
  const plat = platform === "windows" || platform === "linux"
    ? platform
    : (os.platform() === "win32" ? "windows" : "linux");
  const flavor = plat === "windows" ? "WindowsServer" : "LinuxServer";
  return path.join(installDir, "RSDragonwilds", "Saved", "Config", flavor);
}
function settingsIniPath(installDir, platform) {
  return path.join(serverConfigDir(installDir, platform), "DedicatedServer.ini");
}
function defaultIniPath(installDir) {
  // Shipped default template lives at install root.
  return path.join(installDir, "DefaultDedicatedServer.ini");
}

// Parse OptionSettings=(...) into { key: value } preserving string quotes.
// New Dragonwilds DedicatedServer.ini is a simple INI with header and key=value
// pairs. Parse the DedicatedServer.ini into a flat object of strings.
function parseOptionSettings(text) {
  const lines = String(text || "").split(/\r?\n/).map((l) => l.trim());
  const result = {};
  for (const line of lines) {
    if (!line || line.startsWith("#") || line.startsWith(";") || line.startsWith("[")) continue;
    const idx = line.indexOf("=");
    if (idx <= 0) continue;
    const k = line.slice(0, idx).trim();
    let v = line.slice(idx + 1).trim();
    // Strip optional surrounding quotes
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
    result[k] = v;
  }
  return result;
}

function serializeOptionSettings(obj) {
  // Write a simple INI under the required header. Values will be quoted where
  // they contain spaces.
  const lines = ["[/Script/Dominion.DedicatedServerSettings]"];
  for (const [k, v] of Object.entries(obj)) {
    const sval = typeof v === "string" && /\s/.test(v) ? `"${v}"` : String(v);
    lines.push(`${k}=${sval}`);
  }
  return lines.join("\n") + "\n";
}

function readSettings(installDir, platform) {
  const p = settingsIniPath(installDir, platform);
  let raw;
  if (fs.existsSync(p)) raw = fs.readFileSync(p, "utf8");
  else if (fs.existsSync(defaultIniPath(installDir)))
    raw = fs.readFileSync(defaultIniPath(installDir), "utf8");
  else return { path: p, exists: false, options: {} };
  return { path: p, exists: true, options: parseOptionSettings(raw) };
}

function writeSettings(installDir, options, platform) {
  const p = settingsIniPath(installDir, platform);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, serializeOptionSettings(options), "utf8");
  return p;
}

// Raw file access for the in-app text editor. Returns the exact bytes on disk
// (falling back to the shipped default template if the world's ini doesn't exist
// yet), so the editor round-trips comments and key order untouched.
function readRawSettings(installDir, platform) {
  const p = settingsIniPath(installDir, platform);
  if (fs.existsSync(p)) return { path: p, exists: true, content: fs.readFileSync(p, "utf8") };
  const dp = defaultIniPath(installDir);
  if (fs.existsSync(dp)) return { path: p, exists: false, content: fs.readFileSync(dp, "utf8") };
  return { path: p, exists: false, content: "" };
}
function writeRawSettings(installDir, content, platform) {
  const p = settingsIniPath(installDir, platform);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, content, "utf8");
  return p;
}

// Re-apply this world's own ports + password (spec §2 step 7, §3 step 6).
// PublicPort/PublicIP are the address advertised to the community server browser.
// They default to the game (listen) port / auto-detect, but the user can override
// them in Settings → Server Identity (e.g. a playit.gg tunnel address), so we only
// force PublicPort back to the game port on a fresh install or an explicit port
// change (syncPublicPort) — otherwise a routine save would clobber a tunnel port.
function applyWorldNetworkSettings(installDir, world, { syncPublicPort = false } = {}) {
  const { options } = readSettings(installDir, world.platform);
  if (syncPublicPort || options.PublicPort == null) options.PublicPort = String(world.game_port);
  options.RESTAPIPort = String(world.rest_api_port);
  options.RESTAPIEnabled = world.rest_api_enabled ? "True" : "False";
  // RCON is deprecated by Pocketpair and scheduled to stop functioning. Off by
  // default; only written when a world explicitly opts into legacy RCON.
  if (world.rcon_enabled) {
    options.RCONPort = String(world.rcon_port);
    options.RCONEnabled = "True";
  } else {
    options.RCONEnabled = "False";
  }
  // Core Dragonwilds identity fields
  options.OwnerId = world.owner_id || "";
  options.ServerName = world.display_name || "";
  options.DefaultWorldName = world.default_world_name || "";
  // Admin and player join passwords. Empty string = open server (anyone can join).
  options.AdminPassword = world.admin_password || "";
  options.WorldPassword = world.server_password || "";
  // Leave a user-set PublicIP alone; only seed a blank (auto-detect) default.
  if (options.PublicIP == null) options.PublicIP = '""';
  return writeSettings(installDir, options, world.platform);
}

module.exports = {
  serverConfigDir, settingsIniPath, defaultIniPath,
  parseOptionSettings, serializeOptionSettings,
  readSettings, writeSettings, readRawSettings, writeRawSettings,
  applyWorldNetworkSettings,
};
