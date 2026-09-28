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

function formatIniValue(value) {
  const v = value == null ? "" : String(value);
  return /\s/.test(v) ? `"${v.replace(/"/g, '\\"')}"` : v;
}

function serializeOptionSettings(obj) {
  const lines = ["[/Script/Dominion.DedicatedServerSettings]"];
  for (const [k, v] of Object.entries(obj)) lines.push(`${k}=${formatIniValue(v)}`);
  return lines.join("\n") + "\n";
}

function patchRawSettings(raw, updates) {
  const input = String(raw || "");
  const newline = input.includes("\r\n") ? "\r\n" : "\n";
  const lines = input ? input.split(/\r?\n/) : ["[/Script/Dominion.DedicatedServerSettings]"];
  if (!lines.some((line) => /^\s*\[\/Script\/Dominion\.DedicatedServerSettings\]\s*$/i.test(line))) {
    lines.unshift("[/Script/Dominion.DedicatedServerSettings]");
  }
  for (const [key, value] of Object.entries(updates || {})) {
    let found = false;
    for (let i = 0; i < lines.length; i++) {
      const match = lines[i].match(/^(\s*)([^;#=][^=]*?)(\s*=\s*)(.*)$/);
      if (!match || match[2].trim().toLowerCase() !== String(key).toLowerCase()) continue;
      lines[i] = `${match[1]}${match[2]}${match[3]}${formatIniValue(value)}`;
      found = true;
    }
    if (!found) lines.push(`${key}=${formatIniValue(value)}`);
  }
  while (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines.join(newline) + newline;
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
function withWorldNetworkSettings(options, world, { syncPublicPort = false } = {}) {
  const next = { ...(options || {}) };
  if (syncPublicPort || next.PublicPort == null || String(next.PublicPort).trim() === "") next.PublicPort = String(world.game_port);
  next.RESTAPIPort = String(world.rest_api_port);
  next.RESTAPIEnabled = world.rest_api_enabled ? "True" : "False";
  if (world.rcon_enabled) {
    next.RCONPort = String(world.rcon_port);
    next.RCONEnabled = "True";
  } else {
    next.RCONEnabled = "False";
  }
  next.OwnerId = world.owner_id || "";
  next.ServerName = world.display_name || "";
  next.DefaultWorldName = world.default_world_name || "";
  next.AdminPassword = world.admin_password || "";
  next.WorldPassword = world.server_password || "";
  if (next.PublicIP == null) next.PublicIP = '""';
  return next;
}

function applyWorldNetworkSettings(installDir, world, opts = {}) {
  const current = readRawSettings(installDir, world.platform);
  const options = withWorldNetworkSettings(parseOptionSettings(current.content), world, opts);
  return writeRawSettings(installDir, patchRawSettings(current.content, options), world.platform);
}

module.exports = {
  serverConfigDir, settingsIniPath, defaultIniPath,
  parseOptionSettings, serializeOptionSettings, patchRawSettings,
  readSettings, writeSettings, readRawSettings, writeRawSettings,
  withWorldNetworkSettings, applyWorldNetworkSettings,
};
