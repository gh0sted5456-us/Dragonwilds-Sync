// lib/notify.js  (spec §10)
const https = require("https");
const dbm = require("./db");
const { webhookFor, TEMPLATE_DEFAULTS } = require("./discord-routing");

function post(url, payload) {
  return new Promise((resolve) => {
    try {
      const u = new URL(url);
      const data = JSON.stringify(payload);
      const req = https.request(
        { hostname: u.hostname, path: u.pathname + u.search, method: "POST",
          headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } },
        (res) => { res.on("data", () => {}); res.on("end", resolve); }
      );
      req.on("error", resolve);
      req.write(data); req.end();
    } catch { resolve(); }
  });
}

// Parse a world's per-world notify_events JSON. A missing/blank value means "all on".
function notifyEventsFor(world) {
  if (!world || !world.notify_events) return {};
  try { return JSON.parse(world.notify_events) || {}; } catch { return {}; }
}

// A world's custom message template for one event kind, or "" to use the built-in default.
function templateFor(world, kind) {
  if (!world || !world.notify_templates) return "";
  try {
    const map = JSON.parse(world.notify_templates) || {};
    const tpl = map[kind];
    return typeof tpl === "string" && tpl.trim() ? tpl : "";
  } catch { return ""; }
}

// Substitute {token} placeholders from params. Unknown tokens are left untouched so a
// typo shows up plainly rather than silently vanishing.
function renderTemplate(tpl, params) {
  return tpl.replace(/\{(\w+)\}/g, (m, k) => (params[k] != null ? String(params[k]) : m));
}

// Fired by modules on notable events. Each world routes every event kind to one of its
// configured Discord webhooks (or to none). When the world defines a custom template for
// the kind, it's rendered from `params` (+ always-available {world}/{time}) and sent as-is
// (full user control); otherwise the built-in `defaultText` is sent with the legacy
// `**[kind]**` prefix, so existing behaviour is unchanged.
async function notify(worldId, kind, defaultText, params = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) return;
  const url = webhookFor(world, kind);
  if (!url) return;
  // A custom template wins; otherwise a kind may still ship a built-in default template
  // (deaths do, so they render nicely without setup); otherwise the legacy `**[kind]**`
  // prefix on defaultText.
  const tpl = templateFor(world, kind) || TEMPLATE_DEFAULTS[kind] || "";
  const content = tpl
    ? renderTemplate(tpl, { world: world.display_name, time: new Date().toLocaleString(), ...params })
    : `**[${kind}]** ${defaultText}`;
  await post(url, { content });
}

module.exports = { notify, post, notifyEventsFor, renderTemplate, templateFor };
