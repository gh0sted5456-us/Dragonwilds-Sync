const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const zlib = require("zlib");
const dbm = require("./db");
const { P } = require("./paths");

const CATALOG_KEY = "profileSaveCatalog:v1";
const MAX_SCAN_ENTRIES = 5000;
const MAX_SCAN_DEPTH = 5;
const MAX_WORLD_BYTES = 512 * 1024 * 1024;
const MAX_CHARACTER_BYTES = 64 * 1024 * 1024;
const GAMEPASS_PACKAGE = "JagexLimited.Dominion_srxstwq7wczqa";
const SCAN_CACHE_MS = 10000;
const SCAN_CACHE = globalThis.__RSDW_PROFILE_SAVE_SCAN_CACHE || new Map();
globalThis.__RSDW_PROFILE_SAVE_SCAN_CACHE = SCAN_CACHE;

function idFor(kind, sourcePath) {
  return `${kind}-${crypto.createHash("sha256").update(path.resolve(sourcePath).toLowerCase()).digest("hex").slice(0, 16)}`;
}

function readCatalog() {
  const value = dbm.getSetting(CATALOG_KEY, { items: [] });
  return { items: Array.isArray(value?.items) ? value.items : [] };
}

function writeCatalog(catalog) {
  dbm.setSetting(CATALOG_KEY, { items: catalog.items, updatedAt: Date.now() });
  SCAN_CACHE.clear();
  return catalog;
}

function directoryStats(root) {
  let files = 0; let size = 0; let modifiedAt = 0;
  const pending = [root];
  while (pending.length && files < MAX_SCAN_ENTRIES) {
    const current = pending.pop();
    let entries = [];
    try { entries = fs.readdirSync(current, { withFileTypes: true }); } catch { continue; }
    for (const entry of entries) {
      if (entry.isSymbolicLink()) continue;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) pending.push(full);
      else if (entry.isFile()) {
        try { const stat = fs.statSync(full); files++; size += stat.size; modifiedAt = Math.max(modifiedAt, stat.mtimeMs); } catch {}
      }
    }
  }
  return { files, size, modifiedAt };
}

function defaultRoots(profileId) {
  const roots = [];
  const local = process.env.LOCALAPPDATA;
  if (local) {
    roots.push(path.join(local, "RSDragonwilds", "Saved"));
    const wgs = path.join(local, "Packages", GAMEPASS_PACKAGE, "SystemAppData", "wgs");
    if (fs.existsSync(wgs)) roots.push(wgs);
  }
  const profile = profileId ? dbm.getProfile(profileId) : null;
  if (profile) {
    try {
      const connection = JSON.parse(profile.connection_json || "{}");
      if (connection.savePath) roots.push(path.resolve(connection.savePath));
    } catch {}
  }
  return [...new Set(roots.map((root) => path.resolve(root)))];
}

function scan(profileId, extraRoots = []) {
  const discoveries = new Map();
  const candidates = [...new Set([...defaultRoots(profileId), ...(extraRoots || []).filter(Boolean).map((root) => path.resolve(String(root)))])];
  const roots = candidates.filter((root) => !candidates.some((other) => other !== root && root.toLowerCase().startsWith(`${other.toLowerCase()}${path.sep}`)));
  let visited = 0;
  const addWorld = (file, service = "windows") => {
    try {
      const stat = fs.statSync(file);
      if (!stat.isFile() || !/\.sav$/i.test(file)) return;
      const id = idFor("world", file);
      discoveries.set(id, { id, kind: "world", name: path.basename(file), sourcePath: file, service, size: stat.size, files: 1, modifiedAt: stat.mtimeMs, manageable: true });
    } catch {}
  };
  const addCharacter = (dir, service = "windows") => {
    const stats = directoryStats(dir);
    if (!stats.files) return;
    const id = idFor("player", dir);
    discoveries.set(id, { id, kind: "player", name: path.basename(dir), sourcePath: dir, service, ...stats, manageable: true });
  };
  const inspect = (current, depth, service) => {
    if (visited++ >= MAX_SCAN_ENTRIES || depth > MAX_SCAN_DEPTH) return;
    let stat;
    try { stat = fs.statSync(current); } catch { return; }
    if (!stat.isDirectory()) return addWorld(current, service);
    const base = path.basename(current).toLowerCase();
    const normalized = current.replace(/\//g, "\\").toLowerCase();
    if (normalized.includes("\\systemappdata\\wgs")) {
      const id = idFor("wgs", current);
      discoveries.set(id, { id, kind: "wgs", name: "Game Pass WGS container", sourcePath: current, service: "gamepass", ...directoryStats(current), manageable: false, extractable: true, note: "World and character payloads can be extracted read-only. Writing back uses the verified RSDW Save Converter." });
      return;
    }
    if (base === "savegames") {
      for (const entry of fs.readdirSync(current, { withFileTypes: true })) if (entry.isFile()) addWorld(path.join(current, entry.name), service);
      return;
    }
    if (base === "savecharacter" || base === "savecharacters") return addCharacter(current, service);
    let entries = [];
    try { entries = fs.readdirSync(current, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      if (visited >= MAX_SCAN_ENTRIES || entry.isSymbolicLink()) break;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) inspect(full, depth + 1, service);
      else if (entry.isFile() && /\.sav$/i.test(entry.name) && base === "savegames") addWorld(full, service);
    }
  };
  for (const root of roots) inspect(root, 0, /\\(xboxgames|windowsapps|wpsystem)\\/i.test(root.replace(/\//g, "\\")) ? "gamepass" : "windows");
  const catalog = readCatalog();
  return { roots, discoveries: [...discoveries.values()].map((item) => ({ ...item, managed: catalog.items.some((saved) => saved.id === item.id) })), managed: catalog.items };
}

function scanCached(profileId, extraRoots = []) {
  const key = JSON.stringify([profileId || null, (extraRoots || []).map((root) => path.resolve(String(root))).sort()]);
  const cached = SCAN_CACHE.get(key);
  if (cached && Date.now() - cached.at < SCAN_CACHE_MS) return cached.value;
  const value = scan(profileId, extraRoots);
  SCAN_CACHE.set(key, { at: Date.now(), value });
  return value;
}

function characterMetadata(data) {
  if (!data.length || data.length > MAX_CHARACTER_BYTES) return null;
  try {
    const text = data.toString("utf8").replace(/^\uFEFF/, "").trimStart();
    if (!text.startsWith("{")) return null;
    const parsed = JSON.parse(text);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") return null;
    const find = (object, key) => Object.entries(object || {}).find(([name]) => name.toLowerCase() === key.toLowerCase())?.[1];
    const metadata = find(parsed, "meta_data");
    const progress = find(parsed, "GameProgress");
    if (!metadata || typeof metadata !== "object" || !progress || typeof progress !== "object") return null;
    const name = find(metadata, "char_name");
    return { name: typeof name === "string" && name.trim() ? name.trim().slice(0, 96) : "Game Pass Character" };
  } catch { return null; }
}

function unwrapWgsWorld(data) {
  if (data.length < 14 || data.readUInt32LE(0) !== 12 || data.readUInt32LE(4) !== 65536 || data[12] !== 0x78) return null;
  const expected = data.readUInt32LE(8);
  if (!expected || expected > MAX_WORLD_BYTES) throw new Error("A Game Pass world payload declared an unsafe uncompressed size");
  const raw = zlib.inflateSync(data.subarray(12), { maxOutputLength: MAX_WORLD_BYTES });
  if (raw.length !== expected || raw.subarray(0, 4).toString("ascii") !== "SAVE") throw new Error("A Game Pass world payload failed SAVE signature or length verification");
  return raw;
}

function discoverWgsPayloads(root) {
  const found = [];
  const hashes = new Set();
  const pending = [{ value: path.resolve(root), depth: 0 }];
  let visited = 0;
  while (pending.length && visited++ < MAX_SCAN_ENTRIES) {
    const { value, depth } = pending.pop();
    let entries = [];
    try { entries = fs.readdirSync(value, { withFileTypes: true }); } catch { continue; }
    for (const entry of entries) {
      if (entry.isSymbolicLink()) continue;
      const full = path.join(value, entry.name);
      if (entry.isDirectory()) { if (depth < MAX_SCAN_DEPTH) pending.push({ value: full, depth: depth + 1 }); continue; }
      if (!entry.isFile()) continue;
      let stat;
      try { stat = fs.statSync(full); } catch { continue; }
      if (!stat.size || stat.size > MAX_WORLD_BYTES + 12) continue;
      let data;
      try { data = fs.readFileSync(full); } catch { continue; }
      let kind = null; let payload = null; let displayName = null;
      try {
        const raw = unwrapWgsWorld(data);
        if (raw) { kind = "world"; payload = raw; }
      } catch { continue; }
      if (!kind) {
        const metadata = characterMetadata(data);
        if (metadata) { kind = "player"; payload = data; displayName = metadata.name; }
      }
      if (!kind) continue;
      const digest = crypto.createHash("sha256").update(payload).digest("hex");
      if (hashes.has(`${kind}:${digest}`)) continue;
      hashes.add(`${kind}:${digest}`);
      found.push({ kind, payload, digest, sourcePath: full, modifiedAt: stat.mtimeMs, displayName });
    }
  }
  return found;
}

function safeSaveName(value, fallback) {
  return String(value || fallback).replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").trim().replace(/[. ]+$/g, "").slice(0, 96) || fallback;
}

function extractWgs(sourcePath) {
  const source = path.resolve(String(sourcePath || ""));
  const normalized = source.replace(/\//g, "\\").toLowerCase();
  if (!normalized.includes("\\systemappdata\\wgs") || !fs.existsSync(source)) throw new Error("Choose a Dragonwilds Game Pass SystemAppData\\wgs folder");
  const payloads = discoverWgsPayloads(source);
  if (!payloads.length) throw new Error("No supported Dragonwilds world or character payloads were found in this WGS folder");
  const catalog = readCatalog();
  const imported = [];
  for (const payload of payloads) {
    const id = `${payload.kind}-wgs-${payload.digest.slice(0, 16)}`;
    const existing = catalog.items.find((item) => item.id === id);
    if (existing) { imported.push(existing); continue; }
    const vault = P.profileSaveVault(id);
    const candidate = `${vault}.incoming-${crypto.randomBytes(4).toString("hex")}`;
    fs.rmSync(candidate, { recursive: true, force: true });
    fs.mkdirSync(candidate, { recursive: true });
    let name;
    if (payload.kind === "world") {
      name = `Game Pass World ${payload.digest.slice(0, 8)}.sav`;
      fs.writeFileSync(path.join(candidate, name), payload.payload);
    } else {
      name = safeSaveName(payload.displayName, `Game Pass Character ${payload.digest.slice(0, 8)}`);
      const bundle = path.join(candidate, "SaveCharacter");
      fs.mkdirSync(bundle, { recursive: true });
      fs.writeFileSync(path.join(bundle, `${name}.json`), payload.payload);
    }
    fs.rmSync(vault, { recursive: true, force: true });
    moveDirectory(candidate, vault);
    const record = { id, kind: payload.kind, name, originalPath: payload.sourcePath, vault, assignment: null, files: 1, size: payload.payload.length, modifiedAt: payload.modifiedAt, adoptedAt: Date.now(), service: "gamepass", conversion: { from: "gamepass-wgs", digest: payload.digest } };
    catalog.items.push(record);
    imported.push(record);
  }
  writeCatalog(catalog);
  return { imported, worlds: imported.filter((item) => item.kind === "world").length, players: imported.filter((item) => item.kind === "player").length };
}

function copyDirectory(source, destination) {
  fs.mkdirSync(destination, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) continue;
    const from = path.join(source, entry.name);
    const to = path.join(destination, entry.name);
    if (entry.isDirectory()) copyDirectory(from, to);
    else if (entry.isFile()) fs.copyFileSync(from, to);
  }
}

function moveDirectory(source, destination) {
  try { fs.renameSync(source, destination); }
  catch (error) {
    if (!['EPERM', 'EXDEV'].includes(error.code)) throw error;
    copyDirectory(source, destination);
    fs.rmSync(source, { recursive: true, force: true });
  }
}

function moveFile(source, destination) {
  try { fs.renameSync(source, destination); }
  catch (error) {
    if (!['EPERM', 'EXDEV'].includes(error.code)) throw error;
    fs.copyFileSync(source, destination);
    fs.rmSync(source, { force: true });
  }
}

function replaceDirectorySafely(source, destination, recovery) {
  const nonce = crypto.randomBytes(4).toString("hex");
  const incoming = `${destination}.incoming-${nonce}`;
  const previous = `${destination}.previous-${nonce}`;
  fs.rmSync(incoming, { recursive: true, force: true });
  fs.rmSync(previous, { recursive: true, force: true });
  copyDirectory(source, incoming);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  if (fs.existsSync(destination)) moveDirectory(destination, previous);
  try {
    if (fs.existsSync(previous)) copyDirectory(previous, recovery);
    moveDirectory(incoming, destination);
    fs.rmSync(previous, { recursive: true, force: true });
  } catch (error) {
    fs.rmSync(incoming, { recursive: true, force: true });
    if (!fs.existsSync(destination) && fs.existsSync(previous)) moveDirectory(previous, destination);
    throw error;
  }
}

function replaceFileSafely(source, destination, recovery) {
  const nonce = crypto.randomBytes(4).toString("hex");
  const incoming = `${destination}.incoming-${nonce}`;
  const previous = `${destination}.previous-${nonce}`;
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.copyFileSync(source, incoming);
  if (fs.existsSync(destination)) moveFile(destination, previous);
  try {
    if (fs.existsSync(previous)) {
      fs.mkdirSync(path.dirname(recovery), { recursive: true });
      fs.copyFileSync(previous, recovery);
    }
    moveFile(incoming, destination);
    fs.rmSync(previous, { force: true });
  } catch (error) {
    fs.rmSync(incoming, { force: true });
    if (!fs.existsSync(destination) && fs.existsSync(previous)) moveFile(previous, destination);
    throw error;
  }
}

function adopt({ sourcePath, kind, scope = "world", profileId = null }) {
  const source = path.resolve(String(sourcePath || ""));
  if (!fs.existsSync(source)) throw new Error("The discovered save no longer exists");
  if (!['world', 'player'].includes(kind)) throw new Error("Only world and player saves can be managed");
  if (kind === "world" && (!fs.statSync(source).isFile() || !/\.sav$/i.test(source))) throw new Error("World profiles require a .sav file");
  if (kind === "player" && !fs.statSync(source).isDirectory()) throw new Error("Player saves must be imported as a SaveCharacter bundle");
  const id = idFor(kind, source);
  const vault = P.profileSaveVault(id);
  const candidate = `${vault}.incoming-${crypto.randomBytes(4).toString("hex")}`;
  fs.rmSync(candidate, { recursive: true, force: true });
  fs.mkdirSync(candidate, { recursive: true });
  if (kind === "world") fs.copyFileSync(source, path.join(candidate, path.basename(source)));
  else copyDirectory(source, path.join(candidate, "SaveCharacter"));
  fs.rmSync(vault, { recursive: true, force: true });
  moveDirectory(candidate, vault);
  const stats = kind === "world" ? { files: 1, size: fs.statSync(source).size, modifiedAt: fs.statSync(source).mtimeMs } : directoryStats(source);
  const catalog = readCatalog();
  const assignment = scope === "unassigned" ? null : kind === "player" && scope === "agnostic" ? { scope: "agnostic", profileId: null } : { scope: "world", profileId: String(profileId || "") || null };
  if (assignment && !assignment.profileId && assignment.scope === "world") throw new Error("Choose a World profile for this save");
  for (const item of catalog.items) {
    if (assignment && item.kind === kind && item.assignment?.scope === assignment.scope && item.assignment?.profileId === assignment.profileId) item.assignment = null;
  }
  const record = { id, kind, name: kind === "world" ? path.basename(source) : path.basename(source), originalPath: source, vault, assignment, ...stats, adoptedAt: Date.now() };
  const index = catalog.items.findIndex((item) => item.id === id);
  if (index >= 0) catalog.items[index] = record; else catalog.items.push(record);
  writeCatalog(catalog);
  return record;
}

function createProfileFromSave({ id = null, sourcePath = null, service = "steam" } = {}) {
  if (!["steam", "epic"].includes(service)) throw new Error("Local save profiles currently launch through Steam or Epic Games. Use RSDW Save Converter for Game Pass imports.");
  let catalog = readCatalog();
  let item = id ? catalog.items.find((entry) => entry.id === id) : null;
  if (!item && sourcePath) {
    item = adopt({ sourcePath, kind: "world", scope: "unassigned" });
    catalog = readCatalog();
  }
  if (!item || item.kind !== "world") throw new Error("Choose a discovered or managed world save");
  const profileId = crypto.randomUUID();
  const displayName = path.basename(item.name || "Dragonwilds World", path.extname(item.name || "")).trim() || "Dragonwilds World";
  const savedRoot = process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, "RSDragonwilds", "Saved") : null;
  const profile = dbm.upsertProfile({
    profile_id: profileId,
    display_name: displayName,
    server_world_id: null,
    client_install: dbm.getSetting(`clientInstall:${service}`, null),
    connection: {
      localWorld: true,
      service,
      platform: service === "epic" ? "steam" : service,
      savePath: savedRoot,
      sourceSavePath: item.originalPath || null,
      worldType: "Local",
      rules: { access: "Local World", passwordRequired: false },
      modBadges: [],
      modCount: 0,
    },
  });
  assign(item.id, "world", profileId);
  return { profile, save: readCatalog().items.find((entry) => entry.id === item.id) };
}

function assign(id, scope, profileId) {
  const catalog = readCatalog();
  const item = catalog.items.find((entry) => entry.id === id);
  if (!item) throw new Error("Managed save not found");
  const assignment = item.kind === "player" && scope === "agnostic" ? { scope: "agnostic", profileId: null } : { scope: "world", profileId: String(profileId || "") || null };
  if (!assignment.profileId && assignment.scope === "world") throw new Error("Choose a World profile for this save");
  for (const other of catalog.items) if (other.id !== item.id && other.kind === item.kind && other.assignment?.scope === assignment.scope && other.assignment?.profileId === assignment.profileId) other.assignment = null;
  item.assignment = assignment;
  writeCatalog(catalog);
  return item;
}

function remove(id) {
  const catalog = readCatalog();
  const item = catalog.items.find((entry) => entry.id === id);
  if (!item) return false;
  catalog.items = catalog.items.filter((entry) => entry.id !== id);
  writeCatalog(catalog);
  fs.rmSync(P.profileSaveVault(id), { recursive: true, force: true });
  return true;
}

function liveLocations(connection = {}) {
  let saved = process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, "RSDragonwilds", "Saved") : null;
  if (connection.savePath) {
    const selected = path.resolve(connection.savePath);
    const normalized = selected.replace(/\//g, "\\").toLowerCase();
    if (normalized.includes("\\systemappdata\\wgs")) return { unsupported: true, reason: "Game Pass WGS saves are detected but cannot be swapped safely without rewriting Microsoft container metadata." };
    const base = path.basename(selected).toLowerCase();
    if (base === "savegames" || base === "savecharacter" || base === "savecharacters") saved = path.dirname(selected);
    else if (base === "saved") saved = selected;
    else saved = path.join(selected, "Saved");
  }
  if (!saved) return { unsupported: true, reason: "No Dragonwilds save location is configured." };
  return { saved, worlds: path.join(saved, "SaveGames"), players: path.join(saved, "SaveCharacter") };
}

function safeRecovery(profileId) {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return path.join(P.profileSaveRecovery(), String(profileId).replace(/[^a-zA-Z0-9_.-]/g, "_"), stamp);
}

function activateForProfile(profileId) {
  const profile = dbm.getProfile(profileId);
  if (!profile) throw new Error("World profile not found");
  const connection = JSON.parse(profile.connection_json || "{}");
  const catalog = readCatalog();
  const specificPlayer = catalog.items.find((item) => item.kind === "player" && item.assignment?.scope === "world" && item.assignment.profileId === profileId);
  const agnosticPlayer = catalog.items.find((item) => item.kind === "player" && item.assignment?.scope === "agnostic");
  const player = specificPlayer || agnosticPlayer || null;
  const world = catalog.items.find((item) => item.kind === "world" && item.assignment?.scope === "world" && item.assignment.profileId === profileId) || null;
  if (!player && !world) return { activated: false, player: null, world: null };
  const live = liveLocations(connection);
  if (live.unsupported) throw new Error(live.reason);
  const ledgerKey = `activeProfileSaves:${crypto.createHash("sha256").update(live.saved.toLowerCase()).digest("hex").slice(0, 16)}`;
  const previous = dbm.getSetting(ledgerKey, {});
  const recovery = safeRecovery(profileId);

  if (previous.playerId && previous.playerId !== player?.id && fs.existsSync(live.players)) {
    const old = catalog.items.find((item) => item.id === previous.playerId);
    if (old) {
      const oldBundle = path.join(P.profileSaveVault(old.id), "SaveCharacter");
      fs.rmSync(oldBundle, { recursive: true, force: true });
      copyDirectory(live.players, oldBundle);
      const stats = directoryStats(live.players); Object.assign(old, stats, { capturedAt: Date.now() });
    }
  }
  if (player && previous.playerId !== player.id) {
    const source = path.join(P.profileSaveVault(player.id), "SaveCharacter");
    if (!fs.existsSync(source)) throw new Error("The managed player-save bundle is missing");
    replaceDirectorySafely(source, live.players, path.join(recovery, "SaveCharacter"));
  }
  if (world) {
    const sourceDir = P.profileSaveVault(world.id);
    const source = path.join(sourceDir, world.name);
    if (!fs.existsSync(source)) throw new Error("The managed world-save file is missing");
    const destination = path.join(live.worlds, world.name);
    replaceFileSafely(source, destination, path.join(recovery, "SaveGames", world.name));
    const now = new Date(); fs.utimesSync(destination, now, now);
  }
  writeCatalog(catalog);
  dbm.setSetting(ledgerKey, { profileId, playerId: player?.id || null, worldId: world?.id || null, activatedAt: Date.now(), recovery });
  return { activated: true, player: player ? { id: player.id, name: player.name, scope: player.assignment.scope } : null, world: world ? { id: world.id, name: world.name } : null, recovery };
}

module.exports = { scan, scanCached, adopt, assign, remove, extractWgs, createProfileFromSave, activateForProfile, liveLocations, readCatalog, unwrapWgsWorld, characterMetadata };
