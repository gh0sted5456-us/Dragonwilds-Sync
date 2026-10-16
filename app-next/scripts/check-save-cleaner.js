const assert = require("assert");
const fs = require("fs");
const path = require("path");
const cleaner = require("../lib/save-cleaner");
const jobs = require("../lib/jobs");

const ids = (prefix, count) => Array.from({ length: count }, (_, index) => `${prefix}-${index}`);
const itemIds = ids("item", 120);
const recipeIds = ids("recipe", 120);
const questIds = ids("quest", 20);
const payloads = {
  manifest: { game_root: "RSDWArchive/1.0.0-test", generated_at_utc: "2026-10-11T00:00:00Z" },
  items: { tabs: { bag: { items: itemIds.map((itemData) => ({ itemData })) } } },
  recipes: recipeIds.map((persistence_id) => ({ persistence_id })),
  quests: { version: "1.0.0-test", quests: questIds.map((persistence_id) => ({ persistence_id })) },
};
const catalog = cleaner.catalogFromPayloads(payloads);

assert.equal(catalog.items.length, 120);
assert.equal(catalog.recipes.length, 120);
assert.equal(catalog.quests.length, 20);

const source = {
  meta_data: { char_name: "Cleaner Test" },
  GameProgress: {
    Inventory: {
      0: { ItemData: "item-1", Count: 1 },
      7: { ItemData: "retired-item", Count: 1 },
      opaque: "third-party-shape-must-survive",
    },
    PersonalInventory: { 2: { ItemData: "item-2" } },
    Loadout: { Head: { PlayerInventoryItemIndex: 7 }, Body: { ItemData: "item-3" } },
    Progress: {
      ItemsPickedUp: ["item-1", "retired-item"],
      RecipesUnlocked: ["recipe-1", "retired-recipe"],
      BuildingsUnlocked: ["unresolved-building-must-survive"],
    },
    QuestProgress: {
      QuestTracked: "retired-quest",
      Quests: [{ QuestId: "quest-1" }, { QuestId: "retired-quest" }, "opaque-row"],
    },
  },
};

const plan = cleaner.planPlayerDocument(source, catalog);
assert(plan.value.GameProgress.Inventory[0]);
assert(!plan.value.GameProgress.Inventory[7]);
assert.equal(plan.value.GameProgress.Inventory.opaque, "third-party-shape-must-survive");
assert(!plan.value.GameProgress.Loadout.Head);
assert(plan.value.GameProgress.Loadout.Body);
assert.deepEqual(plan.value.GameProgress.Progress.ItemsPickedUp, ["item-1"]);
assert.deepEqual(plan.value.GameProgress.Progress.RecipesUnlocked, ["recipe-1"]);
assert.deepEqual(plan.value.GameProgress.Progress.BuildingsUnlocked, ["unresolved-building-must-survive"]);
assert.equal(plan.value.GameProgress.QuestProgress.QuestTracked, "");
assert.deepEqual(plan.value.GameProgress.QuestProgress.Quests, [{ QuestId: "quest-1" }, "opaque-row"]);
assert.equal(plan.removed.length, 6);
assert(source.GameProgress.Inventory[7], "planning must not mutate the source save");

const utf16 = cleaner.encodeDocument(source, "utf16le");
const decoded = cleaner.decodeDocument(utf16);
assert.equal(decoded.encoding, "utf16le");
assert.deepEqual(JSON.parse(decoded.text), source);
assert.throws(() => cleaner.planPlayerDocument({ Customization: {}, meta_data: {} }, catalog), /native Dragonwilds gameplay/);

const folder = fs.mkdtempSync(path.join(__dirname, "..", ".rsdw-world-inspect-test-"));
try {
  const worldPath = path.join(folder, "World.sav");
  const mode = Buffer.alloc(13);
  Buffer.from("L_World\0", "ascii").copy(mode);
  mode.writeUInt32LE(3, 9);
  const info = Buffer.alloc(8);
  info.write("INFO");
  const lvls = Buffer.alloc(8 + mode.length);
  lvls.write("LVLS");
  lvls.writeUInt32LE(mode.length, 4);
  mode.copy(lvls, 8);
  const save = Buffer.alloc(8);
  save.write("SAVE");
  save.writeUInt32LE(info.length + lvls.length, 4);
  fs.writeFileSync(worldPath, Buffer.concat([save, info, lvls]));
  const inspected = cleaner.inspectWorldSave(worldPath);
  assert.equal(inspected.formatStatus, "verified");
  assert.equal(inspected.worldType, "Custom");
  assert.deepEqual(inspected.chunks.map((chunk) => chunk.tag), ["INFO", "LVLS"]);
  save.writeUInt32LE(1, 4);
  fs.writeFileSync(worldPath, Buffer.concat([save, info, lvls]));
  assert.equal(cleaner.inspectWorldSave(worldPath).formatStatus, "unverified");
} finally { fs.rmSync(folder, { recursive: true, force: true }); }

async function waitForJob(id) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const job = jobs.getJob(id);
    if (job?.status !== "running") return job;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error("Save cleaner test job timed out");
}

async function checkWorldArchive() {
  const folder = fs.mkdtempSync(path.join(__dirname, "..", ".rsdw-cache-cleaner-test-"));
  const previousDataDir = process.env.APP_MANAGER_DATA_DIR;
  process.env.APP_MANAGER_DATA_DIR = path.join(folder, "launcher-data");
  const originalRename = fs.renameSync;
  const originalUnlink = fs.unlinkSync;
  const originalCopy = fs.copyFileSync;
  const originalFetch = global.fetch;
  const originalRead = fs.readFileSync;
  try {
    const saved = path.join(folder, "Saved");
    const saveGames = path.join(saved, "SaveGames");
    const cache = path.join(saved, "SpudCache");
    const nested = path.join(cache, "Nested");
    fs.mkdirSync(saveGames, { recursive: true });
    fs.mkdirSync(nested, { recursive: true });
    const worldPath = path.join(saveGames, "World.sav");
    const world = Buffer.alloc(16);
    world.write("SAVE");
    world.writeUInt32LE(8, 4);
    world.write("LVLS", 8);
    fs.writeFileSync(worldPath, world);
    const first = path.join(cache, "One.lvl");
    const second = path.join(nested, "Two.lvl");
    const unrelated = path.join(cache, "keep-me.txt");
    const nestedUnrelated = path.join(nested, "config.json");
    const empty = path.join(cache, "KeepEmptyFolder");
    fs.mkdirSync(empty);
    fs.writeFileSync(unrelated, "not a rebuildable cache file");
    fs.writeFileSync(nestedUnrelated, "{\"preserve\":true}");
    const seed = () => { fs.writeFileSync(first, "first cache"); fs.writeFileSync(second, "second cache"); };
    const preview = async () => {
      const job = await waitForJob(cleaner.startPreview("world", worldPath));
      assert.equal(job.status, "success", job.error);
      return job.result;
    };
    const assertPreserved = () => {
      assert.deepEqual(fs.readFileSync(worldPath), world, "world save must never change");
      assert.equal(fs.readFileSync(unrelated, "utf8"), "not a rebuildable cache file");
      assert.equal(fs.readFileSync(nestedUnrelated, "utf8"), "{\"preserve\":true}");
      assert(fs.statSync(empty).isDirectory(), "unknown folders must remain in place");
    };

    seed();
    let result = await preview();
    assert.equal(result.cacheFiles.length, 2);
    const jobId = cleaner.startClean(result.previewId);
    assert.equal(cleaner.startClean(result.previewId), jobId, "repeated cleanup must reuse the running job");
    let job = await waitForJob(jobId);
    assert.equal(job.status, "success", job.error);
    assert.equal(job.result.changed, 2);
    assert.equal(fs.readFileSync(path.join(job.result.backup, "One.lvl"), "utf8"), "first cache");
    assert.equal(fs.readFileSync(path.join(job.result.backup, "Nested", "Two.lvl"), "utf8"), "second cache");
    assert(!fs.existsSync(first));
    assert(!fs.existsSync(second));
    assertPreserved();

    seed();
    result = await preview();
    fs.writeFileSync(second, "changed after review");
    job = await waitForJob(cleaner.startClean(result.previewId));
    assert.equal(job.status, "error");
    assert.match(job.error, /SPUD cache changed after preview/);
    assert.equal(fs.readFileSync(first, "utf8"), "first cache");
    assert.equal(fs.readFileSync(second, "utf8"), "changed after review");
    assertPreserved();

    seed();
    result = await preview();
    fs.copyFileSync = (from, to, ...args) => {
      originalCopy(from, to, ...args);
      if (to.endsWith("One.lvl")) fs.writeFileSync(to, "corrupted copy");
    };
    try { job = await waitForJob(cleaner.startClean(result.previewId)); }
    finally { fs.copyFileSync = originalCopy; }
    assert.equal(job.status, "error");
    assert.match(job.error, /backup verification failed/);
    assert.equal(fs.readFileSync(first, "utf8"), "first cache");
    assert.equal(fs.readFileSync(second, "utf8"), "second cache");
    assertPreserved();

    result = await preview();
    let stagedCount = 0;
    fs.renameSync = (from, to) => {
      if (to.endsWith(".rsdw-cache-archive") && ++stagedCount === 2) throw new Error("simulated locked cache file");
      return originalRename(from, to);
    };
    try { job = await waitForJob(cleaner.startClean(result.previewId)); }
    finally { fs.renameSync = originalRename; }
    assert.equal(job.status, "error");
    assert.match(job.error, /Original cache restored/);
    assert.equal(fs.readFileSync(first, "utf8"), "first cache");
    assert.equal(fs.readFileSync(second, "utf8"), "second cache");
    assertPreserved();

    result = await preview();
    let removedCount = 0;
    fs.unlinkSync = (file) => {
      if (file.endsWith(".rsdw-cache-archive") && ++removedCount === 2) throw new Error("simulated delete failure");
      return originalUnlink(file);
    };
    try { job = await waitForJob(cleaner.startClean(result.previewId)); }
    finally { fs.unlinkSync = originalUnlink; }
    assert.equal(job.status, "error");
    assert.match(job.error, /Original cache restored/);
    assert.equal(fs.readFileSync(first, "utf8"), "first cache");
    assert.equal(fs.readFileSync(second, "utf8"), "second cache");
    assertPreserved();

    job = await waitForJob(cleaner.startClean(result.previewId));
    assert.equal(job.status, "success", "a failed cleanup must allow retry with an unchanged preview");
    assertPreserved();
    result = await preview();
    assert.equal(result.cacheFiles.length, 0);

    // Linked subfolders are never scanned or cleaned, even when they contain .lvl files.
    const external = path.join(folder, "External");
    fs.mkdirSync(external);
    fs.writeFileSync(path.join(external, "Outside.lvl"), "leave outside file alone");
    const link = path.join(cache, "Linked");
    fs.symlinkSync(external, link, process.platform === "win32" ? "junction" : "dir");
    result = await preview();
    assert.equal(result.cacheFiles.length, 0);
    assert.equal(fs.readFileSync(path.join(external, "Outside.lvl"), "utf8"), "leave outside file alone");
    fs.unlinkSync(link);

    global.fetch = async (url) => {
      const key = String(url).endsWith("_ingest_manifest.json") ? "manifest" : String(url).endsWith("catalog.json") ? "items" : String(url).endsWith("recipes.json") ? "recipes" : "quests";
      return { ok: true, json: async () => payloads[key] };
    };
    const playerFolder = path.join(folder, "Players");
    fs.mkdirSync(playerFolder);
    const oversized = path.join(playerFolder, "TooLarge.json");
    const fd = fs.openSync(oversized, "w");
    try { fs.ftruncateSync(fd, 64 * 1024 * 1024 + 1); }
    finally { fs.closeSync(fd); }
    fs.readFileSync = (file, ...args) => {
      assert.notEqual(file, oversized, "oversized player saves must be rejected before allocating a read buffer");
      return originalRead(file, ...args);
    };
    try { job = await waitForJob(cleaner.startPreview("player", oversized)); }
    finally { fs.readFileSync = originalRead; }
    assert.equal(job.status, "success", job.error);
    assert.equal(job.result.filesSkipped, 1);
    assert.match(job.result.skipped[0].reason, /Size outside safety bounds/);
    assert.equal(fs.statSync(oversized).size, 64 * 1024 * 1024 + 1);
    for (let index = 0; index < 512; index++) fs.writeFileSync(path.join(playerFolder, `${index}.json`), "{}");
    job = await waitForJob(cleaner.startPreview("player", playerFolder));
    assert.equal(job.status, "error");
    assert.match(job.error, /at most 512 player saves/);
  } finally {
    fs.renameSync = originalRename;
    fs.unlinkSync = originalUnlink;
    fs.copyFileSync = originalCopy;
    fs.readFileSync = originalRead;
    global.fetch = originalFetch;
    if (previousDataDir == null) delete process.env.APP_MANAGER_DATA_DIR;
    else process.env.APP_MANAGER_DATA_DIR = previousDataDir;
    assert(path.dirname(folder) === path.resolve(__dirname, ".."), "test cleanup must stay in its workspace");
    fs.rmSync(folder, { recursive: true, force: true });
  }
}

checkWorldArchive().then(() => console.log("Save cleaner registry, preview guards, archive verification and rollback: OK")).catch((error) => { console.error(error); process.exitCode = 1; });
