// Each hosted Server gets a private install tree. SteamCMD's machine-level
// installation is a template, never the writable runtime for a new profile.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const dbm = require("./db");
const detect = require("./detect");
const { contains } = require("./installdir");

const ROOT_KEY = "applicationSetup:serverProfilesDir";
const LEDGER = ".rsdw-core.json";

function realDestination(candidate) {
  let current = path.resolve(candidate);
  const missing = [];
  while (!fs.existsSync(current)) {
    const parent = path.dirname(current);
    if (parent === current) break;
    missing.unshift(path.basename(current));
    current = parent;
  }
  return path.join(fs.realpathSync(current), ...missing);
}

function profileRoot(templateDir) {
  const saved = String(dbm.getSetting(ROOT_KEY, "") || "").trim();
  // The RSDW branch lives beside, not inside, SteamCMD's force_install_dir.
  // Both are inside the same core workspace, but Steam cannot touch profiles.
  return path.resolve(saved || path.join(path.dirname(path.resolve(templateDir)), "RSDW", "Profiles"));
}

function validateRoot(root, templateDir) {
  const resolved = path.resolve(String(root || ""));
  const template = path.resolve(String(templateDir || ""));
  if (!root || !path.isAbsolute(String(root))) throw new Error("Choose an absolute Server profiles folder.");
  if (resolved === path.parse(resolved).root) throw new Error("The Server profiles folder cannot be a drive root.");
  const realRoot = realDestination(resolved);
  const realTemplate = realDestination(template);
  if (contains(realRoot, realTemplate) || contains(realTemplate, realRoot)) {
    throw new Error("Server profiles must be outside the shared SteamCMD installation folder.");
  }
  for (const world of dbm.listWorlds()) {
    if (world.install_dir && contains(realDestination(world.install_dir), realRoot)) {
      throw new Error(`The profile folder cannot be inside ${world.display_name}'s server files.`);
    }
  }
  return resolved;
}

function forkPath(templateDir, worldId) {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(worldId))) throw new Error("Invalid Server profile ID.");
  const root = validateRoot(profileRoot(templateDir), templateDir);
  return path.join(root, worldId);
}

function managedFork(world, templateDir) {
  if (!world?.install_dir || !templateDir || !/^[0-9a-f-]{36}$/i.test(String(world.world_id))) return false;
  const target = path.resolve(world.install_dir);
  const core = path.resolve(templateDir);
  return target !== core && path.basename(target).toLowerCase() === String(world.world_id).toLowerCase()
    && !contains(realDestination(target), realDestination(core));
}

function baseFile(relative) {
  const name = relative.replace(/[\\/]/g, "/").toLowerCase();
  if (!name || name === LEDGER || name === "rsdw" || name.startsWith("rsdw/") || name === "rsdragonwilds/activeworld.txt") return false;
  if (name === "rsdragonwilds/saved" || name.startsWith("rsdragonwilds/saved/") || /^rsdragonwilds\/content\/paks\/(~mods|logicmods)(\/|$)/.test(name)) return false;
  // Steam installation bookkeeping is not executable game content. Different
  // LastUpdated/StateFlags/owner values must never prevent a profile launch.
  if (name === "steamapps" || name.startsWith("steamapps/")) return false;
  if (/^appmanifest_\d+\.acf$/.test(path.basename(name))) return false;
  if (/^rsdragonwilds\/binaries\/[^/]+\/ue4ss(\/|$)/.test(name)) return false;
  if (/^rsdragonwilds\/binaries\/[^/]+\/(version|dwmapi)\.dll$/.test(name)) return false;
  return true;
}

async function hash(file) {
  const digest = crypto.createHash("sha256");
  for await (const chunk of fs.createReadStream(file)) digest.update(chunk);
  return digest.digest("hex");
}

async function coreFiles(coreDir) {
  const root = path.resolve(coreDir);
  const files = [];
  async function visit(dir) {
    for (const entry of await fs.promises.readdir(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const relative = path.relative(root, full);
      if (!baseFile(relative)) continue;
      if (entry.isSymbolicLink()) throw new Error(`Core contains a linked path: ${relative}`);
      if (entry.isDirectory()) await visit(full);
      else if (entry.isFile()) files.push({ relative, size: (await fs.promises.stat(full)).size, sha256: await hash(full) });
    }
  }
  await visit(root);
  return files.sort((a, b) => a.relative.localeCompare(b.relative));
}

function readLedger(installDir) {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(installDir, LEDGER), "utf8"));
    if (data?.schema !== 1 || !Array.isArray(data.files) || typeof data.coreDir !== "string") return null;
    const files = [];
    for (const file of data.files) {
      if (typeof file.relative !== "string" || path.isAbsolute(file.relative) || file.relative.split(/[\\/]/).some((part) => part === "..") || !/^[a-f0-9]{64}$/i.test(file.sha256 || "")) return null;
      // Upgrade old ledgers in memory; retained Steam metadata and mod files
      // must not enter either the update or deletion side of the delta.
      if (baseFile(file.relative)) files.push({ ...file, relative: file.relative.replace(/[\\/]/g, path.sep) });
    }
    return { ...data, files };
  } catch { return null; }
}

async function captureBaseline(coreDir, world, { onLog = () => {} } = {}) {
  if (!managedFork(world, coreDir)) return null;
  const existing = readLedger(world.install_dir);
  if (existing) return existing;
  const core = detect.inspect(coreDir);
  const fork = detect.inspect(world.install_dir);
  if (!core.valid || !fork.valid) throw new Error("Core or Server profile is incomplete");
  if (core.buildId && fork.buildId && String(core.buildId) !== String(fork.buildId)) {
    throw new Error(`${world.display_name} is on a different build; review its base files before adopting core updates`);
  }
  const files = [];
  for (const file of await coreFiles(coreDir)) {
    const target = path.join(world.install_dir, file.relative);
    if (fs.existsSync(target) && fs.statSync(target).isFile() && (await hash(target)) === file.sha256) files.push(file);
  }
  const ledger = { schema: 1, coreDir: path.resolve(coreDir), buildId: core.buildId, files };
  fs.writeFileSync(path.join(world.install_dir, LEDGER), JSON.stringify(ledger, null, 2), "utf8");
  onLog(`RSDW: indexed ${files.length} unchanged core files for ${world.display_name}`);
  return ledger;
}

async function refreshFork(coreDir, world, { onLog = () => {}, onProgress = () => {} } = {}) {
  if (updatingCores.has(path.resolve(coreDir).toLowerCase())) throw new Error("Wait for the shared Core update to finish before starting or refreshing a Server profile.");
  if (!managedFork(world, coreDir)) throw new Error("This profile is not an RSDW-managed Server fork");
  const target = path.resolve(world.install_dir);
  const ledger = await captureBaseline(coreDir, world, { onLog });
  if (path.resolve(ledger.coreDir).toLowerCase() !== path.resolve(coreDir).toLowerCase()) {
    throw new Error("This Server profile belongs to a different core installation");
  }
  const newFiles = await coreFiles(coreDir);
  const old = new Map(ledger.files.map((file) => [file.relative.toLowerCase(), file]));
  const fresh = new Map(newFiles.map((file) => [file.relative.toLowerCase(), file]));
  const changes = [];
  const conflicts = [];
  for (const file of newFiles) {
    const previous = old.get(file.relative.toLowerCase());
    if (previous?.sha256 === file.sha256) continue;
    const current = path.join(target, file.relative);
    const currentHash = fs.existsSync(current) && fs.statSync(current).isFile() ? await hash(current) : null;
    if (currentHash && currentHash !== (previous?.sha256 || file.sha256)) conflicts.push(file.relative);
    else changes.push({ kind: "copy", file });
  }
  for (const file of ledger.files) {
    if (fresh.has(file.relative.toLowerCase())) continue;
    const current = path.join(target, file.relative);
    const currentHash = fs.existsSync(current) && fs.statSync(current).isFile() ? await hash(current) : null;
    if (currentHash && currentHash !== file.sha256) conflicts.push(file.relative);
    else if (currentHash) changes.push({ kind: "remove", file });
  }
  if (conflicts.length) throw new Error(`Core refresh needs review; modified base files were preserved: ${conflicts.slice(0, 5).join(", ")}${conflicts.length > 5 ? ` (+${conflicts.length - 5} more)` : ""}`);
  if (!changes.length) {
    const coreBuild = detect.inspect(coreDir).buildId;
    if (ledger.buildId !== coreBuild || JSON.stringify(ledger.files) !== JSON.stringify(newFiles)) {
      const latestLedger = { schema: 1, coreDir: path.resolve(coreDir), buildId: coreBuild, files: newFiles };
      const temporary = path.join(target, `${LEDGER}.${crypto.randomUUID()}.tmp`);
      try {
        fs.writeFileSync(temporary, JSON.stringify(latestLedger, null, 2), { encoding: "utf8", flag: "wx" });
        fs.renameSync(temporary, path.join(target, LEDGER));
      } finally { if (fs.existsSync(temporary)) fs.rmSync(temporary, { force: true }); }
    }
    return { updated: false, changedFiles: 0, buildId: coreBuild };
  }
  const nonce = crypto.randomUUID();
  const stage = path.join(path.dirname(target), `.${world.world_id}.core-stage-${nonce}`);
  const previous = path.join(path.dirname(target), `.${world.world_id}.core-previous-${nonce}`);
  let promoted = false;
  try {
    onLog(`RSDW: staging ${world.display_name}; ${changes.length} base file changes, profile saves and mods retained`);
    await fs.promises.cp(target, stage, { recursive: true, force: false, errorOnExist: true,
      filter: async (entry) => {
        if ((await fs.promises.lstat(entry)).isSymbolicLink()) throw new Error(`Profile contains a linked path: ${entry}`);
        return true;
      },
    });
    let completed = 0;
    for (const change of changes) {
      const destination = path.join(stage, change.file.relative);
      if (change.kind === "copy") {
        await fs.promises.mkdir(path.dirname(destination), { recursive: true });
        await fs.promises.copyFile(path.join(coreDir, change.file.relative), destination);
        if ((await hash(destination)) !== change.file.sha256) throw new Error(`Core file changed while copying: ${change.file.relative}`);
      } else await fs.promises.rm(destination, { force: true });
      completed++;
      onProgress({ completed, total: changes.length, file: change.file.relative });
      onLog(`RSDW: ${change.kind === "copy" ? "copied" : "removed"} ${change.file.relative} (${completed}/${changes.length})`);
    }
    const core = detect.inspect(coreDir);
    fs.writeFileSync(path.join(stage, LEDGER), JSON.stringify({ schema: 1, coreDir: path.resolve(coreDir), buildId: core.buildId, files: newFiles }, null, 2), "utf8");
    const checked = detect.inspect(stage);
    if (!core.valid || !checked.valid || (core.buildId && checked.buildId !== core.buildId)) throw new Error("Staged Server profile did not match the verified core build");
    await fs.promises.rename(target, previous);
    try { await fs.promises.rename(stage, target); promoted = true; }
    catch (error) { await fs.promises.rename(previous, target); throw error; }
    await fs.promises.rm(previous, { recursive: true, force: true }).catch((error) => {
      onLog(`RSDW: refreshed profile is ready, but the previous staged copy needs cleanup: ${error.message}`);
    });
    return { updated: true, changedFiles: changes.length, buildId: core.buildId };
  } finally {
    if (!promoted) await fs.promises.rm(stage, { recursive: true, force: true }).catch(() => {});
  }
}

const updatingCores = globalThis.__RSDW_CORE_UPDATES || (globalThis.__RSDW_CORE_UPDATES = new Map());

async function updateCore(coreDir, platform, { onLog = () => {} } = {}) {
  const key = path.resolve(coreDir).toLowerCase();
  if (updatingCores.has(key)) {
    onLog("RSDW: another core update is running; waiting for its verified result");
    return updatingCores.get(key);
  }
  const work = (async () => {
    const steam = require("./steamcmd");
    const current = detect.inspect(coreDir);
    if (current.valid) {
      for (const world of dbm.listWorlds()) {
        if (!managedFork(world, coreDir) || readLedger(world.install_dir)) continue;
        try { await captureBaseline(coreDir, world, { onLog }); }
        catch (error) { onLog(`RSDW: ${world.display_name} needs a base-file review: ${error.message}`); }
      }
    }
    await steam.ensureSteamCmd((line) => onLog(`SteamCMD: ${line}`));
    onLog(`RSDW: updating shared core at ${coreDir}`);
    const result = await steam.installOrUpdate(coreDir, (line) => onLog(`SteamCMD: ${line}`), platform);
    if (!result.ok) throw new Error(`SteamCMD failed (code ${result.code})${result.detail ? `: ${result.detail}` : ""}`);
    const verified = detect.inspect(coreDir);
    if (!verified.valid) throw new Error(verified.reason || "Updated core did not validate");
    onLog(`RSDW: verified core build ${verified.buildId || result.buildId || "unknown"}`);
    return { ...result, buildId: verified.buildId || result.buildId || null };
  })();
  updatingCores.set(key, work);
  try { return await work; }
  finally { if (updatingCores.get(key) === work) updatingCores.delete(key); }
}

async function refreshStoppedProfiles(coreDir, { onLog = () => {}, onProgress = () => {} } = {}) {
  const sup = require("./supervisor");
  const results = [];
  const coreBuild = detect.inspect(coreDir).buildId;
  for (const world of dbm.listWorlds()) {
    if (!managedFork(world, coreDir)) continue;
    if (coreBuild) dbm.updateWorld(world.world_id, { latest_known_build_id: coreBuild });
    if (sup.isAlive(world.world_id)) {
      onLog(`RSDW: ${world.display_name} is running; core refresh waits for its next start`);
      results.push({ worldId: world.world_id, pending: true });
      continue;
    }
    try {
      const result = await sup.runMaintenance(world.world_id, () => refreshFork(coreDir, world, {
        onLog, onProgress: (progress) => onProgress({ worldId: world.world_id, worldName: world.display_name, ...progress }),
      }));
      if (result.buildId) dbm.updateWorld(world.world_id, { build_id: result.buildId, latest_known_build_id: result.buildId });
      onLog(`RSDW: ${world.display_name} ${result.updated ? `refreshed ${result.changedFiles} base files` : "already matches the core"}`);
      results.push({ worldId: world.world_id, ...result });
    } catch (error) {
      onLog(`RSDW: ${world.display_name} refresh needs attention: ${error.message}`);
      dbm.logEvent(world.world_id, "update", `Core refresh needs attention: ${error.message}`);
      results.push({ worldId: world.world_id, error: error.message });
    }
  }
  return results;
}

async function forkInstall(templateDir, worldId, { includeSaved = false, onLog = () => {} } = {}) {
  const source = path.resolve(templateDir);
  const info = detect.inspect(source);
  if (!info.valid) throw new Error(info.reason || "The shared dedicated-server installation is incomplete.");
  const target = forkPath(source, worldId);
  const targetParent = path.dirname(target);
  if (fs.existsSync(target)) throw new Error(`Server profile folder already exists: ${target}`);
  await fs.promises.mkdir(targetParent, { recursive: true });
  onLog(`Forking server files from ${source}`);
  onLog(`Private Server profile: ${target}`);
  try {
    await fs.promises.cp(source, target, {
      recursive: true,
      force: false,
      errorOnExist: true,
      filter: async (entry) => {
        const relative = path.relative(source, entry).split(path.sep).join("/").toLowerCase();
        if (relative === "rsdw" || relative.startsWith("rsdw/")) return false;
        if (relative === "rsdragonwilds/activeworld.txt") return false;
        if (!includeSaved && relative === "rsdragonwilds/saved") return false;
        if (relative === "steamapps/downloading" || relative === "steamapps/temp") return false;
        if ((await fs.promises.lstat(entry)).isSymbolicLink()) throw new Error(`Cannot fork linked server file: ${entry}`);
        return true;
      },
    });
    const fork = detect.inspect(target);
    if (!fork.valid) throw new Error(`The private Server profile did not validate: ${fork.reason}`);
    const files = await coreFiles(source);
    fs.writeFileSync(path.join(target, LEDGER), JSON.stringify({ schema: 1, coreDir: source, buildId: info.buildId, files }, null, 2), "utf8");
    onLog(`Verified private server executable: ${fork.binary}`);
    return { installDir: target, platform: fork.platform, buildId: fork.buildId };
  } catch (error) {
    // This target was created only for this UUID and is still inside the
    // validated profile root. Never remove the template or another profile.
    if (path.dirname(target) === targetParent && path.basename(target) === worldId) {
      await fs.promises.rm(target, { recursive: true, force: true }).catch(() => {});
    }
    throw error;
  }
}

module.exports = { ROOT_KEY, LEDGER, baseFile, coreFiles, realDestination, profileRoot, validateRoot, forkPath, forkInstall, managedFork, readLedger, captureBaseline, refreshFork, updateCore, refreshStoppedProfiles };
