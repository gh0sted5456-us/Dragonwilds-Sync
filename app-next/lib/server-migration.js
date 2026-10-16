const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const dbm = require("./db");
const forks = require("./server-forks");
const detect = require("./detect");
const active = require("./active-server-profile");
const { contains } = require("./installdir");

const recordKey = (id) => `serverMigration:${id}`;
const equalPath = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

function plan(worldId, { jobId = null } = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("Server profile not found");
  const coreDir = dbm.getSetting("applicationSetup:serverDir", null);
  if (!coreDir) throw new Error("Link the shared Server Core in Application Setup first");
  const source = path.resolve(world.install_dir || "");
  const sourceInfo = detect.inspect(source), coreInfo = detect.inspect(coreDir);
  if (!world.install_dir || !sourceInfo.valid) throw new Error(sourceInfo.reason || "The existing Server folder is unavailable");
  if (!coreInfo.valid) throw new Error(coreInfo.reason || "The shared Server Core is incomplete");
  if (sourceInfo.platform !== coreInfo.platform) throw new Error("The existing Server and its Core must use the same platform");
  if (fs.lstatSync(source).isSymbolicLink()) throw new Error("The source Server folder is linked; select its actual folder before migrating");
  const destination = forks.forkPath(coreDir, worldId);
  const realSource = fs.realpathSync(source);
  if (fs.existsSync(destination) && fs.lstatSync(destination).isSymbolicLink()) throw new Error("The migration destination is linked; it will not be used");
  const realTarget = forks.realDestination(destination);
  const worlds = dbm.listWorlds();
  const shared = equalPath(source, coreDir) || worlds.some((item) => item.world_id !== worldId && item.install_dir && equalPath(item.install_dir, source));
  const previous = dbm.getSetting(recordKey(worldId), null);
  const result = { worldId, source, destination, coreDir: path.resolve(coreDir), shared, canMigrate: true, reason: "", resume: false, previous };
  if (equalPath(source, destination)) return { ...result, canMigrate: false, reason: "This profile already uses the configured RSDW/Profiles folder." };
  if (contains(realSource, realTarget) || contains(realTarget, realSource)) throw new Error("Migration source and destination must not contain one another");
  if (worlds.some((item) => {
    if (item.world_id === worldId || !item.install_dir || equalPath(item.install_dir, source)) return false;
    const other = forks.realDestination(item.install_dir);
    // The shared installation may contain an old RSDW branch. Inventory
    // deliberately excludes that whole branch rather than nesting its profiles.
    return contains(realSource, other) && !(shared && contains(path.join(realSource, "RSDW"), other));
  })) {
    throw new Error("The source folder contains another registered Server. Select a self-contained Server folder first.");
  }
  if (fs.existsSync(destination)) {
    if (previous?.phase === "verified" && previous.signature && previous.ledgerHash && typeof previous.source === "string" && typeof previous.destination === "string" && typeof previous.coreDir === "string" && equalPath(previous.source, source) && equalPath(previous.destination, destination) && equalPath(previous.coreDir, coreDir)) result.resume = true;
    else return { ...result, canMigrate: false, reason: "The destination already exists. It will not be overwritten; choose another profiles root or review that folder." };
  }
  if (worlds.some((item) => require("./supervisor").isAlive(item.world_id))) return { ...result, canMigrate: false, reason: "Stop all hosted Servers before migrating a Server profile." };
  if (shared && active.readActiveId() !== worldId) return { ...result, canMigrate: false, reason: "Activate this profile first so the shared folder's current world can be identified." };
  if (require("./jobs").listJobs().some((job) => job.id !== jobId && job.status === "running" && (["install", "update", "runtime"].includes(job.type) || job.phase === "copy"))) {
    return { ...result, canMigrate: false, reason: "Wait for the current installation, update or file-copy job to finish." };
  }
  const sourceText = source.replace(/\\/g, "/").toLowerCase();
  if ([world.extra_args, world.wine_launch_flags].some((value) => String(value || "").replace(/\\/g, "/").toLowerCase().includes(sourceText))) {
    return { ...result, canMigrate: false, reason: "Custom launch arguments reference the old folder. Review those arguments before migrating so the Server cannot load files from the old installation." };
  }
  return result;
}

async function digest(file) {
  const hash = crypto.createHash("sha256");
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

async function inventory(root, shared, onLog = () => {}) {
  if (fs.lstatSync(root).isSymbolicLink()) throw new Error("Linked Server folder needs review before migration");
  const files = [], directories = [];
  async function visit(directory) {
    for (const item of await fs.promises.readdir(directory, { withFileTypes: true })) {
      const file = path.join(directory, item.name), relative = path.relative(root, file);
      const normalized = relative.replace(/\\/g, "/").toLowerCase();
      if (normalized === forks.LEDGER || normalized === "steamapps" || normalized.startsWith("steamapps/") || (shared && (normalized === "rsdw" || normalized.startsWith("rsdw/")))) continue;
      if (item.isSymbolicLink()) throw new Error(`Linked file needs review before migration: ${relative}`);
      if (item.isDirectory()) { directories.push(relative); await visit(file); }
      else if (item.isFile()) {
        files.push({ relative, size: (await fs.promises.stat(file)).size, sha256: await digest(file) });
        onLog(`Inspected ${files.length} files: ${relative}`);
      }
    }
  }
  await visit(root);
  files.sort((a, b) => a.relative.localeCompare(b.relative));
  directories.sort();
  const signature = crypto.createHash("sha256").update(JSON.stringify({ files, directories })).digest("hex");
  return { files, directories, signature };
}

function rebasePath(value, source, destination) {
  if (typeof value !== "string" || /[\r\n;]/.test(value) || !path.isAbsolute(value) || !contains(source, value)) return value;
  return path.join(destination, path.relative(source, value));
}
const PATH_FIELDS = new Set(["path", "root", "folder", "source", "target", "sourcePath", "targetPath", "destination", "destinationPath", "installDir", "install_dir", "cachePath", "files", "copied"]);
function rebaseStored(value, source, destination, pathValue = false) {
  if (typeof value === "string") return pathValue ? rebasePath(value, source, destination) : value;
  if (Array.isArray(value)) return value.map((item) => rebaseStored(item, source, destination, pathValue));
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, rebaseStored(item, source, destination, PATH_FIELDS.has(key))]));
  return value;
}

function commitProfile(worldId, approved, buildId, signature, rawIni, legacyValues) {
  const connection = dbm.db();
  connection.exec("SAVEPOINT rsdw_server_migration");
  try {
    const world = dbm.getWorld(worldId);
    if (!world || !equalPath(world.install_dir, approved.source)) throw new Error("The profile's source folder changed during migration");
    const patch = { install_dir: approved.destination, build_id: buildId || world.build_id, status: "stopped", process_id: null, wine_prefix: rebasePath(world.wine_prefix, approved.source, approved.destination) };
    const storedIni = dbm.getSetting(active.profileKey(worldId), null);
    if (!storedIni && rawIni) {
      // Fill missing legacy identity only; never replace a saved profile override.
      for (const [key, column] of [["OwnerId", "owner_id"], ["AdminPassword", "admin_password"], ["WorldPassword", "server_password"], ["DefaultWorldName", "default_world_name"]]) {
        if (!world[column] && legacyValues[key]) patch[column] = String(legacyValues[key]).replace(/^["']|["']$/g, "");
      }
      dbm.setSetting(active.profileKey(worldId), { schema: 1, raw: rawIni });
    }
    let env;
    try { env = JSON.parse(world.env_vars || "{}"); } catch {}
    if (env && typeof env === "object" && !Array.isArray(env)) {
      patch.env_vars = JSON.stringify(Object.fromEntries(Object.entries(env).map(([key, value]) => [key, /(?:path|dir|directory|root|folder|prefix|home)$/i.test(key) ? rebasePath(value, approved.source, approved.destination) : value])));
    }
    for (const row of connection.prepare("SELECT key FROM app_settings WHERE key LIKE ?").all(`%${worldId}%`)) {
      if (row.key === recordKey(worldId) || row.key === active.profileKey(worldId)) continue;
      const old = dbm.getSetting(row.key, null);
      const next = rebaseStored(old, approved.source, approved.destination, /^(modLaneLedger|modRequiredSource|serverRuntimeFiles):/.test(row.key));
      if (JSON.stringify(old) !== JSON.stringify(next)) dbm.setSetting(row.key, next);
    }
    if (approved.shared && !dbm.getSetting(`serverRuntimeFiles:${worldId}`, null)) {
      dbm.setSetting(`serverRuntimeFiles:${worldId}`, dbm.getSetting("applicationSetup:activeServerRuntimeFiles", { files: [] }));
    }
    for (const mod of dbm.listMods(worldId)) {
      const folder = rebasePath(mod.folder, approved.source, approved.destination);
      if (folder !== mod.folder) dbm.updateMod(mod.id, { folder });
    }
    dbm.updateWorld(worldId, patch);
    dbm.setSetting(recordKey(worldId), { schema: 1, ...approved, previous: undefined, signature, phase: "complete", completedAt: Date.now() });
    dbm.logEvent(worldId, "provision", `Migrated Server profile to ${approved.destination}. Recovery source retained: ${approved.source}`);
    connection.exec("RELEASE rsdw_server_migration");
  } catch (error) {
    connection.exec("ROLLBACK TO rsdw_server_migration");
    connection.exec("RELEASE rsdw_server_migration");
    throw error;
  }
}

async function migrate(worldId, review, { jobId = null, onLog = () => {}, onProgress = () => {} } = {}) {
  return require("./supervisor").runMaintenance(worldId, async () => {
    const approved = plan(worldId, { jobId });
    if (!approved.canMigrate) throw new Error(approved.reason);
    if (review?.confirm !== true || review.source !== approved.source || review.destination !== approved.destination || review.coreDir !== approved.coreDir) throw new Error("Review and confirm the current source, destination and Core before migrating");
    const realSource = fs.realpathSync(approved.source), realTarget = forks.realDestination(approved.destination);
    const guard = () => {
      const processGuard = require("./server-process-guard");
      const processes = processGuard.runningServerProcesses();
      const check = processGuard.assertNoConflictingServer;
      const world = dbm.getWorld(worldId);
      check({ ...world, install_dir: approved.source }, { processes });
      check({ ...world, install_dir: approved.destination }, { processes });
      if (!equalPath(fs.realpathSync(approved.source), realSource) || !equalPath(forks.realDestination(approved.destination), realTarget)) throw new Error("Migration paths were redirected while copying; neither profile was switched");
    };
    guard();
    onLog(`Recovery source will remain untouched: ${approved.source}`);
    onProgress({ percent: 0, message: "Inspecting the current Server files…" });
    const original = await inventory(approved.source, approved.shared, onLog);
    const sourceInfo = detect.inspect(approved.source);
    const ini = require("./ini");
    const rawIni = ini.readRawSettings(approved.source, sourceInfo.platform).content;
    const legacyValues = ini.parseOptionSettings(rawIni || "");
    const stage = path.join(path.dirname(approved.destination), `.${worldId}.migration-stage-${crypto.randomUUID()}`);
    let promoted = false;
    try {
      if (approved.resume) {
        const retained = await inventory(approved.destination, approved.shared);
        if (retained.signature !== approved.previous.signature || original.signature !== retained.signature) throw new Error("The source or retained destination changed after the interrupted migration. Neither folder was modified; review them before retrying.");
        if ((await digest(path.join(approved.destination, forks.LEDGER))) !== approved.previous.ledgerHash) throw new Error("The retained Core ledger changed after the interrupted migration; neither folder was switched");
        promoted = true;
      } else {
        dbm.setSetting(recordKey(worldId), { schema: 1, source: approved.source, destination: approved.destination, coreDir: approved.coreDir, phase: "copying", startedAt: Date.now() });
        await fs.promises.mkdir(stage, { recursive: true });
        for (const directory of original.directories) await fs.promises.mkdir(path.join(stage, directory), { recursive: true });
        for (let index = 0; index < original.files.length; index++) {
          const file = original.files[index];
          await fs.promises.copyFile(path.join(approved.source, file.relative), path.join(stage, file.relative), fs.constants.COPYFILE_EXCL);
          onProgress({ percent: Math.round(10 + 55 * (index + 1) / original.files.length), message: `Copied ${index + 1}/${original.files.length}: ${file.relative}` });
        }
        onProgress({ percent: 70, message: "Verifying every copied file…" });
        if ((await inventory(stage, approved.shared)).signature !== original.signature) throw new Error("Copied Server files did not verify; the original profile remains unchanged");
        const oldLedger = forks.readLedger(approved.source);
        let files = oldLedger?.files;
        if (!files) {
          const local = new Map(original.files.map((file) => [file.relative.toLowerCase(), file.sha256]));
          files = (await forks.coreFiles(approved.coreDir)).filter((file) => local.get(file.relative.toLowerCase()) === file.sha256);
        }
        fs.writeFileSync(path.join(stage, forks.LEDGER), JSON.stringify({ schema: 1, coreDir: approved.coreDir, buildId: oldLedger?.buildId || sourceInfo.buildId || dbm.getWorld(worldId).build_id || null, files }, null, 2));
        if (!detect.inspect(stage).valid) throw new Error("The staged Server executable is incomplete; migration was not committed");
        const latest = plan(worldId, { jobId });
        if (!latest.canMigrate || latest.destination !== approved.destination || latest.source !== approved.source || latest.coreDir !== approved.coreDir) throw new Error(latest.reason || "Migration paths changed; review them again");
        guard();
        if ((await inventory(approved.source, approved.shared)).signature !== original.signature) throw new Error("Source files changed while copying. Migration was cancelled and the original remains active.");
        dbm.setSetting(recordKey(worldId), { schema: 1, source: approved.source, destination: approved.destination, coreDir: approved.coreDir, phase: "verified", signature: original.signature, ledgerHash: await digest(path.join(stage, forks.LEDGER)), verifiedAt: Date.now() });
        if (fs.existsSync(approved.destination)) throw new Error("The migration destination appeared while copying; it will not be overwritten");
        await fs.promises.rename(stage, approved.destination);
        promoted = true;
      }
      guard();
      if ((await inventory(approved.source, approved.shared)).signature !== original.signature) throw new Error("Source files changed before committing. Both folders were retained; review them before retrying.");
      if (!equalPath(dbm.getSetting("applicationSetup:serverDir", ""), approved.coreDir) || !equalPath(forks.forkPath(approved.coreDir, worldId), approved.destination)) throw new Error("Core or profiles folder changed before committing. Both folders were retained; review the new paths.");
      if (!equalPath(dbm.getWorld(worldId).install_dir, approved.source)) throw new Error("The profile folder changed during migration");
      commitProfile(worldId, approved, sourceInfo.buildId, original.signature, rawIni, legacyValues);
      onProgress({ percent: 100, message: "Migration verified; Server remains stopped" });
      onLog(`Verified ${original.files.length} files. Profile now uses ${approved.destination}; original files were not removed.`);
      return { installDir: approved.destination, recoverySource: approved.source, filesVerified: original.files.length, stopped: true };
    } catch (error) {
      onLog(`Migration failed. Original profile retained at ${approved.source}: ${error.message}`);
      throw error;
    } finally {
      if (!promoted && path.basename(stage).startsWith(`.${worldId}.migration-stage-`)) await fs.promises.rm(stage, { recursive: true, force: true }).catch(() => {});
    }
  }, "profile-migration");
}

module.exports = { plan, migrate, rebaseStored, recordKey };
