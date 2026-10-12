const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");
const dbm = require("./db");
const steamlib = require("./steamlibrary");
const { P } = require("./paths");
const verifiedHashCache = new Map();

function normalizedInstall(input) {
  const install = steamlib.normalizeGameInstall(input);
  if (!install) throw new Error("Choose a valid Dragonwilds game installation before managing profile files.");
  try { return fs.realpathSync.native(install); }
  catch (error) {
    if (error.code !== "EPERM") throw error;
    // Some Windows installations disallow realpath's reparse-point query.
    // Fall back only when every existing segment is a normal directory.
    const resolved = path.resolve(install);
    const root = path.parse(resolved).root;
    let current = root;
    for (const segment of resolved.slice(root.length).split(path.sep).filter(Boolean)) {
      current = path.join(current, segment);
      const stat = fs.lstatSync(current);
      if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error(`Game installation uses an unverified link: ${current}`);
    }
    return resolved;
  }
}

function locationKey(install) {
  return crypto.createHash("sha256").update(path.resolve(install).toLowerCase()).digest("hex").slice(0, 20);
}

function vaultRoot(install) {
  return path.join(P.clientOriginals(), locationKey(install));
}

function activeLedgerKey(service, install) {
  const location = path.resolve(String(install || service || "default")).toLowerCase();
  return `clientActiveSync:${service}:${crypto.createHash("sha256").update(location).digest("hex").slice(0, 12)}`;
}

function managedTargets(service, install) {
  const ledger = dbm.getSetting(activeLedgerKey(service, install), dbm.getSetting(`clientActiveSync:${service}`, { files: [] }));
  const snapshot = ledger?.profileId ? P.clientProfile(ledger.profileId) : null;
  let manifest = null;
  try { if (snapshot) manifest = JSON.parse(fs.readFileSync(path.join(snapshot, "manifest.json"), "utf8")); } catch {}
  const expected = new Map((manifest?.units || []).flatMap((unit) => unit.files || []).map((item) => [String(item.target).toLowerCase(), item.sha256]));
  const managed = new Set();
  for (const entry of ledger?.files || []) {
    const relative = String(entry).replace(/\\/g, "/");
    try {
      const source = snapshot && targetPath(snapshot, relative);
      const destination = targetPath(install, relative);
      if (!source || !fs.existsSync(source) || !fs.existsSync(destination)) continue;
      const expectedHash = expected.get(relative.toLowerCase());
      if (!expectedHash) { if (sameFile(source, destination)) managed.add(relative); continue; }
      const a = fs.statSync(source), b = fs.statSync(destination);
      if (!a.isFile() || !b.isFile() || a.size !== b.size) continue;
      const sharedInode = a.dev === b.dev && a.ino === b.ino;
      if (fileHashSync(destination) === expectedHash && (sharedInode || fileHashSync(source) === expectedHash)) managed.add(relative);
    } catch {}
  }
  return managed;
}

function sameFile(left, right) {
  const a = fs.statSync(left), b = fs.statSync(right);
  if (!a.isFile() || !b.isFile() || a.size !== b.size) return false;
  if (a.dev === b.dev && a.ino === b.ino) return true;
  return fileHashSync(left) === fileHashSync(right);
}

function fileHashSync(file) {
  const stat = fs.statSync(file);
  const key = `${path.resolve(file).toLowerCase()}:${stat.size}:${stat.mtimeMs}:${stat.ctimeMs}:${stat.dev}:${stat.ino}`;
  if (verifiedHashCache.has(key)) return verifiedHashCache.get(key);
  const digest = crypto.createHash("sha256"), buffer = Buffer.allocUnsafe(1024 * 1024);
  const fd = fs.openSync(file, "r");
  try { let bytes; while ((bytes = fs.readSync(fd, buffer, 0, buffer.length, null)) > 0) digest.update(buffer.subarray(0, bytes)); }
  finally { fs.closeSync(fd); }
  const value = digest.digest("hex");
  if (verifiedHashCache.size >= 1024) verifiedHashCache.clear();
  verifiedHashCache.set(key, value);
  return value;
}

function expectedRoots(install) {
  const project = path.join(install, "RSDragonwilds");
  const roots = [
    path.join(project, "Content", "Paks", "~mods"),
    path.join(project, "Content", "Paks", "LogicMods"),
  ];
  for (const platform of ["Win64", "WinGDK"]) {
    const binary = path.join(project, "Binaries", platform);
    // Keep the shared loader binaries/config in place. Moving UE4SS itself
    // before a connected World's manifest can provide a compatible loader
    // would make the game fail to start. Only mod content is forked here.
    roots.push(path.join(binary, "ue4ss", "Mods"));
  }
  return roots;
}

function relativeTarget(install, file) {
  const relative = path.relative(install, file).split(path.sep).join("/");
  if (!relative.startsWith("RSDragonwilds/") || relative.split("/").some((part) => !part || part === "." || part === "..")) {
    throw new Error(`Unsafe game file path: ${file}`);
  }
  return relative;
}

function targetPath(install, relative) {
  const parts = String(relative || "").replace(/\\/g, "/").split("/");
  if (!parts.length || parts[0] !== "RSDragonwilds" || parts.some((part) => !part || part === "." || part === "..")) throw new Error("Unsafe archived file path");
  const file = path.resolve(install, ...parts);
  if (!file.toLowerCase().startsWith((path.resolve(install) + path.sep).toLowerCase())) throw new Error("Archived path escapes the game installation");
  let ancestor = path.resolve(install);
  for (const segment of parts.slice(0, -1)) {
    ancestor = path.join(ancestor, segment);
    try { if (fs.lstatSync(ancestor).isSymbolicLink()) throw new Error(`A linked folder blocks safe file management: ${ancestor}`); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
  }
  return file;
}

function linkedAncestor(install, candidate) {
  let current = path.resolve(install);
  for (const segment of path.relative(install, candidate).split(path.sep).filter(Boolean)) {
    current = path.join(current, segment);
    try { if (fs.lstatSync(current).isSymbolicLink()) return current; }
    catch (error) { if (error.code !== "ENOENT") throw error; }
  }
  return null;
}

function walkCandidate(candidate, files, unsupported) {
  if (!fs.existsSync(candidate)) return;
  const stat = fs.lstatSync(candidate);
  if (stat.isSymbolicLink()) { unsupported.push(candidate); return; }
  if (stat.isFile()) { files.push(candidate); return; }
  if (!stat.isDirectory()) { unsupported.push(candidate); return; }
  for (const item of fs.readdirSync(candidate)) walkCandidate(path.join(candidate, item), files, unsupported);
}

function listArchives(install) {
  const root = path.join(vaultRoot(install), "archives");
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root, { withFileTypes: true }).filter((item) => item.isDirectory() && !item.name.endsWith(".partial")).map((item) => {
    const location = path.join(root, item.name);
    try {
      const manifest = JSON.parse(fs.readFileSync(path.join(location, "manifest.json"), "utf8"));
      return { ...manifest, location };
    } catch { return { id: item.name, location, corrupt: true }; }
  }).sort((a, b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")));
}

function scan(input, service = "steam") {
  const install = normalizedInstall(input);
  const managed = managedTargets(service, install);
  const managedKeys = new Set([...managed].map((item) => item.toLowerCase()));
  const files = [], unsupported = [];
  for (const candidate of expectedRoots(install)) {
    const linked = linkedAncestor(install, candidate);
    if (linked) unsupported.push(linked);
    else walkCandidate(candidate, files, unsupported);
  }
  const entries = files.map((file) => {
    const relative = relativeTarget(install, file);
    const stat = fs.statSync(file);
    return { relative, size: stat.size, modifiedAt: stat.mtimeMs };
  }).filter((entry) => !managedKeys.has(entry.relative.toLowerCase())).sort((a, b) => a.relative.localeCompare(b.relative));
  const archives = listArchives(install);
  const pending = ["archives", "restores"].flatMap((kind) => {
    const directory = path.join(vaultRoot(install), kind);
    return fs.existsSync(directory) ? fs.readdirSync(directory).filter((name) => name.endsWith(".partial")).map((name) => `${kind}/${name}`) : [];
  });
  const fingerprint = crypto.createHash("sha256").update(JSON.stringify(entries)).digest("hex");
  return {
    install, service, entries, unsupported: unsupported.map((item) => relativeTarget(install, item)),
    archives: archives.map(({ location: _location, ...item }) => item), pending,
    fingerprint, ready: entries.length === 0 && unsupported.length === 0 && pending.length === 0,
  };
}

function gameProcesses() {
  if (process.platform === "win32") {
    const script = "$ErrorActionPreference='Stop'; Get-Process -Name '*Dragonwilds*' -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -notmatch 'Server' } | Select-Object Id,Path | ConvertTo-Json -Compress";
    const result = spawnSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], {
      encoding: "utf8", timeout: 8000, windowsHide: true, maxBuffer: 1024 * 1024,
    });
    if (result.error || result.status !== 0) throw new Error(`Could not verify that Dragonwilds is closed: ${result.error?.message || result.stderr?.trim() || "process query failed"}`);
    const output = String(result.stdout || "").replace(/^\uFEFF/, "").trim();
    if (!output) return [];
    const value = JSON.parse(output);
    return (Array.isArray(value) ? value : [value]).map((item) => ({ pid: Number(item.Id), path: item.Path || "" }));
  }
  if (process.platform === "linux") {
    const found = [];
    for (const item of fs.readdirSync("/proc", { withFileTypes: true })) {
      if (!item.isDirectory() || !/^\d+$/.test(item.name)) continue;
      try {
        const command = fs.readFileSync(`/proc/${item.name}/cmdline`, "utf8").replace(/\0/g, " ");
        if (!/RSDragonwilds(?:-Win(?:64|GDK)-Shipping)?\.exe|RuneScape Dragonwilds\.exe/i.test(command) || /dragonwildsserver/i.test(command)) continue;
        let executable = "";
        try { executable = fs.readlinkSync(`/proc/${item.name}/exe`); } catch {}
        found.push({ pid: Number(item.name), path: executable, command });
      } catch {}
    }
    return found;
  }
  return [];
}

function assertGameStopped(install, processes = gameProcesses()) {
  const root = path.resolve(install).toLowerCase() + path.sep;
  const active = processes.find((item) => !item.path || path.resolve(item.path).toLowerCase().startsWith(root) || String(item.command || "").toLowerCase().includes(root));
  if (active) throw new Error(`Dragonwilds is still running (PID ${active.pid}). Close the game before changing or restoring profile mods.`);
}

async function hashFile(file) {
  const hash = crypto.createHash("sha256");
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

function writeJson(file, value) {
  fs.writeFileSync(file, JSON.stringify(value, null, 2), { encoding: "utf8", flag: "wx" });
}

async function recoverPending(install) {
  const root = path.join(vaultRoot(install), "archives");
  if (!fs.existsSync(root)) return;
  for (const name of fs.readdirSync(root).filter((item) => item.endsWith(".partial"))) {
    const pending = path.join(root, name);
    const manifestPath = path.join(pending, "manifest.json");
    if (!fs.existsSync(manifestPath)) {
      // No manifest means removal of native files never began.
      await fs.promises.rm(pending, { recursive: true, force: true });
      continue;
    }
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    for (const item of manifest.files || []) {
      const destination = targetPath(install, item.relative);
      const backup = targetPath(path.join(pending, "files"), item.relative);
      if (fs.existsSync(destination)) {
        if (await hashFile(destination) !== item.sha256) throw new Error(`Interrupted archive found a changed file: ${item.relative}. Restore it manually from ${pending}.`);
      } else {
        if (await hashFile(backup) !== item.sha256) throw new Error(`Interrupted archive has a damaged backup: ${item.relative}`);
        await fs.promises.mkdir(path.dirname(destination), { recursive: true });
        await fs.promises.copyFile(backup, destination, fs.constants.COPYFILE_EXCL);
      }
    }
    await fs.promises.rm(pending, { recursive: true, force: true });
  }
}

async function recoverPendingRestores(install) {
  const root = path.join(vaultRoot(install), "restores");
  if (!fs.existsSync(root)) return;
  for (const name of fs.readdirSync(root).filter((item) => item.endsWith(".partial"))) {
    const pending = path.join(root, name);
    const manifestPath = path.join(pending, "manifest.json");
    if (!fs.existsSync(manifestPath)) {
      await fs.promises.rm(pending, { recursive: true, force: true });
      continue;
    }
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    const managed = new Map((manifest.managed || []).map((item) => [item.relative.toLowerCase(), item]));
    const originals = new Map((manifest.originals || []).map((item) => [item.relative.toLowerCase(), item]));
    for (const item of manifest.originals || []) {
      const destination = targetPath(install, item.relative);
      if (!fs.existsSync(destination)) continue;
      const actual = await hashFile(destination);
      const previous = managed.get(item.relative.toLowerCase());
      if (actual === item.sha256) await fs.promises.unlink(destination);
      else if (!previous || actual !== previous.sha256) throw new Error(`Interrupted restore found a changed file: ${item.relative}. Review ${pending} manually.`);
    }
    for (const item of manifest.managed || []) {
      const destination = targetPath(install, item.relative);
      const backup = targetPath(path.join(pending, "managed"), item.relative);
      if (await hashFile(backup) !== item.sha256) throw new Error(`Interrupted restore has a damaged managed backup: ${item.relative}`);
      if (fs.existsSync(destination)) {
        if (await hashFile(destination) === item.sha256) continue;
        const original = originals.get(item.relative.toLowerCase());
        if (!original || await hashFile(destination) !== original.sha256) throw new Error(`Interrupted restore found a changed file: ${item.relative}. Review ${pending} manually.`);
        await fs.promises.unlink(destination);
      }
      await fs.promises.mkdir(path.dirname(destination), { recursive: true });
      await fs.promises.copyFile(backup, destination, fs.constants.COPYFILE_EXCL);
    }
    await fs.promises.rm(pending, { recursive: true, force: true });
  }
}

async function archive(input, service, fingerprint, { processes } = {}) {
  const install = normalizedInstall(input);
  assertGameStopped(install, processes);
  await recoverPendingRestores(install);
  await recoverPending(install);
  const inventory = scan(install, service);
  if (inventory.fingerprint !== fingerprint) throw new Error("The mod inventory changed. Review the current list before archiving.");
  if (inventory.unsupported.length) throw new Error("Linked or special files require manual review before archiving.");
  if (!inventory.entries.length) return { archived: false, inventory };
  const data = path.resolve(P.clientOriginals());
  if (data.toLowerCase().startsWith((path.resolve(install) + path.sep).toLowerCase())) throw new Error("Safe Storage must be outside the game installation.");
  const id = `${new Date().toISOString().replace(/[:.]/g, "-")}-${crypto.randomBytes(4).toString("hex")}`;
  const root = path.join(vaultRoot(install), "archives");
  const pending = path.join(root, `${id}.partial`);
  const complete = path.join(root, id);
  await fs.promises.mkdir(path.join(pending, "files"), { recursive: true });
  const records = [];
  try {
    for (const item of inventory.entries) {
      const source = targetPath(install, item.relative);
      const destination = targetPath(path.join(pending, "files"), item.relative);
      if (!fs.lstatSync(source).isFile()) throw new Error(`Mod file changed while archiving: ${item.relative}`);
      await fs.promises.mkdir(path.dirname(destination), { recursive: true });
      await fs.promises.copyFile(source, destination, fs.constants.COPYFILE_EXCL);
      const hash = await hashFile(source);
      if (hash !== await hashFile(destination)) throw new Error(`Safe Storage verification failed: ${item.relative}`);
      const current = fs.statSync(source);
      if (current.size !== item.size || current.mtimeMs !== item.modifiedAt) throw new Error(`Mod file changed while archiving: ${item.relative}`);
      records.push({ relative: item.relative, size: item.size, sha256: hash });
    }
    const latest = scan(install, service);
    if (latest.fingerprint !== fingerprint) throw new Error("The mod inventory changed during backup; no game files were removed.");
    const manifest = { schema: "RSDW.ClientOriginals.v1", id, install, service, createdAt: new Date().toISOString(), files: records };
    writeJson(path.join(pending, "manifest.json"), manifest);
    for (const item of records) await fs.promises.unlink(targetPath(install, item.relative));
    await fs.promises.rename(pending, complete);
    return { archived: true, archiveId: id, fileCount: records.length, inventory: scan(install, service) };
  } catch (error) {
    if (fs.existsSync(path.join(pending, "manifest.json"))) await recoverPending(install).catch(() => {});
    else await fs.promises.rm(pending, { recursive: true, force: true }).catch(() => {});
    throw error;
  }
}

async function restore(input, service, { processes } = {}) {
  const install = normalizedInstall(input);
  assertGameStopped(install, processes);
  await recoverPendingRestores(install);
  await recoverPending(install);
  const archives = listArchives(install).filter((item) => !item.restoredAt && item.service === service);
  if (archives.some((item) => item.corrupt)) throw new Error("Safe Storage contains a damaged manifest; restore is blocked.");
  if (!archives.length) return { restored: false, fileCount: 0 };
  const managed = managedTargets(service, install);
  const managedKeys = new Set([...managed].map((item) => item.toLowerCase()));
  const originals = archives.flatMap((item) => item.files.map((file) => ({ ...file, archive: item })));
  const distinct = new Set();
  for (const item of originals) {
    const key = item.relative.toLowerCase();
    if (distinct.has(key)) throw new Error(`More than one archived original occupies ${item.relative}. Choose an archive to restore before making any changes.`);
    distinct.add(key);
  }
  for (const item of originals) {
    const destination = targetPath(install, item.relative);
    if (fs.existsSync(destination) && !managedKeys.has(item.relative.toLowerCase())) throw new Error(`Restore would overwrite an unmanaged file: ${item.relative}`);
    const backup = targetPath(path.join(item.archive.location, "files"), item.relative);
    if (await hashFile(backup) !== item.sha256) throw new Error(`Stored original failed verification: ${item.relative}`);
  }
  // Managed projections are removed only when their bytes still match the
  // profile snapshot. An edited file is user data and must be reviewed.
  const ledger = dbm.getSetting(activeLedgerKey(service, install), { files: [] });
  const profileSnapshot = ledger?.profileId ? P.clientProfile(ledger.profileId) : null;
  for (const target of ledger?.files || []) {
    const destination = targetPath(install, target);
    if (fs.existsSync(destination) && !managedKeys.has(target.toLowerCase())) throw new Error(`A managed file changed after activation: ${target}. Restore is blocked to protect it.`);
  }
  for (const target of managed) {
    const destination = targetPath(install, target);
    if (!fs.existsSync(destination)) continue;
    const source = profileSnapshot && targetPath(profileSnapshot, target);
    if (!source || !fs.existsSync(source) || await hashFile(destination) !== await hashFile(source)) throw new Error(`A managed file was edited after activation: ${target}. Restore is blocked to protect it.`);
  }
  const pending = path.join(vaultRoot(install), "restores", `${new Date().toISOString().replace(/[:.]/g, "-")}-${crypto.randomBytes(4).toString("hex")}.partial`);
  const managedRecords = [];
  try {
    await fs.promises.mkdir(path.join(pending, "managed"), { recursive: true });
    for (const target of managed) {
      const destination = targetPath(install, target);
      if (!fs.existsSync(destination)) continue;
      const backup = targetPath(path.join(pending, "managed"), target);
      await fs.promises.mkdir(path.dirname(backup), { recursive: true });
      await fs.promises.copyFile(destination, backup, fs.constants.COPYFILE_EXCL);
      const sha256 = await hashFile(destination);
      if (sha256 !== await hashFile(backup)) throw new Error(`Could not verify rollback copy: ${target}`);
      managedRecords.push({ relative: target, sha256 });
    }
    writeJson(path.join(pending, "manifest.json"), { managed: managedRecords, originals: originals.map(({ relative, sha256 }) => ({ relative, sha256 })) });
    for (const target of managed) {
      const destination = targetPath(install, target);
      if (fs.existsSync(destination)) await fs.promises.unlink(destination);
    }
    for (const item of originals) {
      const destination = targetPath(install, item.relative);
      const backup = targetPath(path.join(item.archive.location, "files"), item.relative);
      await fs.promises.mkdir(path.dirname(destination), { recursive: true });
      await fs.promises.copyFile(backup, destination, fs.constants.COPYFILE_EXCL);
    }
  } catch (error) {
    await recoverPendingRestores(install).catch(() => {});
    throw error;
  }
  dbm.setSetting(activeLedgerKey(service, install), { files: [] });
  for (const item of archives) {
    const file = path.join(item.location, "manifest.json");
    fs.writeFileSync(file, JSON.stringify({ ...item, location: undefined, restoredAt: new Date().toISOString() }, null, 2), "utf8");
  }
  await fs.promises.rm(pending, { recursive: true, force: true });
  return { restored: true, fileCount: originals.length, inventory: scan(install, service) };
}

function assertManagedReady(input, service) {
  const inventory = scan(input, service);
  if (!inventory.ready) throw new Error("Unmanaged Dragonwilds mods or an interrupted archive were found. Open this profile’s Safe Storage panel, review them, and confirm the archive before syncing or launching.");
  assertGameStopped(inventory.install);
  return inventory;
}

async function ensureLocalProfileSnapshot(profileId) {
  const profile = dbm.getProfile(profileId);
  if (!profile) throw new Error("Player profile not found");
  const connection = JSON.parse(profile.connection_json || "{}");
  if (!connection.localWorld) throw new Error("Only local Worlds create their own mod fork from original files");
  const snapshot = P.clientProfile(profileId);
  const manifestPath = path.join(snapshot, "manifest.json");
  if (fs.existsSync(manifestPath)) return { snapshot, created: false };
  const service = connection.service || "steam";
  const install = normalizedInstall(profile.client_install || dbm.getSetting(`clientInstall:${service}`, null));
  const inventory = scan(install, service);
  if (!inventory.ready) throw new Error("Review and archive native mods before creating this local World’s mod fork.");
  const originals = listArchives(install).filter((item) => !item.restoredAt && item.service === service);
  if (originals.some((item) => item.corrupt)) throw new Error("Safe Storage contains a damaged archive");
  const files = [], seen = new Set();
  for (const archive of originals.slice().reverse()) {
    for (const item of archive.files || []) {
      if (seen.has(item.relative.toLowerCase())) continue;
      seen.add(item.relative.toLowerCase());
      files.push({ ...item, archive });
    }
  }
  const candidate = `${snapshot}.candidate-${crypto.randomBytes(4).toString("hex")}`;
  try {
    await fs.promises.mkdir(candidate, { recursive: true });
    for (const item of files) {
      const source = targetPath(path.join(item.archive.location, "files"), item.relative);
      const destination = targetPath(candidate, item.relative);
      if (await hashFile(source) !== item.sha256) throw new Error(`Stored original failed verification: ${item.relative}`);
      await fs.promises.mkdir(path.dirname(destination), { recursive: true });
      await fs.promises.copyFile(source, destination, fs.constants.COPYFILE_EXCL);
    }
    const manifest = {
      protocol: "dragonwilds-world-sync", protocolVersion: 2,
      revision: `local-${crypto.randomBytes(8).toString("hex")}`,
      world: { id: `local-${profileId}`, name: profile.display_name },
      units: files.length ? [{ key: "local-originals", name: "Original local mod set", type: "local", clientRequired: true,
        files: files.map((item) => ({ target: item.relative, size: item.size, sha256: item.sha256 })) }] : [],
    };
    await fs.promises.writeFile(path.join(candidate, "manifest.json"), JSON.stringify(manifest, null, 2), { flag: "wx" });
    if (fs.existsSync(snapshot)) {
      // Never overwrite a partial or pre-existing profile cache.
      if (fs.readdirSync(snapshot).length) throw new Error("This World already has profile-owned files. Review them before creating a new fork.");
      await fs.promises.rmdir(snapshot);
    }
    await fs.promises.rename(candidate, snapshot);
    return { snapshot, created: true, fileCount: files.length };
  } catch (error) {
    await fs.promises.rm(candidate, { recursive: true, force: true }).catch(() => {});
    throw error;
  }
}

module.exports = { scan, archive, restore, assertManagedReady, assertGameStopped, ensureLocalProfileSnapshot, vaultRoot, managedTargets, recoverPending, recoverPendingRestores };
