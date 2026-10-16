// Shared, immutable pool of Dragonwilds world saves. Server profiles receive a
// verified copy; importing here never writes to a live dedicated server.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const AdmZip = require("adm-zip");
const dbm = require("./db");
const { P } = require("./paths");
const { trashPath } = require("./trash");

const CATALOG_KEY = "worldRepository:v1";
const MAX_SAVE_BYTES = 512 * 1024 * 1024;
const WORLD_TYPES = new Set(["Standard", "HardMode", "Creative", "Custom"]);

function catalog() {
  const saved = dbm.getSetting(CATALOG_KEY, { items: [] });
  return Array.isArray(saved?.items) ? saved.items : [];
}

function saveCatalog(items) {
  dbm.setSetting(CATALOG_KEY, { items, updatedAt: Date.now() });
}

function repositoryPath(id) {
  if (!/^[a-f0-9]{24}$/.test(String(id || ""))) throw new Error("Invalid repository world ID");
  return path.join(P.worldRepository(), `${id}.sav`);
}

function digestFile(file) {
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const chunk = Buffer.allocUnsafe(1024 * 1024);
  try {
    let bytes;
    while ((bytes = fs.readSync(fd, chunk, 0, chunk.length, null)) > 0) hash.update(chunk.subarray(0, bytes));
  } finally { fs.closeSync(fd); }
  return hash.digest("hex");
}

// RSDW Save Converter verifies the SAVE envelope when moving Steam/Game Pass
// worlds, but its current CLI does not report the world mode. Read only the
// known L_World difficulty enum; unknown/new values must not be guessed.
function detectWorldType(file) {
  const fd = fs.openSync(file, "r");
  try {
    const header = Buffer.alloc(4);
    if (fs.readSync(fd, header, 0, 4, 0) !== 4 || header.toString("ascii") !== "SAVE") {
      throw new Error("This is not a Dragonwilds SAVE world file");
    }
    const marker = Buffer.from("L_World\0", "ascii");
    const chunk = Buffer.allocUnsafe(1024 * 1024);
    let carry = Buffer.alloc(0);
    let offset = 0;
    const scanLimit = Math.min(fs.fstatSync(fd).size, 32 * 1024 * 1024);
    while (offset < scanLimit) {
      const bytes = fs.readSync(fd, chunk, 0, Math.min(chunk.length, scanLimit - offset), offset);
      if (!bytes) break;
      const data = Buffer.concat([carry, chunk.subarray(0, bytes)]);
      const at = data.indexOf(marker);
      if (at >= 0 && at + 13 <= data.length) {
        const value = data.readUInt32LE(at + 9);
        const type = ({ 0: "Standard", 1: "HardMode", 3: "Custom" })[value] || null;
        return { detectedWorldType: type, rawMode: value };
      }
      carry = Buffer.from(data.subarray(Math.max(0, data.length - 16)));
      offset += bytes;
    }
    return { detectedWorldType: null, rawMode: null };
  } finally { fs.closeSync(fd); }
}

function listWorlds() {
  return catalog().map((item) => ({ ...item, available: fs.existsSync(repositoryPath(item.id)) }));
}

function getWorld(id) {
  const item = catalog().find((entry) => entry.id === id);
  if (!item) throw new Error("Repository world not found");
  const file = repositoryPath(item.id);
  if (!fs.existsSync(file)) throw new Error("Repository world file is missing");
  if (digestFile(file) !== item.sha256) throw new Error("Repository world failed SHA-256 verification");
  return { ...item, file };
}

function importWorld(sourcePath) {
  const source = path.resolve(String(sourcePath || ""));
  if (!fs.existsSync(source) || !fs.statSync(source).isFile()) throw new Error("World save file not found");
  const isZip = /\.zip$/i.test(source);
  if (!isZip && !/\.sav$/i.test(source)) throw new Error("Choose a .sav file or a ZIP with one .sav");
  const temporary = path.join(P.worldRepository(), `.incoming-${crypto.randomUUID()}.sav`);
  let name = path.basename(source);
  try {
    if (isZip) {
      const entries = new AdmZip(source).getEntries().filter((entry) => !entry.isDirectory && /\.sav$/i.test(entry.entryName));
      if (entries.length !== 1) throw new Error(`ZIP must contain exactly one .sav (found ${entries.length})`);
      if (entries[0].header.size <= 0 || entries[0].header.size > MAX_SAVE_BYTES) throw new Error("World save exceeds the repository size limit");
      name = path.basename(entries[0].entryName.replace(/\\/g, "/"));
      fs.writeFileSync(temporary, entries[0].getData());
    } else {
      const size = fs.statSync(source).size;
      if (size <= 0 || size > MAX_SAVE_BYTES) throw new Error("World save exceeds the repository size limit");
      fs.copyFileSync(source, temporary);
    }
    const stat = fs.statSync(temporary);
    if (stat.size <= 0 || stat.size > MAX_SAVE_BYTES) throw new Error("World save exceeds the repository size limit");
    const mode = detectWorldType(temporary);
    const sha256 = digestFile(temporary);
    const id = sha256.slice(0, 24);
    const destination = repositoryPath(id);
    const items = catalog();
    const existing = items.find((item) => item.id === id);
    if (existing) {
      if (!fs.existsSync(destination) || digestFile(destination) !== sha256) fs.copyFileSync(temporary, destination);
      return existing;
    }
    fs.copyFileSync(temporary, destination);
    if (digestFile(destination) !== sha256) throw new Error("Could not verify the repository copy");
    const item = {
      id, name, sha256, size: stat.size, importedAt: Date.now(),
      worldType: mode.detectedWorldType, detectedWorldType: mode.detectedWorldType,
      rawMode: mode.rawMode, typeSource: mode.detectedWorldType ? "save" : "unverified",
    };
    items.push(item);
    saveCatalog(items);
    return item;
  } finally { fs.rmSync(temporary, { force: true }); }
}

function setWorldType(id, worldType) {
  if (!WORLD_TYPES.has(worldType)) throw new Error("Choose Standard, HardMode, Creative, or Custom");
  const items = catalog();
  const item = items.find((entry) => entry.id === id);
  if (!item) throw new Error("Repository world not found");
  item.worldType = worldType;
  item.typeSource = "manual";
  saveCatalog(items);
  return item;
}

function removeWorld(id) {
  const items = catalog();
  const item = items.find((entry) => entry.id === id);
  if (!item) throw new Error("Repository world not found");
  // A queued swap still needs this source. Already activated server copies are
  // independent and remain untouched when the shared repository entry goes.
  for (const world of dbm.listWorlds()) {
    if (dbm.getSetting(`pendingWorldSave:${world.world_id}`, null)?.repositoryId === id) {
      throw new Error("This world is queued for a server. Choose another world there before deleting it from the repository.");
    }
  }
  trashPath(repositoryPath(id));
  saveCatalog(items.filter((entry) => entry.id !== id));
  return item;
}

module.exports = { listWorlds, getWorld, importWorld, setWorldType, removeWorld, detectWorldType, digestFile };
