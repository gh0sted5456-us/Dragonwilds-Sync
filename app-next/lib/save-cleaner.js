const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { P } = require("./paths");
const jobs = require("./jobs");
const profileSaves = require("./profile-saves");

const SOURCE = "https://raw.githubusercontent.com/RSDWArchive/RSDWTools/main";
const CACHE_MAX_AGE = 6 * 60 * 60 * 1000;
const MAX_PLAYER_FILE = 64 * 1024 * 1024;
const MAX_PLAYER_FILES = 512;
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
  while (pending.length && files.length < MAX_PLAYER_FILES) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.isSymbolicLink()) continue;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) pending.push(full);
      else if (entry.isFile() && /\.json$/i.test(entry.name)) files.push(full);
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
    const buffer = fs.readFileSync(file);
    if (!buffer.length || buffer.length > MAX_PLAYER_FILE) { skipped.push({ path: file, reason: "Size outside safety bounds" }); continue; }
    try {
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

function previewWorld(sourcePath, jobId) {
  jobs.setProgress(jobId, 25, "Validating world save…");
  const { target, cache } = worldCacheFor(sourcePath);
  const header = Buffer.alloc(4);
  const descriptor = fs.openSync(target, "r");
  try { fs.readSync(descriptor, header, 0, 4, 0); } finally { fs.closeSync(descriptor); }
  if (header.toString("ascii") !== "SAVE") throw new Error("World file is not a supported Dragonwilds SAVE document");
  const entries = [];
  if (fs.existsSync(cache)) {
    const pending = [cache];
    while (pending.length) {
      const current = pending.pop();
      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        if (entry.isSymbolicLink()) continue;
        const full = path.join(current, entry.name);
        if (entry.isDirectory()) pending.push(full);
        else if (entry.isFile() && /\.lvl$/i.test(entry.name)) {
          const stat = fs.statSync(full);
          entries.push({ path: full, name: path.relative(cache, full), size: stat.size, hash: sha256(fs.readFileSync(full)) });
        }
      }
    }
  }
  jobs.setProgress(jobId, 95, "World cache inspection complete");
  return {
    kind: "world", sourcePath: target, cachePath: cache, cacheFiles: entries,
    bytes: entries.reduce((sum, row) => sum + row.size, 0), removed: [],
    binaryScrubAvailable: false,
    summary: entries.length ? `${entries.length} rebuildable SPUD cache file${entries.length === 1 ? "" : "s"} ready to archive` : "SPUD cache is already clean",
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
  if (!fs.existsSync(cache) || !preview.cacheFiles.length) return { changed: 0, removed: 0, backup: null };
  const current = previewWorld(preview.sourcePath, null).cacheFiles;
  const before = new Map(preview.cacheFiles.map((row) => [row.name.toLowerCase(), row.hash]));
  if (current.length !== preview.cacheFiles.length || current.some((row) => before.get(row.name.toLowerCase()) !== row.hash)) {
    throw new Error("SPUD cache changed after preview; close Dragonwilds and inspect it again");
  }
  jobs.setProgress(jobId, 20, "Archiving SPUD cache…");
  const backupRoot = backupDestination("world");
  fs.mkdirSync(backupRoot, { recursive: true });
  const destination = path.join(backupRoot, "SpudCache");
  fs.cpSync(cache, destination, { recursive: true, errorOnExist: true });
  const copiedFiles = preview.cacheFiles.filter((row) => {
    const copied = path.join(destination, row.name);
    return fs.existsSync(copied) && sha256(fs.readFileSync(copied)) === row.hash;
  });
  if (copiedFiles.length !== preview.cacheFiles.length) throw new Error("SPUD cache backup verification failed; original cache was left untouched");
  const previous = `${cache}.previous-${crypto.randomUUID()}`;
  fs.renameSync(cache, previous);
  try { fs.mkdirSync(cache, { recursive: true }); }
  catch (error) { fs.renameSync(previous, cache); throw error; }
  fs.rmSync(previous, { recursive: true, force: true });
  jobs.setProgress(jobId, 90, "Verified an empty rebuildable SPUD cache");
  return { changed: preview.cacheFiles.length, removed: preview.cacheFiles.length, backup: destination };
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
  const preview = PREVIEWS.get(String(previewId || ""));
  if (!preview) throw new Error("Cleanup preview expired; preview the save again");
  const jobId = jobs.createJob({ type: "cleanup", worldName: preview.kind === "player" ? "Player Save Cleaner" : "World Cleaner" });
  setTimeout(() => {
    try {
      const result = preview.kind === "player" ? applyPlayer(preview, jobId) : applyWorld(preview, jobId);
      const job = jobs.getJob(jobId);
      if (job) job.result = result;
      PREVIEWS.delete(previewId);
      jobs.finishJob(jobId, true);
    } catch (error) { jobs.finishJob(jobId, false, { error: error.message }); }
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
  planPlayerDocument, catalogFromPayloads, decodeDocument, encodeDocument,
};
