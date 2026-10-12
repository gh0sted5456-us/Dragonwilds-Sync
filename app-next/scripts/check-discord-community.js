const assert = require("assert");
const discord = require("../lib/discord-community");

(async () => {
  const oldToken = process.env.RSDW_DISCORD_BOT_TOKEN;
  delete process.env.RSDW_DISCORD_BOT_TOKEN;
  try {
    const community = await discord.loadCommunity(async (url) => {
      if (url.includes("/invites/")) return { ok: true, json: async () => ({ guild: { id: "guild-1", name: "RSDW", icon: "icon" }, approximate_presence_count: 42, approximate_member_count: 250 }) };
      if (url.includes("/widget.json")) return { ok: true, json: async () => ({ members: [{ id: "member-1", username: "Online Ranger", avatar_url: "https://cdn.discordapp.com/widget.png", status: "online" }] }) };
      throw new Error(`Unexpected URL ${url}`);
    }, { force: true });
    assert.equal(community.online, 42);
    assert.equal(community.members, 250);
    assert.equal(community.active[0].name, "Online Ranger");
    assert.equal(community.moderators.length, 0);
    assert(!JSON.stringify(community).includes("token"));
    console.log("Discord community integration: OK");
  } finally {
    if (oldToken == null) delete process.env.RSDW_DISCORD_BOT_TOKEN; else process.env.RSDW_DISCORD_BOT_TOKEN = oldToken;
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
