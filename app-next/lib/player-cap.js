// A dedicated World's player cap belongs to Game.ini, not DedicatedServer.ini.
// Keep the choice per profile and write only MaxPlayers into the shared game tree.
const fs = require("fs");
const path = require("path");
const dbm = require("./db");
const ini = require("./ini");

const SECTION = "[/Script/Engine.GameSession]";
const profileKey = (worldId) => `serverProfilePlayerCap:${worldId}`;

function validate(value) {
  const text = typeof value === "number" && Number.isInteger(value) ? String(value) :
    typeof value === "string" ? value.trim() : "";
  if (!/^[1-9]\d*$/.test(text) || Number(text) > 128) {
    throw new Error("Player cap must be a whole number from 1 to 128.");
  }
  return Number(text);
}

function read(content) {
  let active = false;
  const values = [];
  for (const raw of String(content || "").split(/\r?\n/)) {
    const line = raw.trim().replace(/^\uFEFF/, "");
    if (/^\[[^\]]+\]$/.test(line)) {
      active = line.toLowerCase() === SECTION.toLowerCase();
    } else if (active && !/^[;#]/.test(line) && /^MaxPlayers\s*=/i.test(line)) {
      values.push(validate(line.split("=", 2)[1]));
    }
  }
  if (values.length > 1) throw new Error("Game.ini has more than one GameSession MaxPlayers value.");
  return values[0] ?? null;
}

function patch(content, value) {
  const cap = validate(value);
  const original = String(content || "");
  const newline = original.includes("\r\n") ? "\r\n" : "\n";
  const lines = original ? original.split(/\r?\n/) : [];
  const output = [];
  let active = false;
  let inserted = false;
  for (const line of lines) {
    const trimmed = line.trim().replace(/^\uFEFF/, "");
    if (/^\[[^\]]+\]$/.test(trimmed)) {
      active = trimmed.toLowerCase() === SECTION.toLowerCase();
      output.push(line);
      if (active && !inserted) {
        output.push(`MaxPlayers=${cap}`);
        inserted = true;
      }
      continue;
    }
    if (active && !/^[;#]/.test(trimmed) && /^MaxPlayers\s*=/i.test(trimmed)) continue;
    output.push(line);
  }
  if (!inserted) {
    if (output.length && output[output.length - 1].trim()) output.push("");
    output.push(SECTION, `MaxPlayers=${cap}`);
  }
  return output.join(newline).replace(/(?:\r?\n)+$/, "") + newline;
}

function gameIniPath(world) {
  if (!world?.install_dir) throw new Error("Choose a dedicated server installation first.");
  return path.join(ini.serverConfigDir(world.install_dir, world.platform), "Game.ini");
}

function settingsFor(worldOrId) {
  const world = typeof worldOrId === "object" ? worldOrId : dbm.getWorld(worldOrId);
  if (!world) throw new Error("Server World not found.");
  const file = gameIniPath(world);
  const saved = dbm.getSetting(profileKey(world.world_id), null);
  let cap;
  if (saved !== null && saved !== undefined) {
    cap = validate(saved);
  } else {
    // Adopt an existing Game.ini only when it cannot belong to another active
    // World. A newly added, inactive profile starts at the documented default.
    const activeId = dbm.getSetting("activeServerWorldId", "");
    const canAdopt = !activeId || activeId === world.world_id;
    try { cap = canAdopt && fs.existsSync(file) ? (read(fs.readFileSync(file, "utf8")) ?? 6) : 6; }
    catch { cap = 6; } // Let the in-app editor repair an invalid or duplicate live value.
    dbm.setSetting(profileKey(world.world_id), cap);
  }
  return { path: file, maxPlayers: cap, content: fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "", exists: fs.existsSync(file) };
}

function save(worldId, value) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("Server World not found.");
  const cap = validate(value);
  dbm.setSetting(profileKey(worldId), cap);
  return settingsFor(world);
}

function materialize(worldOrId) {
  const world = typeof worldOrId === "object" ? worldOrId : dbm.getWorld(worldOrId);
  const settings = settingsFor(world);
  const next = patch(settings.content, settings.maxPlayers);
  ini.writeVerifiedFile(settings.path, next);
  if (read(fs.readFileSync(settings.path, "utf8")) !== settings.maxPlayers) {
    throw new Error(`Player cap did not persist in ${settings.path}`);
  }
  return { ...settings, content: next, exists: true };
}

module.exports = { SECTION, profileKey, validate, read, patch, gameIniPath, settingsFor, save, materialize };
