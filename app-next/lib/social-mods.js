const NEXUS_GAME = "runescapedragonwilds";
const CURSE_GAME_SLUG = "runescape-dragonwilds";
const credentials = require("./provider-credentials");
let curseGameId = null;
const NEXUS_QUERY = `query RsdwMods($filter: ModsFilter, $sort: [ModsSort!], $count: Int, $offset: Int) {
  mods(filter: $filter, sort: $sort, count: $count, offset: $offset) {
    totalCount
    nodes { modId name summary author updatedAt createdAt downloads pictureUrl version uploader { name } }
  }
}`;

const fallbacks = {
  nexus: [
    { id: "nexus-ue4ss", name: "UE4SS for RSDragonwilds", author: "UE4SS-RE", summary: "The scripting loader used by many Dragonwilds mods.", updatedAt: "2026-09-18T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/4" },
    { id: "nexus-298", name: "No Carry Capacity", author: "ModsByTat", summary: "Tunable carry-capacity limits for standard Worlds.", updatedAt: "2026-09-19T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/298" },
    { id: "nexus-142", name: "GreaterRocksplosion", author: "WarrenKD", summary: "Increase the damage, power, and range of the Rocksplosion spell.", updatedAt: "2026-09-20T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/142" },
    { id: "nexus-307", name: "Lose Nothing on Death", author: "ModsByTat", summary: "Keep carried items when a character dies.", updatedAt: "2026-09-19T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/307" },
    { id: "nexus-334", name: "Magic While Moving", author: "ModsByTat", summary: "Use magic attacks while moving through the World.", updatedAt: "2026-09-18T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/334" },
    { id: "nexus-343", name: "Quick Deposit to Chests", author: "Solaris710", summary: "Quickly deposit items already stored in nearby chests.", updatedAt: "2026-06-28T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/343" },
    { id: "nexus-150", name: "Greater Carry Capacity", author: "WarrenKD", summary: "Increase the default character carry weight.", updatedAt: "2026-09-19T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/150" },
    { id: "nexus-157", name: "Greater Tempest Shield", author: "WarrenKD", summary: "Extend and strengthen the Tempest Shield spell.", updatedAt: "2026-09-20T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/157" },
    { id: "nexus-345", name: "Stack Size and Weight Mod", author: "ModsByTat", summary: "Large item stacks with zero item weight for dedicated or solo Worlds.", updatedAt: "2026-09-18T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/345" },
    { id: "nexus-140", name: "Greater Splinter", author: "WarrenKD", summary: "Increase the effectiveness of the Splinter spell.", updatedAt: "2026-09-20T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/140" },
    { id: "nexus-154", name: "Greater Enchant Weapon", author: "WarrenKD", summary: "Buff fire and air weapon enchants and reduce their cooldown.", updatedAt: "2026-09-20T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/154" },
    { id: "nexus-276", name: "Faster Miniboss Respawns", author: "CareBear", summary: "Respawn minibosses and rare-drop monsters after one day.", updatedAt: "2026-09-22T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/276" },
    { id: "nexus-295", name: "No Building Stability", author: "ModsByTat", summary: "Remove building-stability requirements in standard Worlds.", updatedAt: "2026-09-19T00:00:00Z", url: "https://www.nexusmods.com/runescapedragonwilds/mods/295" },
  ],
  curseforge: [
    { id: "curse-rune-ui", name: "Rune UI", author: "Dragonwilds community", summary: "Move, resize, fade, or hide HUD elements in game.", url: "https://www.curseforge.com/runescape-dragonwilds/ue4ss-mods/rune-ui" },
    { id: "curse-mod-menu", name: "Mod Menu", author: "Dragonwilds community", summary: "Configure compatible mods from Dragonwilds' in-game menu.", url: "https://www.curseforge.com/runescape-dragonwilds/ue4ss-mods/mod-menu" },
    { id: "curse-minimap", name: "Minimap", author: "Dragonwilds community", summary: "A lightweight configurable minimap using the native map system.", url: "https://www.curseforge.com/runescape-dragonwilds/ue4ss-mods/minimap" },
  ],
};

function clean(value, max = 120) { return String(value || "").trim().slice(0, max); }
function matches(item, query, author) {
  const q = query.toLowerCase();
  const a = author.toLowerCase();
  return (!q || `${item.name} ${item.summary || ""} ${item.author || ""}`.toLowerCase().includes(q))
    && (!a || String(item.author || "").toLowerCase().includes(a));
}
function order(items, sort) {
  return [...items].sort((a, b) => {
    if (sort === "name") return String(a.name).localeCompare(String(b.name));
    if (sort === "recent") return Date.parse(b.updatedAt || 0) - Date.parse(a.updatedAt || 0);
    return Number(b.downloads || 0) - Number(a.downloads || 0);
  });
}
function nexusBrowseUrl(query, author) {
  const params = new URLSearchParams();
  if (query) params.set("search", query);
  if (author) params.set("author", author);
  const suffix = params.toString();
  return `https://www.nexusmods.com/games/${NEXUS_GAME}/mods${suffix ? `?${suffix}` : ""}`;
}
function curseBrowseUrl(query, author, sort) {
  const params = new URLSearchParams({ page: "1", pageSize: "20", sortBy: sort === "recent" ? "latest update" : sort === "name" ? "name" : "popularity" });
  if (query || author) params.set("search", [query, author].filter(Boolean).join(" "));
  return `https://www.curseforge.com/${CURSE_GAME_SLUG}/search?${params}`;
}

function nexusItem(mod) {
  return { id: `nexus-${mod.modId}`, name: mod.name, author: mod.author || mod.uploader?.name, summary: mod.summary, downloads: mod.downloads, updatedAt: mod.updatedAt || mod.createdAt || null, image: mod.pictureUrl || null, version: mod.version || null, url: `https://www.nexusmods.com/${NEXUS_GAME}/mods/${mod.modId}` };
}

async function fetchNexusPage(key, { query, author, sort, page, pageSize }, fetchImpl) {
  const filter = [{ gameDomainName: { value: NEXUS_GAME, op: "EQUALS" } }];
  if (query) filter.push({ nameStemmed: { value: query, op: "MATCHES" } });
  if (author) filter.push({ author: { value: author, op: "MATCHES" } });
  const sortValue = sort === "name" ? { name: { direction: "ASC" } } : sort === "recent" ? { updatedAt: { direction: "DESC" } } : { downloads: { direction: "DESC" } };
  const response = await fetchImpl("https://api.nexusmods.com/v2/graphql", {
    method: "POST",
    headers: { ...(key ? { APIKEY: key } : {}), "Content-Type": "application/json", "Application-Name": "RSDW-Sync", "Application-Version": "0.1.1" },
    body: JSON.stringify({ query: NEXUS_QUERY, variables: { filter: { filter }, sort: [sortValue], count: pageSize, offset: (page - 1) * pageSize } }),
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) throw new Error(`Nexus Mods returned HTTP ${response.status}`);
  const payload = await response.json();
  if (payload?.errors?.length) throw new Error(`Nexus Mods: ${payload.errors.map((error) => error.message).join("; ")}`);
  const result = payload?.data?.mods || {};
  return { total: Number(result.totalCount || 0), nodes: Array.isArray(result.nodes) ? result.nodes : [] };
}

async function nexusCatalog({ query = "", author = "", sort = "popular", page = 1, pageSize = 12 } = {}, fetchImpl = fetch) {
  const key = credentials.apiKey("nexus");
  let source = fallbacks.nexus;
  let live = false;
  let note = "Nexus Mods catalog is temporarily unavailable; showing the bundled discovery preview.";
  try {
    const result = await fetchNexusPage(key, { query, author, sort, page, pageSize }, fetchImpl);
    source = result.nodes.map(nexusItem);
    live = true;
    note = null;
    return { items: source, total: result.total, live, fullCatalog: true, note, searchUrl: nexusBrowseUrl(query, author) };
  } catch { /* Keep the bundled preview when Nexus is offline or rate-limited. */ }
  const filtered = order(source.filter((item) => matches(item, query, author)), sort);
  const start = (page - 1) * pageSize;
  return { items: filtered.slice(start, start + pageSize), total: filtered.length, live, fullCatalog: live, note, searchUrl: nexusBrowseUrl(query, author) };
}

async function resolveCurseGame(headers, fetchImpl) {
  if (curseGameId) return curseGameId;
  const response = await fetchImpl(`https://api.curseforge.com/v1/games?slug=${CURSE_GAME_SLUG}`, { headers, signal: AbortSignal.timeout(12000) });
  if (!response.ok) throw new Error(`CurseForge games returned HTTP ${response.status}`);
  const payload = await response.json();
  const game = (payload?.data || []).find((item) => item.slug === CURSE_GAME_SLUG) || payload?.data?.[0];
  if (!game?.id) throw new Error("CurseForge did not identify RuneScape: Dragonwilds");
  curseGameId = game.id;
  return curseGameId;
}

async function curseCatalog({ query = "", author = "", sort = "popular", page = 1, pageSize = 12 } = {}, fetchImpl = fetch) {
  const key = credentials.apiKey("curseforge");
  const searchUrl = curseBrowseUrl(query, author, sort);
  if (!key) {
    const filtered = order(fallbacks.curseforge.filter((item) => matches(item, query, author)), sort);
    const start = (page - 1) * pageSize;
    return { items: filtered.slice(start, start + pageSize), total: filtered.length, live: false, fullCatalog: false, note: "Connect a CurseForge API key in Settings → Mod sources to browse the complete Dragonwilds catalog.", searchUrl };
  }
  const headers = { "x-api-key": key, Accept: "application/json" };
  const gameId = await resolveCurseGame(headers, fetchImpl);
  const params = new URLSearchParams({ gameId: String(gameId), sortField: sort === "recent" ? "3" : sort === "name" ? "4" : "6", sortOrder: sort === "name" ? "asc" : "desc", index: String((page - 1) * pageSize), pageSize: String(pageSize) });
  if (query || author) params.set("searchFilter", query || author);
  const response = await fetchImpl(`https://api.curseforge.com/v1/mods/search?${params}`, { headers, signal: AbortSignal.timeout(12000) });
  if (!response.ok) throw new Error(`CurseForge returned HTTP ${response.status}`);
  const payload = await response.json();
  const items = (payload?.data || []).map((mod) => ({ id: `curse-${mod.id}`, name: mod.name, author: mod.authors?.[0]?.name, summary: mod.summary, downloads: mod.downloadCount, updatedAt: mod.dateModified || mod.latestFiles?.[0]?.fileDate || null, image: mod.logo?.thumbnailUrl || mod.logo?.url || null, url: mod.links?.websiteUrl || searchUrl })).filter((item) => matches(item, query, author));
  const total = author && query ? items.length : Number(payload?.pagination?.totalCount ?? items.length);
  return { items, total, live: true, fullCatalog: true, note: null, searchUrl };
}

async function popularMods(fetchImpl = fetch) {
  const [nexus, curseforge] = await Promise.allSettled([nexusCatalog({ pageSize: 24 }, fetchImpl), curseCatalog({ pageSize: 24 }, fetchImpl)]);
  return {
    nexus: nexus.status === "fulfilled" ? nexus.value : { items: fallbacks.nexus, live: false, note: nexus.reason?.message || "Nexus Mods is unavailable." },
    curseforge: curseforge.status === "fulfilled" ? curseforge.value : { items: fallbacks.curseforge, live: false, note: curseforge.reason?.message || "CurseForge is unavailable." },
  };
}

async function searchMods(options = {}, fetchImpl = fetch) {
  const query = clean(options.query);
  const author = clean(options.author);
  const source = ["nexus", "curseforge"].includes(options.source) ? options.source : "all";
  const sort = ["popular", "recent", "name"].includes(options.sort) ? options.sort : "popular";
  const page = Math.max(1, Math.min(500, Number(options.page) || 1));
  const pageSize = Math.max(1, Math.min(24, Number(options.pageSize) || 12));
  const eachSize = pageSize;
  const requested = source === "all" ? ["nexus", "curseforge"] : [source];
  const settled = await Promise.allSettled(requested.map((provider) => provider === "nexus"
    ? nexusCatalog({ query, author, sort, page, pageSize: eachSize }, fetchImpl)
    : curseCatalog({ query, author, sort, page, pageSize: eachSize }, fetchImpl)));
  const providers = {};
  requested.forEach((provider, index) => {
    const result = settled[index];
    providers[provider] = result.status === "fulfilled" ? result.value : { items: [], total: 0, live: false, fullCatalog: false, note: result.reason?.message || `${provider} is unavailable.`, searchUrl: provider === "nexus" ? nexusBrowseUrl(query, author) : curseBrowseUrl(query, author, sort) };
  });
  const items = order(Object.entries(providers).flatMap(([provider, value]) => value.items.map((item) => ({ ...item, provider }))), sort).slice(0, pageSize);
  const total = Object.values(providers).reduce((sum, value) => sum + Number(value.total || 0), 0);
  const pages = Math.max(1, ...Object.values(providers).map((value) => Math.ceil(Number(value.total || 0) / eachSize)));
  return { items, total, page, pageSize, pages, providers };
}

module.exports = { fallbacks, popularMods, searchMods, nexusBrowseUrl, curseBrowseUrl };
