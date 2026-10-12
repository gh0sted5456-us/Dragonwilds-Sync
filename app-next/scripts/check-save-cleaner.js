const assert = require("assert");
const cleaner = require("../lib/save-cleaner");

const ids = (prefix, count) => Array.from({ length: count }, (_, index) => `${prefix}-${index}`);
const itemIds = ids("item", 120);
const recipeIds = ids("recipe", 120);
const questIds = ids("quest", 20);
const catalog = cleaner.catalogFromPayloads({
  manifest: { game_root: "RSDWArchive/1.0.0-test", generated_at_utc: "2026-10-11T00:00:00Z" },
  items: { tabs: { bag: { items: itemIds.map((itemData) => ({ itemData })) } } },
  recipes: recipeIds.map((persistence_id) => ({ persistence_id })),
  quests: { version: "1.0.0-test", quests: questIds.map((persistence_id) => ({ persistence_id })) },
});

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

console.log("Save cleaner registry and preservation contract: OK");
