const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { P } = require("./paths");
const jobs = require("./jobs");
const profileSaves = require("./profile-saves");
const worldRepository = require("./world-repository");

const SOURCE = "https://raw.githubusercontent.com/RSDWArchive/RSDWTools/main";
const CACHE_MAX_AGE = 6 * 60 * 60 * 1000;
const MAX_PLAYER_FILE = 64 * 1024 * 1024;
const MAX_PLAYER_FILES = 512;
const MAX_WORLD_FILE = 512 * 1024 * 1024;
const PREVIEWS = globalThis.__RSDW_SAVE_CLEANER_PREVIEWS || new Map();
globalThis.__RSDW_SAVE_CLEANER_PREVIEWS = PREVIEWS;

const CATALOG_FILES = {
  manifest: "data/_ingest_manifest.json",
  items: "website/tools/item-editor/data/catalog.json",
  recipes: "website/tools/recipe-unlocker/data/recipes.json",
  quests: "website/tools/quest-editor/data/quests.json",
};

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function digestFile(file) {
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const chunk = Buffer.allocUnsafe(256 * 1024);
  try {
    let count;
    while ((count = fs.readSync(fd, chunk, 0, chunk.length, null)) > 0) hash.update(chunk.subarray(0, count));
  } finally { fs.closeSync(fd); }
  return hash.digest("hex");
}

function cachePath() {
  return path.join(P.saveCleanerCache(), "rsdw-native-registry.json");
}

function catalogFromPayloads(payloads) {
  const itemRows = Object.values(payloads.items?.tabs || {}).flatMap((tab) => Array.isArray(tab?.items) ? tab.items : []);
  const items = [...new Set(itemRows.map((row) => String(row?.itemData || "").trim()).filter(Boolean))];
  const recipes = [...new Set((payloads.recipes || []).map((row) => String(row?.persistence_id || "").trim()).filter(Boolean))];
  const quests = [...new Set((payloads.quests?.quests || []).map((row) => String(row?.persistence_id || "").trim()).filter(Boolean))];
  if (items.length < 100 || recipes.length < 100 || quests.length < 10) {
    throw new Error("RSDW game registry is incomplete; save cleanup was refused");
  }
  const version = String(payloads.quests?.version || payloads.manifest?.game_root?.split(/[\\/]/).pop() || "current");
  return {
    schema: "RSDWSync.SaveCleanerRegistry.v1",
    version,
    generatedAt: payloads.quests?.generatedAtUtc || payloads.manifest?.generated_at_utc || null,
    fetchedAt: Date.now(),
    source: "RSDWArchive/RSDWTools main",
    items, recipes, quests,
  };
}

function readCachedCatalog() {
  try {
    const value = JSON.parse(fs.readFileSync(cachePath(), "utf8"));
    if (!value || !Array.isArray(value.items) || !Array.isArray(value.recipes) || !Array.isArray(value.quests)) return null;
    if (value.items.length < 100 || value.recipes.length < 100 || value.quests.length < 10) return null;
    return value;
  } catch { return null; }
}

async function fetchJson(relative, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${SOURCE}/${relative}`, {
      signal: controller.signal,
      headers: { "user-agent": "RSDW-Sync-Save-Cleaner" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`RSDW registry download failed (${response.status})`);
    return await response.json();
  } finally { clearTimeout(timer); }
}

async function loadCatalog({ force = false, jobId = null } = {}) {
  const cached = readCachedCatalog();
  if (!force && cached && Date.now() - Number(cached.fetchedAt || 0) < CACHE_MAX_AGE) return { ...cached, cached: true };
  const payloads = {};
  const entries = Object.entries(CATALOG_FILES);
  try {
    for (let index = 0; index < entries.length; index++) {
      const [key, relative] = entries[index];
      jobs.setProgress(jobId, 5 + Math.round((index / entries.length) * 40), `Refreshing ${key} registry from RSDW…`);
      payloads[key] = await fetchJson(relative);
    }
    const catalog = catalogFromPayloads(payloads);
    const temp = `${cachePath()}.${crypto.randomUUID()}.tmp`;
    fs.writeFileSync(temp, JSON.stringify(catalog));
    fs.renameSync(temp, cachePath());
    return { ...catalog, cached: false };
  } catch (error) {
    // A stale registry can misclassify content introduced by a newer game build.
    // Forced cleanup previews therefore fail closed instead of deleting against it.
    if (!force && cached) return { ...cached, cached: true, stale: true, refreshError: error.message };
    throw error;
  }
}

function decodeDocument(buffer) {
  if (buffer.length >= 2 && buffer[0] === 0xff && buffer[1] === 0xfe) {
    return { text: buffer.subarray(2).toString("utf16le"), encoding: "utf16le" };
  }
  return { text: buffer.toString("utf8").replace(/^\uFEFF/, ""), encoding: "utf8" };
}

function encodeDocument(value, encoding) {
  const text = `${JSON.stringify(value, null, 2)}\n`;
  return encoding === "utf16le" ? Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from(text, "utf16le")]) : Buffer.from(text, "utf8");
}

function planPlayerDocument(source, catalog) {
  if (!source || Array.isArray(source) || typeof source !== "object" || !source.GameProgress || typeof source.GameProgress !== "object") {
    throw new Error("Only native Dragonwilds gameplay character JSON is supported");
  }
  const next = structuredClone(source);
  const game = next.GameProgress;
  const knownItems = new Set(catalog.items);
  const knownRecipes = new Set(catalog.recipes);
  const knownQuests = new Set(catalog.quests);
  const removed = [];
  const removedInventorySlots = new Set();

  for (const section of ["Inventory", "PersonalInventory", "Loadout"]) {
    const entries = game[section];
    if (entries == null) continue;
    if (!entries || Array.isArray(entries) || typeof entries !== "object") throw new Error(`Unsupported ${section} layout`);
    for (const [slot, row] of Object.entries(entries)) {
      if (!row || Array.isArray(row) || typeof row !== "object") continue;
      const id = typeof row.ItemData === "string" ? row.ItemData : "";
      const linkedSlot = Number.isInteger(row.PlayerInventoryItemIndex) ? String(row.PlayerInventoryItemIndex) : null;
      if ((id && !knownItems.has(id)) || (section === "Loadout" && linkedSlot && removedInventorySlots.has(linkedSlot))) {
        delete entries[slot];
        if (section === "Inventory") removedInventorySlots.add(slot);
        removed.push({ kind: section, id: id || `inventory slot ${linkedSlot}`, slot });
      }
    }
  }

  const progress = game.Progress;
  if (progress != null) {
    if (!progress || Array.isArray(progress) || typeof progress !== "object") throw new Error("Unsupported Progress layout");
    for (const [field, known] of [["ItemsPickedUp", knownItems], ["MilestoneMaterialsPickedUp", knownItems], ["RecipesUnlocked", knownRecipes], ["RecipesNew", knownRecipes]]) {
      if (progress[field] == null) continue;
      if (!Array.isArray(progress[field])) throw new Error(`Unsupported ${field} layout`);
      progress[field] = progress[field].filter((id) => {
        if (typeof id !== "string" || known.has(id)) return true;
        removed.push({ kind: field, id });
        return false;
      });
    }
  }

  const questProgress = game.QuestProgress;
  if (questProgress != null) {
    if (!questProgress || Array.isArray(questProgress) || typeof questProgress !== "object") throw new Error("Unsupported QuestProgress layout");
    if (questProgress.Quests != null) {
      if (!Array.isArray(questProgress.Quests)) throw new Error("Unsupported quest list layout");
      questProgress.Quests = questProgress.Quests.filter((row) => {
        const id = row && typeof row === "object" && typeof row.QuestId === "string" ? row.QuestId : "";
        if (!id || knownQuests.has(id)) return true;
        removed.push({ kind: "Quest/dialogue", id });
        return false;
      });
    }
    if (typeof questProgress.QuestTracked === "string" && questProgress.QuestTracked && !knownQuests.has(questProgress.QuestTracked)) {
      removed.push({ kind: "Quest tracked", id: questProgress.QuestTracked });
      questProgress.QuestTracked = "";
    }
  }
  return { value: next, removed };
}

function playerFiles(sourcePath) {
  const target = path.resolve(String(sourcePath || ""));
  if (!fs.existsSync(target)) throw new Error("Player save path was not found");
  const stat = fs.statSync(target);
  if (stat.isFile()) return [target];
  if (!stat.isDirectory()) throw new Error("Player save path must be a JSON file or SaveCharacter folder");
  const files = [];
  const pending = [target];
  while (pending.length) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.isSymbolicLink()) continue;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) pending.push(full);
      else if (entry.isFile() && /\.json$/i.test(entry.name)) {
        if (files.length >= MAX_PLAYER_FILES) throw new Error(`Choose a smaller folder; at most ${MAX_PLAYER_FILES} player saves can be inspected together`);
        files.push(full);
      }
    }
  }
  if (!files.length) throw new Error("No player JSON saves were found in this folder");
  return files;
}

async function previewPlayer(sourcePath, jobId) {
  const catalog = await loadCatalog({ force: true, jobId });
  jobs.setProgress(jobId, 52, "Inspecting player saves…");
  const plans = [];
  const skipped = [];
  const files = playerFiles(sourcePath);
  for (let index = 0; index < files.length; index++) {
    const file = files[index];
    try {
      const size = fs.statSync(file).size;
      if (!size || size > MAX_PLAYER_FILE) { skipped.push({ path: file, reason: "Size outside safety bounds" }); continue; }
      const buffer = fs.readFileSync(file);
      if (!buffer.length || buffer.length > MAX_PLAYER_FILE) { skipped.push({ path: file, reason: "Size outside safety bounds" }); continue; }
      const decoded = decodeDocument(buffer);
      const source = JSON.parse(decoded.text);
      const planned = planPlayerDocument(source, catalog);
      plans.push({ path: file, hash: sha256(buffer), encoding: decoded.encoding, output: planned.value, removed: planned.removed });
    } catch (error) { skipped.push({ path: file, reason: error.message }); }
    jobs.setProgress(jobId, 52 + Math.round(((index + 1) / files.length) * 43), `Compared ${index + 1} of ${files.length} player saves…`);
  }
  const removed = plans.flatMap((plan) => plan.removed.map((row) => ({ ...row, file: path.basename(plan.path) })));
  return {
    kind: "player", sourcePath: path.resolve(sourcePath), catalog: publicCatalog(catalog),
    filesScanned: plans.length, filesSkipped: skipped.length, skipped, removed, plans,
    summary: removed.length ? `${removed.length} registry-orphaned record${removed.length === 1 ? "" : "s"} found` : "No registry-orphaned records found",
  };
}

function worldCacheFor(savePath) {
  const target = path.resolve(String(savePath || ""));
  if (!fs.existsSync(target) || !fs.statSync(target).isFile() || !/\.sav$/i.test(target)) throw new Error("Choose a Dragonwilds .sav world file");
  const saveGames = path.dirname(target);
  const saved = path.basename(saveGames).toLowerCase() === "savegames" ? path.dirname(saveGames) : path.dirname(target);
  return { target, cache: path.join(saved, "SpudCache") };
}

function inspectWorldSave(file) {
  const size = fs.statSync(file).size;
  if (size < 8 || size > MAX_WORLD_FILE) throw new Error("World save is outside the supported size range");
  const fd = fs.openSync(file, "r");
  const header = Buffer.alloc(8);
  const chunks = [];
  let formatStatus = "verified";
  let formatWarning = null;
  try {
    if (fs.readSync(fd, header, 0, 8, 0) !== 8 || header.toString("ascii", 0, 4) !== "SAVE") {
      throw new Error("World file is not a supported Dragonwilds SAVE document");
    }
    const declaredSize = header.readUInt32LE(4) + 8;
    if (declaredSize !== size) {
      formatStatus = "unverified";
      formatWarning = `SAVE envelope declares ${declaredSize} bytes; file contains ${size}. No binary edits are permitted.`;
    } else {
      let cursor = 8;
      while (cursor < size && chunks.length < 128) {
        if (cursor + 8 > size || fs.readSync(fd, header, 0, 8, cursor) !== 8) { formatStatus = "unverified"; break; }
        const tag = header.toString("ascii", 0, 4);
        const length = header.readUInt32LE(4);
        if (!/^[A-Za-z0-9_]{4}$/.test(tag) || length > size - cursor - 8) { formatStatus = "unverified"; break; }
        chunks.push({ tag, bytes: length });
        cursor += 8 + length;
      }
      if (cursor !== size || chunks.length >= 128 || !chunks.some((chunk) => chunk.tag === "LVLS")) {
        formatStatus = "unverified";
      }
      if (formatStatus !== "verified") formatWarning = "The top-level SPUD chunks could not be fully verified. The save is left untouched.";
    }
  } finally { fs.closeSync(fd); }
  let worldType = null;
  let rawMode = null;
  try { ({ detectedWorldType: worldType, rawMode } = worldRepository.detectWorldType(file)); } catch {}
  return { size, formatStatus, formatWarning, chunks, worldType, rawMode };
}

function previewWorld(sourcePath, jobId) {
  jobs.setProgress(jobId, 25, "Validating world save…");
  const { target, cache } = worldCacheFor(sourcePath);
  const world = inspectWorldSave(target);
  const entries = [];
  let cacheRealPath = null;
  if (fs.existsSync(cache)) {
    if (fs.lstatSync(cache).isSymbolicLink() || !fs.statSync(cache).isDirectory()) throw new Error("World cache must be a local folder, not a linked path");
    cacheRealPath = fs.realpathSync(cache);
    const pending = [cache];
    while (pending.length) {
      const current = pending.pop();
      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        if (entry.isSymbolicLink()) continue;
        const full = path.join(current, entry.name);
        if (entry.isDirectory()) pending.push(full);
        else if (entry.isFile() && /\.lvl$/i.test(entry.name)) {
          const stat = fs.statSync(full);
          entries.push({ path: full, name: path.relative(cache, full), size: stat.size, hash: digestFile(full) });
        }
      }
    }
  }
  jobs.setProgress(jobId, 95, "World cache inspection complete");
  return {
    kind: "world", sourcePath: target, cachePath: cache, cacheRealPath, cacheFiles: entries,
    world,
    bytes: entries.reduce((sum, row) => sum + row.size, 0), removed: [],
    binaryScrubAvailable: false,
    summary: entries.length ? `${entries.length} rebuildable cache file${entries.length === 1 ? "" : "s"} ready to archive` : "No rebuildable cache files found",
  };
}

function publicCatalog(catalog) {
  return {
    version: catalog.version, generatedAt: catalog.generatedAt, fetchedAt: catalog.fetchedAt,
    source: catalog.source, cached: !!catalog.cached, stale: !!catalog.stale,
    refreshError: catalog.refreshError || null,
    counts: { items: catalog.items.length, recipes: catalog.recipes.length, quests: catalog.quests.length },
  };
}

function backupDestination(kind) {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return path.join(P.saveCleanerBackups(), `${stamp}-${kind}-${crypto.randomUUID().slice(0, 8)}`);
}

function applyPlayer(preview, jobId) {
  jobs.setProgress(jobId, 10, "Rechecking player saves…");
  for (const plan of preview.plans) {
    if (sha256(fs.readFileSync(plan.path)) !== plan.hash) throw new Error(`${path.basename(plan.path)} changed after preview; run preview again`);
  }
  const changed = preview.plans.filter((plan) => plan.removed.length);
  if (!changed.length) return { changed: 0, removed: 0, backup: null };
  const outputRoot = backupDestination("player-cleaned-copy");
  fs.mkdirSync(outputRoot, { recursive: true });
  for (let index = 0; index < changed.length; index++) {
    const plan = changed[index];
    const originalCopy = path.join(outputRoot, `${index}-${path.basename(plan.path)}.original`);
    fs.copyFileSync(plan.path, originalCopy);
    const output = encodeDocument(plan.output, plan.encoding);
    const cleanedFile = path.join(outputRoot, `${index}-${path.basename(plan.path)}`);
    const staged = `${cleanedFile}.${crypto.randomUUID()}.cleaning`;
    fs.writeFileSync(staged, output, { flag: "wx" });
    JSON.parse(decodeDocument(fs.readFileSync(staged)).text);
    fs.renameSync(staged, cleanedFile);
    jobs.setProgress(jobId, 30 + Math.round(((index + 1) / changed.length) * 60), `Exported and verified ${index + 1} of ${changed.length} cleaned copies…`);
  }
  return { changed: changed.length, removed: preview.removed.length, backup: outputRoot, originalUntouched: true };
}

function applyWorld(preview, jobId) {
  const cache = preview.cachePath;
  if (!preview.cacheFiles.length) return { changed: 0, removed: 0, backup: null };
  const assertUnchanged = () => {
    const current = previewWorld(preview.sourcePath, null);
    const before = new Map(preview.cacheFiles.map((row) => [row.name, row.hash]));
    if (current.cacheRealPath !== preview.cacheRealPath || current.cacheFiles.length !== before.size || current.cacheFiles.some((row) => before.get(row.name) !== row.hash)) {
      throw new Error("SPUD cache changed after preview; close Dragonwilds and inspect it again");
    }
  };
  const assertLocalFile = (row) => {
    if (!/\.lvl$/i.test(row.name) || path.isAbsolute(row.name) || row.name.split(/[\\/]/).includes("..")) throw new Error("Invalid world cache entry");
    const file = path.join(cache, row.name);
    if (fs.lstatSync(file).isSymbolicLink() || fs.realpathSync(file) !== path.join(preview.cacheRealPath, row.name)) {
      throw new Error("World cache path changed after preview; inspect it again");
    }
    return file;
  };
  assertUnchanged();
  jobs.logJob(jobId, `Archiving ${preview.cacheFiles.length} reviewed .lvl cache files. World save remains unchanged: ${preview.sourcePath}`);
  jobs.setProgress(jobId, 20, "Archiving SPUD cache…");
  const backupRoot = backupDestination("world");
  const destination = path.join(backupRoot, "SpudCache");
  for (let index = 0; index < preview.cacheFiles.length; index++) {
    const row = preview.cacheFiles[index];
    const file = assertLocalFile(row);
    const copied = path.join(destination, row.name);
    fs.mkdirSync(path.dirname(copied), { recursive: true });
    fs.copyFileSync(file, copied, fs.constants.COPYFILE_EXCL);
    if (digestFile(copied) !== row.hash) throw new Error("SPUD cache backup verification failed; original cache was left untouched");
    jobs.setProgress(jobId, 20 + Math.round(((index + 1) / preview.cacheFiles.length) * 40), `Verified backup ${index + 1} of ${preview.cacheFiles.length} cache files…`);
  }
  assertUnchanged();
  jobs.logJob(jobId, `Cache backup verified: ${destination}`);
  // Only reviewed .lvl files are removed. Unknown files, subfolders and links
  // stay in place; there is never a recursive delete of the live cache folder.
  const staged = [];
  const token = crypto.randomUUID();
  try {
    for (const row of preview.cacheFiles) {
      const file = assertLocalFile(row);
      const temporary = `${file}.${token}.rsdw-cache-archive`;
      fs.renameSync(file, temporary);
      staged.push({ file, temporary, copied: path.join(destination, row.name) });
      if (digestFile(temporary) !== row.hash) throw new Error("SPUD cache changed during archiving; close Dragonwilds and inspect it again");
    }
    for (let index = 0; index < staged.length; index++) {
      fs.unlinkSync(staged[index].temporary);
      jobs.setProgress(jobId, 65 + Math.round(((index + 1) / staged.length) * 30), `Archived ${index + 1} of ${staged.length} reviewed cache files…`);
    }
  } catch (error) {
    const failed = [];
    for (const row of staged.reverse()) {
      try {
        if (fs.existsSync(row.file)) { failed.push(row.file); continue; }
        if (fs.existsSync(row.temporary)) fs.renameSync(row.temporary, row.file);
        else fs.copyFileSync(row.copied, row.file, fs.constants.COPYFILE_EXCL);
      } catch { failed.push(row.file); }
    }
    if (failed.length) throw new Error(`${error.message}. Some cache files could not be restored; recovery backup: ${destination}`);
    throw new Error(`${error.message}. Original cache restored; recovery backup: ${destination}`);
  }
  jobs.logJob(jobId, "Reviewed cache files cleared. Other files and folders remain in place; Dragonwilds rebuilds the cache on its next launch.");
  return { changed: preview.cacheFiles.length, removed: preview.cacheFiles.length, backup: destination, originalUntouched: true };
}

function rememberPreview(preview) {
  const id = crypto.randomUUID();
  PREVIEWS.set(id, { ...preview, createdAt: Date.now() });
  prunePreviews();
  return id;
}

function prunePreviews() {
  const cutoff = Date.now() - 30 * 60 * 1000;
  for (const [id, preview] of PREVIEWS) if (preview.createdAt < cutoff) PREVIEWS.delete(id);
}

function startPreview(kind, sourcePath) {
  if (!['player', 'world'].includes(kind)) throw new Error("Unknown save cleaner kind");
  const jobId = jobs.createJob({ type: "cleanup", worldName: kind === "player" ? "Player Save Cleaner" : "World Cleaner" });
  setTimeout(async () => {
    try {
      const preview = kind === "player" ? await previewPlayer(sourcePath, jobId) : previewWorld(sourcePath, jobId);
      const previewId = rememberPreview(preview);
      const job = jobs.getJob(jobId);
      if (job) job.result = { previewId, ...withoutPlans(preview) };
      jobs.finishJob(jobId, true);
    } catch (error) { jobs.finishJob(jobId, false, { error: error.message }); }
  }, 0);
  return jobId;
}

function startClean(previewId) {
  prunePreviews();
  const id = String(previewId || "");
  const preview = PREVIEWS.get(id);
  if (!preview) throw new Error("Cleanup preview expired; preview the save again");
  if (preview.cleanJobId) return preview.cleanJobId;
  const jobId = jobs.createJob({ type: "cleanup", worldName: preview.kind === "player" ? "Player Save Cleaner" : "World Cleaner" });
  preview.cleanJobId = jobId;
  setTimeout(() => {
    try {
      const result = preview.kind === "player" ? applyPlayer(preview, jobId) : applyWorld(preview, jobId);
      const job = jobs.getJob(jobId);
      if (job) job.result = result;
      PREVIEWS.delete(id);
      jobs.finishJob(jobId, true);
    } catch (error) { delete preview.cleanJobId; jobs.finishJob(jobId, false, { error: error.message }); }
  }, 0);
  return jobId;
}

function withoutPlans(preview) {
  const { plans, ...safe } = preview;
  return safe;
}

function listCandidates(kind) {
  const data = profileSaves.scan(null);
  return data.discoveries.filter((row) => row.kind === kind).map((row) => ({
    path: row.sourcePath, name: row.name, size: row.size, modifiedAt: row.modifiedAt, service: row.service,
  }));
}

module.exports = {
  startPreview, startClean, listCandidates, readCachedCatalog, loadCatalog,
  planPlayerDocument, catalogFromPayloads, decodeDocument, encodeDocument, inspectWorldSave,
};
