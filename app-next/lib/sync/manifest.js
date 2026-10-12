const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const dbm = require("../db");
const mods = require("../mod-lanes");
const steamlib = require("../steamlibrary");
const runtimePackages = require("../runtime-packages");
const { P } = require("../paths");
const { signWorldDownload } = require("./auth");
const cloudStorage = require("./cloud-storage");

const PROTOCOL = "dragonwilds-world-sync";
const PROTOCOL_VERSION = 2;
const prerequisiteKey = (worldId) => `syncPrerequisites:${worldId}`;
const hashCache = globalThis.__DRAGONWILDS_SYNC_HASH_CACHE || (globalThis.__DRAGONWILDS_SYNC_HASH_CACHE = new Map());
const MAX_MANIFEST_FILES = 50000;
const MAX_MANIFEST_BYTES = 64 * 1024 * 1024 * 1024;

function sha256File(file) {
  const stat = fs.statSync(file);
  const resolved = path.resolve(file);
  const cacheKey = process.platform === "win32" ? resolved.toLowerCase() : resolved;
  const cached = hashCache.get(cacheKey);
  if (cached && cached.size === stat.size && cached.mtimeMs === stat.mtimeMs) return cached.sha256;
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    let read;
    while ((read = fs.readSync(fd, buffer, 0, buffer.length, null)) > 0) hash.update(buffer.subarray(0, read));
  } finally { fs.closeSync(fd); }
  const sha256 = hash.digest("hex");
  hashCache.set(cacheKey, { size: stat.size, mtimeMs: stat.mtimeMs, sha256 });
  if (hashCache.size > 4096) hashCache.delete(hashCache.keys().next().value);
  return sha256;
}

function walkFiles(root) {
  if (!fs.existsSync(root)) return [];
  const stat = fs.statSync(root);
  if (stat.isFile()) return [{ source: root, relative: path.basename(root) }];
  const out = [];
  const visit = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.isSymbolicLink()) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.isFile()) out.push({ source: full, relative: path.relative(root, full).replace(/\\/g, "/") });
    }
  };
  visit(root);
  return out;
}

function targetBase(mod, platform = "steam") {
  const binaryDir = platform === "gamepass" ? "WinGDK" : "Win64";
  if (mod.type === "pak") {
    if (mod.pakInstallMode === "runeschema") return `RSDragonwilds/Binaries/${binaryDir}/ue4ss/Mods/RuneSchema/mods/${safeSegment(mod.modId || mod.folderName || mod.name)}/paks`;
    return "RSDragonwilds/Content/Paks/~mods";
  }
  if (mod.type === "ue4ss") return `RSDragonwilds/Binaries/${binaryDir}/ue4ss/Mods/${safeSegment(mod.folderName || mod.name)}`;
  if (mod.type === "runeschema") return `RSDragonwilds/Binaries/${binaryDir}/ue4ss/Mods/RuneSchema/mods/${safeSegment(mod.folderName || mod.name)}`;
  throw new Error(`Unsupported synchronization lane: ${mod.type}`);
}

function safeSegment(value) {
  const segment = String(value || "").trim();
  if (!segment || segment === "." || segment === ".." || /[\\/:*?"<>|]/.test(segment)) throw new Error("Unsafe mod name");
  return segment;
}

function filesForMod(mod, platform = "steam") {
  const base = targetBase(mod, platform);
  const sourceFiles = mod.type === "pak"
    ? (mod.files || []).map((source) => ({ source, relative: path.basename(source) }))
    : walkFiles(mod.path);
  return sourceFiles.map(({ source, relative }) => {
    const target = `${base}/${relative}`.replace(/\\/g, "/");
    const stat = fs.statSync(source);
    return { target, size: stat.size, sha256: sha256File(source), source };
  });
}

function publicFile(file) {
  return { target: file.target, size: file.size, sha256: file.sha256 };
}

function buildWorldManifest(worldId, options = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const inventory = mods.selectedMods(worldId);
  const runtimeUnits = runtimePackages.syncUnits(worldId, options.platform);
  const modUnits = inventory.map((mod) => {
    const files = filesForMod(mod, options.platform);
    const identity = crypto.createHash("sha256");
    for (const file of files) identity.update(`${file.target}\0${file.size}\0${file.sha256}\n`);
    return {
      key: mod.selectionKey || mod.key,
      name: mod.name,
      type: mod.type,
      modId: mod.modId || mod.folderName || mod.name,
      author: mod.identity?.author || null,
      runtimeRole: mod.identity?.runtimeRole || null,
      hotload: mod.identity?.hotload ?? null,
      installMode: mod.type === "pak" ? mod.pakInstallMode : null,
      clientRequired: true,
      contentHash: identity.digest("hex"),
      fileCount: files.length,
      bytes: files.reduce((sum, file) => sum + file.size, 0),
      files: files.map(publicFile),
    };
  });
  const units = [
    ...runtimeUnits.map((unit) => ({ ...unit, files: unit.files.map(publicFile) })),
    ...modUnits,
  ];
  const revisionHash = crypto.createHash("sha256");
  for (const unit of units) revisionHash.update(`${unit.key}\0${unit.contentHash}\n`);
  return {
    protocol: PROTOCOL,
    protocolVersion: PROTOCOL_VERSION,
    world: {
      id: world.world_id,
      name: world.display_name,
      gamePort: world.game_port,
      type: "Dedicated",
      rules: {
        access: String(world.server_password || "").trim() ? "Password protected" : "Direct IP",
        passwordRequired: !!String(world.server_password || "").trim(),
        gamePort: world.game_port,
        clientRequiredMods: modUnits.length + runtimeUnits.length,
        platform: world.platform || "windows",
      },
      identity: {
        iconData: world.icon_data || null,
        bannerData: world.banner_data || null,
        accentColor: world.accent_color || null,
      },
    },
    revision: revisionHash.digest("hex"),
    generatedAt: new Date().toISOString(),
    prerequisites: getPrerequisites(worldId),
    clientPlatform: options.platform === "gamepass" ? "gamepass" : "steam",
    units,
  };
}

function withDownloadUrls(worldId, manifest, baseUrl) {
  const base = String(baseUrl || "").replace(/\/$/, "");
  const storage = cloudStorage.publicStatus(worldId);
  return {
    ...manifest,
    transport: { kind: "http-over-tcp", manifestUrl: base, supportsDirectDownloads: true, hostingType: storage.hostType, storageMode: storage.mode, storageProvider: storage.provider },
    units: (manifest.units || []).map((unit) => ({
      ...unit,
      files: (unit.files || []).map((file) => {
        const signed = signWorldDownload(worldId, file.target, file.sha256);
        const query = new URLSearchParams({ target: file.target, platform: manifest.clientPlatform || "steam", expires: String(signed.expires), token: signed.token });
        return { ...file, downloadUrl: `${base}/file?${query}` };
      }),
    })),
  };
}

function profileShareId(profileId) { return `profile-${String(profileId || "")}`; }

function buildProfileManifest(profileId) {
  const profile = dbm.getProfile(profileId);
  if (!profile) throw new Error("Player profile not found");
  const connection = JSON.parse(profile.connection_json || "{}");
  if (!connection.shareEnabled) throw new Error("This player profile is not shared");
  const snapshotFile = path.join(P.clientProfile(profileId), "manifest.json");
  let cached;
  try { cached = JSON.parse(fs.readFileSync(snapshotFile, "utf8")); }
  catch { throw new Error("Synchronize this profile once before sharing it"); }
  const units = (cached.units || []).map((unit) => ({
    ...unit,
    files: (unit.files || []).map(publicFile),
  }));
  return {
    ...cached,
    world: {
      ...(cached.world || {}), id: profileShareId(profileId), name: profile.display_name, type: "Player Share",
      rules: { ...(cached.world?.rules || {}), access: "Player share", passwordRequired: true },
    },
    generatedAt: new Date().toISOString(),
    units,
  };
}

function resolveProfileFile(profileId, requestedTarget) {
  const manifest = buildProfileManifest(profileId);
  const target = String(requestedTarget || "").replace(/\\/g, "/");
  const declared = manifest.units.flatMap((unit) => unit.files || []).find((file) => file.target === target);
  if (!declared) throw new Error("Mod file is not declared by this player profile");
  const parts = target.split("/");
  if (!target.startsWith("RSDragonwilds/") || parts.some((part) => !part || part === "." || part === "..")) throw new Error("Profile contains an unsafe file target");
  const root = path.resolve(P.clientProfile(profileId));
  const source = path.resolve(root, ...parts);
  if (!source.toLowerCase().startsWith((root + path.sep).toLowerCase()) || !fs.statSync(source).isFile()) throw new Error("Shared profile file is unavailable");
  const size = fs.statSync(source).size;
  if (size !== Number(declared.size) || sha256File(source) !== declared.sha256) throw new Error("Shared profile cache no longer matches its verified manifest");
  return { ...declared, source, size };
}

function getPrerequisites(worldId) {
  const saved = dbm.getSetting(prerequisiteKey(worldId), {});
  return {
    ue4ss: String(saved?.ue4ss || "").trim() || null,
    runeSchema: String(saved?.runeSchema || "").trim() || null,
    managedByClient: Object.values(runtimePackages.status(worldId)).some((item) => item.installed),
  };
}

function setPrerequisites(worldId, value = {}) {
  if (!dbm.getWorld(worldId)) throw new Error("World not found");
  const prerequisites = {
    ue4ss: String(value.ue4ss || "").trim() || null,
    runeSchema: String(value.runeSchema || "").trim() || null,
  };
  dbm.setSetting(prerequisiteKey(worldId), prerequisites);
  return prerequisites;
}

function resolveWorldFile(worldId, requestedTarget, options = {}) {
  const target = String(requestedTarget || "").replace(/\\/g, "/");
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  const runtimeFile = runtimePackages.resolveSyncFile(worldId, target, options.platform);
  if (runtimeFile) return runtimeFile;
  const inventory = mods.selectedMods(worldId);
  for (const mod of inventory) {
    const match = filesForMod(mod, options.platform).find((file) => file.target === target);
    if (match) return match;
  }
  throw new Error("Mod file is not declared by this World");
}

function compareManifest(manifest, gameInstall) {
  if (!manifest || manifest.protocol !== PROTOCOL || manifest.protocolVersion !== PROTOCOL_VERSION) throw new Error("Unsupported Dragonwilds Sync manifest");
  const install = steamlib.normalizeGameInstall(gameInstall);
  if (!install) throw new Error("Choose a valid RuneScape: Dragonwilds game installation.");
  const changes = [];
  const targets = new Set();
  let fileCount = 0;
  let declaredBytes = 0;
  const units = [];
  for (const unit of manifest.units || []) {
    const unitChanges = [];
    for (const file of unit.files || []) {
      fileCount += 1;
      if (fileCount > MAX_MANIFEST_FILES) throw new Error("World manifest declares too many files");
      const relative = String(file.target || "").replace(/\\/g, "/");
      if (!relative.startsWith("RSDragonwilds/") || relative.split("/").some((part) => !part || part === "." || part === "..")) throw new Error("Manifest contains an unsafe target path");
      const targetKey = relative.toLowerCase();
      if (targets.has(targetKey)) throw new Error(`World manifest declares the same target more than once: ${relative}`);
      targets.add(targetKey);
      const size = Number(file.size);
      if (!Number.isSafeInteger(size) || size < 0) throw new Error(`World manifest contains an invalid file size: ${relative}`);
      declaredBytes += size;
      if (declaredBytes > MAX_MANIFEST_BYTES) throw new Error("World manifest exceeds the 64 GiB synchronization limit");
      const expectedHash = String(file.sha256 || "").toLowerCase();
      if (!/^[a-f0-9]{64}$/.test(expectedHash)) throw new Error(`World manifest contains an invalid file hash: ${relative}`);
      const local = path.resolve(install, ...relative.split("/"));
      const root = path.resolve(install) + path.sep;
      if (!local.toLowerCase().startsWith(root.toLowerCase())) throw new Error("Manifest target escapes the game installation");
      let state = "missing";
      if (fs.existsSync(local) && fs.statSync(local).isFile()) state = sha256File(local) === expectedHash ? "current" : "changed";
      if (state !== "current") {
        const change = { unitKey: unit.key, unitName: unit.name, unitType: unit.type, clientRequired: unit.clientRequired !== false, target: relative, state, size, sha256: expectedHash, downloadUrl: file.downloadUrl || null, storageMode: manifest.transport?.storageMode || "local", storageProvider: manifest.transport?.storageProvider || "local" };
        changes.push(change);
        unitChanges.push(change);
      }
    }
    units.push({ key: unit.key, name: unit.name, type: unit.type, clientRequired: unit.clientRequired !== false, fileCount: (unit.files || []).length, bytes: Number(unit.bytes || 0), current: unitChanges.length === 0, changedFiles: unitChanges.length });
  }
  return { revision: manifest.revision, current: changes.length === 0, fileCount, declaredBytes, changes, units, transport: manifest.transport || null };
}

function createClientAttestation(manifest, gameInstall) {
  const comparison = compareManifest(manifest, gameInstall);
  if (!comparison.current) throw new Error(`${comparison.changes.length} managed file(s) are not installed exactly as declared`);
  return {
    protocol: PROTOCOL,
    protocolVersion: PROTOCOL_VERSION,
    revision: String(manifest.revision || ""),
    files: (manifest.units || []).flatMap((unit) => unit.files || []).map((file) => ({ target: file.target, size: Number(file.size), sha256: String(file.sha256).toLowerCase() })).sort((a, b) => a.target.localeCompare(b.target)),
  };
}

function verifyClientAttestation(manifest, attestation) {
  if (!attestation || attestation.protocol !== PROTOCOL || attestation.protocolVersion !== PROTOCOL_VERSION || String(attestation.revision || "") !== String(manifest.revision || "")) throw new Error("Client manifest revision does not match this World");
  const expected = (manifest.units || []).flatMap((unit) => unit.files || []).map((file) => ({ target: file.target, size: Number(file.size), sha256: String(file.sha256).toLowerCase() })).sort((a, b) => a.target.localeCompare(b.target));
  const reported = Array.isArray(attestation.files) ? [...attestation.files].map((file) => ({ target: String(file.target || "").replace(/\\/g, "/"), size: Number(file.size), sha256: String(file.sha256 || "").toLowerCase() })).sort((a, b) => a.target.localeCompare(b.target)) : [];
  if (reported.length !== expected.length) throw new Error("Client manifest file count does not match this World");
  for (let index = 0; index < expected.length; index++) {
    const left = expected[index]; const right = reported[index];
    if (left.target !== right.target || left.size !== right.size || left.sha256 !== right.sha256) throw new Error(`Client manifest does not match the required file: ${left.target}`);
  }
  return { approved: true, revision: manifest.revision, fileCount: expected.length };
}

module.exports = { PROTOCOL, PROTOCOL_VERSION, buildWorldManifest, buildProfileManifest, profileShareId, withDownloadUrls, compareManifest, createClientAttestation, verifyClientAttestation, sha256File, resolveWorldFile, resolveProfileFile, getPrerequisites, setPrerequisites };
