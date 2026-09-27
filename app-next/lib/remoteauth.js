// lib/remoteauth.js
// The trust core for Remote Access. PSM is otherwise a single-user, loopback-only app
// with no auth; this module is what makes it safe to expose the local server on the LAN
// (or through a tunnel) so other people can be handed *scoped* control via a short code.
//
// Two kinds of caller exist once Remote Access is ON:
//   • the trusted admin  — the desktop app window (or the browser session that enabled
//     the feature). Proven by an HttpOnly `dwsm_admin` cookie whose value equals the
//     per-launch admin token. NEVER proven by source IP: a raw-TCP tunnel makes a remote
//     guest's request arrive as 127.0.0.1, so IP tells us nothing.
//   • a remote guest    — holds a `dwsm_remote` session cookie tied to a code. Confined to
//     that code's scope (all worlds vs one world) and its allow-list of world tabs.
//
// When Remote Access is OFF (the default) every request is treated as the trusted admin,
// exactly as before this feature existed — the server is loopback-only, so nothing else
// can reach it.
const crypto = require("crypto");
const dbm = require("./db");

const ADMIN_COOKIE = process.env.DWSM_ADMIN_COOKIE || "dwsm_admin";
const SESSION_COOKIE = process.env.DWSM_SESSION_COOKIE || "dwsm_remote";
// A guest session whose last heartbeat was within this window is shown as "active".
const ACTIVE_WINDOW_MS = 45 * 1000;

const S_ENABLED = "remoteAccess.enabled";
const S_LANBIND = "remoteAccess.lanBind";
const S_ADMIN_TOKEN = "remoteAccess.adminToken";

// The world tabs a code can be granted. Mirrors the TABS in app/worlds/[id]/page.jsx.
const ALL_TABS = [
  "overview", "players", "deaths", "map", "broadcast", "chat", "console",
  "settings", "backups", "schedule", "mods", "discord", "discordbot", "admin",
];
// New codes default to everything except the Admin tab (ports, passwords, install dir).
const DEFAULT_TABS = ALL_TABS.filter((t) => t !== "admin");

// ---- feature flags ----
function isEnabled() { return !!dbm.getSetting(S_ENABLED, false); }
function setEnabled(v) { dbm.setSetting(S_ENABLED, !!v); }
function lanBindEnabled() { return !!dbm.getSetting(S_LANBIND, false); }
function setLanBind(v) { dbm.setSetting(S_LANBIND, !!v); }

// ---- request helpers (operate on a NextRequest) ----
function cookie(req, name) {
  try { const c = req.cookies.get(name); if (c) return c.value; } catch {}
  try {
    const raw = req.headers.get("cookie") || "";
    const m = raw.match(new RegExp("(?:^|;\\s*)" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : null;
  } catch { return null; }
}
function clientIp(req) {
  try {
    const xff = req.headers.get("x-forwarded-for");
    if (xff) return xff.split(",")[0].trim();
  } catch {}
  try { return req.ip || null; } catch { return null; }
}
function userAgent(req) { try { return req.headers.get("user-agent") || null; } catch { return null; } }
function isHttps(req) {
  try {
    const proto = req.headers.get("x-forwarded-proto");
    if (proto) return proto.split(",")[0].trim() === "https";
    return new URL(req.url).protocol === "https:";
  } catch { return false; }
}

// ---- admin token / trust ----
// Prefer the per-launch env token the desktop app injects; fall back to a persisted token
// generated on first enable (covers running as a plain web server with no Electron env).
function adminToken() { return process.env.DWSM_ADMIN_TOKEN || dbm.getSetting(S_ADMIN_TOKEN, null); }
function ensureAdminToken() {
  let t = adminToken();
  if (!t) { t = crypto.randomBytes(24).toString("hex"); dbm.setSetting(S_ADMIN_TOKEN, t); }
  return t;
}
function isTrustedAdmin(req) {
  if (!isEnabled()) return true;               // disabled → loopback-only server → full trust
  const tok = adminToken();
  if (!tok) return false;                      // enabled but no token yet → nobody is auto-admin
  return cookie(req, ADMIN_COOKIE) === tok;
}

// ---- codes ----
function tabsOf(code) {
  try { const a = JSON.parse(code.tabs || "[]"); return Array.isArray(a) ? a : []; }
  catch { return []; }
}
function generateCode() {
  const existing = new Set(dbm.listRemoteCodes().map((c) => c.code));
  for (let i = 0; i < 200; i++) {
    const code = String(crypto.randomInt(10000, 100000)); // always 5 digits
    if (!existing.has(code)) return code;
  }
  throw new Error("Could not allocate a unique code.");
}
// Sanitize a caller-supplied tab list down to known ids (drops anything unexpected).
function cleanTabs(tabs) {
  if (!Array.isArray(tabs)) return [];
  return ALL_TABS.filter((t) => tabs.includes(t));
}

// ---- sessions ----
function createSession(codeId, req) {
  const token = crypto.randomBytes(24).toString("hex");
  const now = Date.now();
  dbm.createRemoteSession({
    token, code_id: codeId, created_at: now, last_seen_at: now,
    ip: clientIp(req), user_agent: userAgent(req),
  });
  dbm.touchRemoteCode(codeId, now);
  return token;
}
// Resolve the guest session on a request → { session, code } or null. A disabled or
// deleted code resolves to null, which is what makes disable/delete kick a guest.
function resolveSession(req) {
  const tok = cookie(req, SESSION_COOKIE);
  if (!tok) return null;
  const session = dbm.getRemoteSession(tok);
  if (!session) return null;
  const code = dbm.getRemoteCode(session.code_id);
  if (!code || !code.enabled) return null;
  return { session, code };
}

// ---- audit ----
function audit(req, code, action, worldId, detail) {
  try {
    dbm.logRemoteAudit({
      codeId: code.id,
      codeSnapshot: JSON.stringify({ code: code.code, label: code.label || null, scope: code.scope }),
      action, worldId: worldId || null, detail: detail || null, ip: clientIp(req),
    });
  } catch { /* auditing must never break the request */ }
}

// ---- the guard ----
// opts: { worldId, tab, action, mutating, detail }
//   worldId  — the world the call targets (for scope checks); omit for app-wide calls.
//   tab      — the world tab that governs the call; omit for "any in-scope session" reads
//              (e.g. the base world GET needed to render anything).
//   action   — short label logged to the audit trail when `mutating`.
//   mutating — true for POST/PATCH/DELETE so only real actions are audited, not polls.
// Returns { ok, admin, code?, session?, status?, reason? }.
function authorize(req, opts = {}) {
  if (!isEnabled()) return { ok: true, admin: true };
  if (isTrustedAdmin(req)) return { ok: true, admin: true };

  const rs = resolveSession(req);
  if (!rs) return { ok: false, status: 401, reason: "Not signed in for remote access." };
  const { session, code } = rs;

  if (code.scope === "world" && opts.worldId && code.world_id && opts.worldId !== code.world_id) {
    audit(req, code, "denied", opts.worldId, `world scope`);
    return { ok: false, status: 403, reason: "This code has no access to that world." };
  }
  if (opts.tab && !tabsOf(code).includes(opts.tab)) {
    audit(req, code, "denied", opts.worldId, `tab:${opts.tab}`);
    return { ok: false, status: 403, reason: "This code has no access to that section." };
  }

  dbm.touchRemoteSession(session.token);
  if (opts.action && opts.mutating) audit(req, code, opts.action, opts.worldId, opts.detail);
  return { ok: true, admin: false, code, session };
}

// Admin-only gate for the management API (/api/remote/codes, config).
function requireAdmin(req) { return isTrustedAdmin(req); }

// One-liner for guarding a world route: returns a ready-to-send NextResponse when the
// caller is denied, or null when the call may proceed. Keeps each route to two lines.
function guardResponse(req, opts) {
  const g = authorize(req, opts);
  if (g.ok) return null;
  const { NextResponse } = require("next/server");
  return NextResponse.json({ ok: false, error: g.reason }, { status: g.status || 403 });
}

// Which world tab governs a /rest command (that route is multi-purpose).
function tabForRestCommand(cmd) {
  if (cmd === "kick" || cmd === "ban" || cmd === "unban") return "players";
  if (cmd === "announce") return "broadcast";
  if (cmd === "save" || cmd === "shutdown") return "overview";
  return "admin"; // unknown → most restrictive
}

// What the guest UI needs to know about its own session.
function sessionInfo(code) {
  return {
    scope: code.scope,
    worldId: code.scope === "world" ? code.world_id : null,
    tabs: tabsOf(code),
    label: code.label || null,
  };
}

// ---- brute-force lockout on code entry (in-memory, per ip) ----
const MAX_FAILS = 5;
const LOCK_MS = 60 * 1000;
const attempts = new Map(); // ip -> { fails, lockedUntil }
function lockRemaining(ip) {
  const a = attempts.get(ip || "");
  if (a && a.lockedUntil > Date.now()) return Math.ceil((a.lockedUntil - Date.now()) / 1000);
  return 0;
}
function recordFail(ip) {
  const key = ip || "";
  const a = attempts.get(key) || { fails: 0, lockedUntil: 0 };
  a.fails += 1;
  if (a.fails >= MAX_FAILS) { a.lockedUntil = Date.now() + LOCK_MS; a.fails = 0; }
  attempts.set(key, a);
}
function recordSuccess(ip) { attempts.delete(ip || ""); }

// ---- cookie + CORS helpers (operate on a NextResponse) ----
function cookieOpts(req, maxAge) {
  const secure = isHttps(req);
  // Over an HTTPS tunnel the guest origin can differ from the app origin, so the cookie
  // must be SameSite=None; Secure to survive; on plain-http LAN, Lax is correct.
  return { httpOnly: true, path: "/", sameSite: secure ? "none" : "lax", secure, maxAge };
}
function setSessionCookie(res, req, token) {
  res.cookies.set(SESSION_COOKIE, token, cookieOpts(req, 60 * 60 * 24 * 30));
  return res;
}
function clearSessionCookie(res) {
  res.cookies.set(SESSION_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
function setAdminCookie(res, req) {
  res.cookies.set(ADMIN_COOKIE, ensureAdminToken(), cookieOpts(req, 60 * 60 * 24 * 365));
  return res;
}
function applyCors(res, req) {
  try {
    const origin = req.headers.get("origin");
    if (origin) {
      res.headers.set("Access-Control-Allow-Origin", origin);
      res.headers.set("Access-Control-Allow-Credentials", "true");
      res.headers.append("Vary", "Origin");
    }
    res.headers.set("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS");
    res.headers.set("Access-Control-Allow-Headers", "Content-Type");
  } catch {}
  return res;
}

module.exports = {
  ADMIN_COOKIE, SESSION_COOKIE, ACTIVE_WINDOW_MS, ALL_TABS, DEFAULT_TABS,
  isEnabled, setEnabled, lanBindEnabled, setLanBind,
  adminToken, ensureAdminToken, isTrustedAdmin, requireAdmin, guardResponse,
  generateCode, tabsOf, cleanTabs,
  createSession, resolveSession,
  authorize, tabForRestCommand, sessionInfo, audit,
  lockRemaining, recordFail, recordSuccess,
  clientIp, isHttps,
  setSessionCookie, clearSessionCookie, setAdminCookie, applyCors,
};
