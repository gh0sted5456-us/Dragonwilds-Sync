const assert = require("assert");
const social = require("../lib/social-mods");

(async () => {
  const oldNexus = process.env.RSDW_NEXUS_API_KEY;
  const oldCurse = process.env.RSDW_CURSEFORGE_API_KEY;
  delete process.env.RSDW_NEXUS_API_KEY;
  delete process.env.RSDW_CURSEFORGE_API_KEY;
  try {
    const fallback = await social.popularMods(async () => { throw new Error("anonymous mode must not call provider APIs"); });
    assert.equal(fallback.nexus.live, false);
    assert.equal(fallback.curseforge.live, false);
    assert(fallback.nexus.items.length >= 3, "Nexus fallback discovery is empty");
    assert(fallback.nexus.items.some((item) => item.updatedAt), "Nexus fallback has no recent-sort metadata");
    assert(fallback.curseforge.items.length >= 3, "CurseForge fallback discovery is empty");
    assert(fallback.nexus.items.every((item) => /^https:\/\/(?:www\.)?nexusmods\.com\//.test(item.url)), "Nexus fallback contains an unsafe provider URL");
    assert(fallback.curseforge.items.every((item) => /^https:\/\/(?:www\.)?curseforge\.com\//.test(item.url)), "CurseForge fallback contains an unsafe provider URL");

    process.env.RSDW_CURSEFORGE_API_KEY = "test-key";
    const requested = [];
    const response = (payload) => ({ ok: true, json: async () => payload });
    const live = await social.searchMods({ source: "curseforge", query: "rune", author: "maxx", sort: "recent", page: 2, pageSize: 12 }, async (url, options) => {
      requested.push({ url: String(url), options });
      if (String(url).includes("/v1/games?")) return response({ data: [{ id: 9087, slug: "runescape-dragonwilds" }] });
      return response({
        data: [{ id: 44, name: "Rune Tools", summary: "Tools", authors: [{ name: "Maxx" }], downloadCount: 20, dateModified: "2026-10-01T00:00:00Z", links: { websiteUrl: "https://www.curseforge.com/runescape-dragonwilds/ue4ss-mods/rune-tools" } }],
        pagination: { totalCount: 21 },
      });
    });
    const searchRequest = requested.find((entry) => entry.url.includes("/v1/mods/search?"));
    assert(searchRequest, "CurseForge live catalog was not queried");
    const searchUrl = new URL(searchRequest.url);
    assert.equal(searchUrl.searchParams.get("gameId"), "9087");
    assert.equal(searchUrl.searchParams.get("searchFilter"), "rune");
    assert.equal(searchUrl.searchParams.get("index"), "12");
    assert.equal(searchUrl.searchParams.get("pageSize"), "12");
    assert.equal(searchUrl.searchParams.get("sortField"), "3");
    assert.equal(searchRequest.options.headers["x-api-key"], "test-key");
    assert.equal(live.providers.curseforge.live, true);
    assert.equal(live.items[0].author, "Maxx");

    process.env.RSDW_NEXUS_API_KEY = "nexus-test-key";
    let nexusCalls = 0;
    const nexus = await social.searchMods({ source: "nexus", query: "ward", author: "sage", sort: "name", page: 1, pageSize: 24 }, async (url, options) => {
      assert.equal(url, "https://api.nexusmods.com/v2/graphql");
      assert.equal(options.method, "POST");
      assert.equal(options.headers.APIKEY, "nexus-test-key");
      const body = JSON.parse(options.body);
      assert.equal(body.variables.filter.filter[0].gameDomainName.value, "runescapedragonwilds");
      assert.equal(body.variables.filter.filter[1].nameStemmed.value, "ward");
      assert.equal(body.variables.filter.filter[2].author.value, "sage");
      assert.equal(body.variables.sort[0].name.direction, "ASC");
      assert.equal(body.variables.offset, 0);
      assert.equal(body.variables.count, 24);
      nexusCalls += 1;
      const nodes = [{ modId: 7, name: "Ward Tools", author: "Sage", summary: "A ward", downloads: 12, updatedAt: "2026-10-01T00:00:00Z", pictureUrl: "https://staticdelivery.nexusmods.com/test.png" }];
      return response({ data: { mods: { totalCount: 1, nodes } } });
    });
    assert.equal(nexusCalls, 1);
    assert.equal(nexus.providers.nexus.fullCatalog, true);
    assert.equal(nexus.providers.nexus.total, 1);
    assert.equal(nexus.items[0].name, "Ward Tools");
    console.log("Social mod discovery fallbacks: OK");
  } finally {
    if (oldNexus == null) delete process.env.RSDW_NEXUS_API_KEY; else process.env.RSDW_NEXUS_API_KEY = oldNexus;
    if (oldCurse == null) delete process.env.RSDW_CURSEFORGE_API_KEY; else process.env.RSDW_CURSEFORGE_API_KEY = oldCurse;
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
