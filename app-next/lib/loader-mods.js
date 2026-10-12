const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const MAX_LIST_BYTES = 2 * 1024 * 1024;

function listFile(modsDir, kind) {
  if (kind === "runeschema") return path.join(modsDir, "RuneSchema", "runeschema.txt");
  if (kind === "ue4ss") return path.join(modsDir, "mods.txt");
  throw new Error("Unsupported mod loader");
}

function entryName(name) {
  const value = String(name || "").trim();
  if (!value || value === "." || value === ".." || /[\\/:*?"<>|\r\n]/.test(value)) throw new Error("Invalid mod folder name");
  return value;
}

function readList(file) {
  try {
    if (fs.statSync(file).size > MAX_LIST_BYTES) throw new Error("Mod loader list is too large to edit safely");
    return fs.readFileSync(file, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return "";
    throw error;
  }
}

function parseEntry(line) {
  const match = line.match(/^(\s*)([^\s;#][^:]*?)(\s*:\s*)([01])(\s*(?:[;#].*)?)$/);
  return match ? { name: match[2].trim(), enabled: match[4] === "1", match } : null;
}

function listedState(content, name) {
  let state = null;
  for (const line of content.split(/\r?\n/)) {
    const entry = parseEntry(line);
    if (entry && entry.name.toLowerCase() === name.toLowerCase()) state = entry.enabled;
  }
  return state;
}

function readControlList(modsDir, kind) {
  return readList(listFile(modsDir, kind));
}

function state(modsDir, kind, name, modPath, listText) {
  const safeName = entryName(name);
  const file = listFile(modsDir, kind);
  const listed = listedState(listText === undefined ? readList(file) : listText, safeName);
  const marker = kind === "ue4ss" && modPath && fs.existsSync(path.join(modPath, "enabled.txt"));
  return {
    loaderEnabled: marker ? true : listed,
    loaderStateSource: marker ? "enabled.txt" : listed === null ? "unlisted" : path.basename(file),
    loaderListFile: file,
    loaderEntryName: safeName,
  };
}

function updateText(content, name, enabled) {
  const newline = content.includes("\r\n") ? "\r\n" : "\n";
  const lines = content ? content.split(/\r?\n/) : [];
  let found = false;
  const output = [];
  for (const line of lines) {
    const entry = parseEntry(line);
    if (!entry || entry.name.toLowerCase() !== name.toLowerCase()) { output.push(line); continue; }
    if (found) continue; // Remove duplicate control entries so the resulting state is unambiguous.
    const parts = entry.match;
    output.push(`${parts[1]}${parts[2]}${parts[3]}${enabled ? "1" : "0"}${parts[5]}`);
    found = true;
  }
  if (!found) {
    // UE4SS keeps its built-in Keybinds entry at the end of mods.txt.
    let keybinds = kindLineIndex(output, "Keybinds");
    const inserted = `${name} : ${enabled ? "1" : "0"}`;
    if (keybinds >= 0) {
      while (keybinds > 0 && /^\s*(?:[;#].*)?$/.test(output[keybinds - 1])) keybinds--;
      output.splice(keybinds, 0, inserted);
    }
    else {
      if (output.length && output[output.length - 1] === "") output.splice(output.length - 1, 0, inserted);
      else output.push(inserted);
    }
  }
  return output.join(newline) + (!content ? newline : "");
}

function kindLineIndex(lines, name) {
  return lines.findIndex((line) => parseEntry(line)?.name.toLowerCase() === name.toLowerCase());
}

function atomicWrite(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temporary = `${file}.rsdw-${crypto.randomBytes(6).toString("hex")}.tmp`;
  try {
    fs.writeFileSync(temporary, content, { encoding: "utf8", flag: "wx" });
    fs.renameSync(temporary, file);
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

function setEnabled(modsDir, kind, name, modPath, enabled) {
  const safeName = entryName(name);
  if (typeof enabled !== "boolean") throw new Error("Enabled must be true or false");
  const file = listFile(modsDir, kind);
  const before = readList(file);
  const after = updateText(before, safeName, enabled);
  const marker = kind === "ue4ss" ? path.join(modPath, "enabled.txt") : null;
  const parked = marker ? `${marker}.rsdw-disabled` : null;
  let movedMarker = false;
  if (!enabled && marker && fs.existsSync(marker)) {
    if (fs.existsSync(parked)) throw new Error("Both enabled.txt and its parked copy exist; resolve them before disabling this mod");
    fs.renameSync(marker, parked);
    movedMarker = true;
  }
  try { if (after !== before) atomicWrite(file, after); }
  catch (error) {
    if (movedMarker) fs.renameSync(parked, marker);
    throw error;
  }
  if (enabled && marker && !fs.existsSync(marker) && fs.existsSync(parked)) fs.renameSync(parked, marker);
  const result = state(modsDir, kind, safeName, modPath);
  if (result.loaderEnabled !== enabled) throw new Error("Mod loader state could not be verified after saving");
  return result;
}

module.exports = { state, setEnabled, readControlList, updateText };
