// lib/discord-routing.js
// Pure, isomorphic helpers for per-world Discord webhook routing. Shared by the
// server (notify.js, supervisor.js) and the Discord settings UI, so it must use NO
// node builtins — it gets bundled into the client too.
//
// A world can define several named webhook "channels" and route each event kind to
// one of them (or to none). The config is stored as JSON in worlds.discord_webhooks:
//   { hooks: [{ id, name, url }], routes: { start: id, ..., chat: id } }
// where a route value of "" means "don't send that event".

// Events that flow through notify(): the server-status lifecycle plus backups.
// These are the kinds the legacy single-webhook backfill auto-routes to the
// default channel, so join/leave are deliberately NOT here — they stay opt-in.
const EVENT_KINDS = ["start", "stop", "restart", "crash", "backup", "update"];
// Player presence events, detected by the background poller (lib/presence.js).
const PLAYER_KINDS = ["join", "leave"];
// Player deaths, fed by the DWSMDeathRelay UE4SS mod. A single "death" routing channel
// carries all death variants (killed by a Pal / by a player / environmental); the
// variant only selects which message TEMPLATE is used, not where it's sent.
const DEATH_KINDS = ["death"];
// "chat" is the in-game chat relay, routed the same way but delivered separately.
const ROUTE_KINDS = [...EVENT_KINDS, ...PLAYER_KINDS, ...DEATH_KINDS, "chat"];
const MAX_HOOKS = 10;

// Death notify sub-kinds -> their default message. Each is a separate template the user
// can override, but all route through the single "death" channel above. Player and Pal
// names are wrapped in **bold** so they stand out in Discord.
const TEMPLATE_DEFAULTS = {
  death_pal: "☠️ **{player}** was slain by **{creature}**",
  death_player: "☠️ **{player}** was killed by **{killer}**",
  death_env: "💀 **{player}** died — {cause}",
};

// Collapse a death sub-kind (death_pal/death_player/death_env) to the "death" routing
// channel; every other kind routes under its own name.
function routingKindFor(kind) {
  return typeof kind === "string" && kind.indexOf("death") === 0 ? "death" : kind;
}

function parseJsonish(v) {
  if (!v) return null;
  if (typeof v === "object") return v;
  try { return JSON.parse(v); } catch { return null; }
}

// Build a sanitized { hooks, routes } for a world. When the new multi-webhook config
// hasn't been saved yet, synthesize an equivalent one from the legacy single-webhook
// fields (discord_webhook + notify_events + discord_relay_chat) so existing setups
// behave exactly as before.
function normalizeDiscord(world) {
  const cfg = parseJsonish(world && world.discord_webhooks);
  if (cfg && Array.isArray(cfg.hooks) && cfg.hooks.length) {
    const hooks = [];
    const seen = new Set();
    for (const h of cfg.hooks.slice(0, MAX_HOOKS)) {
      if (!h || typeof h !== "object") continue;
      const id = String(h.id || "").trim();
      if (!id || seen.has(id)) continue;
      seen.add(id);
      hooks.push({
        id,
        name: String(h.name || "").trim() || "Webhook",
        url: String(h.url || "").trim(),
      });
    }
    const validIds = new Set(hooks.map((h) => h.id));
    const src = (cfg.routes && typeof cfg.routes === "object") ? cfg.routes : {};
    const routes = {};
    for (const k of ROUTE_KINDS) {
      const v = String(src[k] || "").trim();
      routes[k] = validIds.has(v) ? v : "";
    }
    return { hooks, routes };
  }

  // ---- legacy fallback: one "Default Channel" from the old single webhook ----
  // Mirrors the one-time DB backfill so a world that somehow still lacks the saved
  // config behaves identically: events routed to the single webhook, and chat only if
  // the relay was on. The old UI stored per-event on/off switches in notify_events
  // (missing/blank = all on), so honour those — routing an event the user had turned
  // off back to the webhook would silently undo their choice.
  const url = String((world && world.discord_webhook) || "").trim();
  const events = parseJsonish(world && world.notify_events) || {};
  const routes = {};
  for (const k of EVENT_KINDS) routes[k] = (url && events[k] !== false) ? "default" : "";
  routes.chat = (url && world && world.discord_relay_chat) ? "default" : "";
  return { hooks: url ? [{ id: "default", name: "Default Channel", url }] : [], routes };
}

// Resolve the destination webhook URL for one event kind, or "" if it isn't routed
// (either the user chose "don't send", or the routed channel has no URL).
function webhookFor(world, kind) {
  const { hooks, routes } = normalizeDiscord(world);
  const id = routes[routingKindFor(kind)];
  if (!id) return "";
  const hook = hooks.find((h) => h.id === id);
  return hook ? hook.url : "";
}

module.exports = {
  EVENT_KINDS, PLAYER_KINDS, DEATH_KINDS, ROUTE_KINDS, MAX_HOOKS, TEMPLATE_DEFAULTS,
  normalizeDiscord, webhookFor, routingKindFor,
};
