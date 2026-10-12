const INVITE_CODE = "bQrVAbA7UC";
let cache = null;

function avatarUrl(user) {
  if (!user?.id || !user?.avatar) return null;
  return `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png?size=96`;
}

function publicMember(member, role = null) {
  const user = member?.user || member;
  return {
    id: String(user?.id || member?.id || ""),
    name: String(member?.nick || user?.global_name || user?.username || member?.username || "Discord member").slice(0, 80),
    avatar: member?.avatar_url || avatarUrl(user),
    status: member?.status || null,
    role,
  };
}

async function readJson(fetchImpl, url, init = {}) {
  const response = await fetchImpl(url, { ...init, signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error(`Discord returned HTTP ${response.status}`);
  return response.json();
}

async function moderatorRoster(fetchImpl, guildId) {
  const token = String(process.env.RSDW_DISCORD_BOT_TOKEN || "").trim();
  if (!token || !guildId) return { moderators: [], note: "Moderator roster becomes available when the community bot is connected." };
  const headers = { Authorization: `Bot ${token}` };
  const [roles, members] = await Promise.all([
    readJson(fetchImpl, `https://discord.com/api/v10/guilds/${guildId}/roles`, { headers }),
    readJson(fetchImpl, `https://discord.com/api/v10/guilds/${guildId}/members?limit=1000`, { headers }),
  ]);
  const configured = new Set(String(process.env.RSDW_DISCORD_MODERATOR_ROLE_IDS || "").split(",").map((id) => id.trim()).filter(Boolean));
  const modRoles = new Map((roles || []).filter((role) => configured.has(String(role.id)) || /owner|admin|moderator|staff/i.test(String(role.name || ""))).map((role) => [String(role.id), String(role.name)]));
  const moderators = (members || []).filter((member) => (member.roles || []).some((id) => modRoles.has(String(id)))).slice(0, 12).map((member) => {
    const roleId = (member.roles || []).find((id) => modRoles.has(String(id)));
    return publicMember(member, modRoles.get(String(roleId)) || "Community team");
  });
  return { moderators, note: moderators.length ? null : "No moderator roles were returned by Discord." };
}

async function loadCommunity(fetchImpl = fetch, options = {}) {
  if (!options.force && cache && Date.now() - cache.at < 5 * 60 * 1000) return cache.value;
  const invite = await readJson(fetchImpl, `https://discord.com/api/v10/invites/${INVITE_CODE}?with_counts=true&with_expiration=true`);
  const guildId = String(invite.guild?.id || "");
  let widget = null;
  try { if (guildId) widget = await readJson(fetchImpl, `https://discord.com/api/guilds/${guildId}/widget.json`); }
  catch { /* public widget is optional */ }
  let team;
  try { team = await moderatorRoster(fetchImpl, guildId); }
  catch { team = { moderators: [], note: "Moderator roster is temporarily unavailable." }; }
  const active = (widget?.members || []).slice(0, 10).map((member) => publicMember(member));
  const value = {
    invite: `https://discord.gg/${INVITE_CODE}`,
    guild: { id: guildId || null, name: invite.guild?.name || "Dragonwilds Creative and Sharing Hub", icon: invite.guild?.icon ? `https://cdn.discordapp.com/icons/${guildId}/${invite.guild.icon}.png?size=128` : null },
    online: Number(invite.approximate_presence_count || active.length || 0),
    members: Number(invite.approximate_member_count || 0),
    active,
    moderators: team.moderators,
    moderatorNote: team.note,
    widgetEnabled: !!widget,
  };
  cache = { at: Date.now(), value };
  return value;
}

module.exports = { INVITE_CODE, loadCommunity, publicMember };
