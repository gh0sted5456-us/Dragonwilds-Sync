import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Guests may reach this cross-origin through an HTTPS tunnel — answer CORS preflight.
export async function OPTIONS(req) {
  return ra.applyCors(new NextResponse(null, { status: 204 }), req);
}

// Enter a code. On success a `dwsm_remote` session cookie is set and the granted scope is
// returned. Wrong codes are rate-limited per IP (5 tries → 60s lockout) — the only thing
// making a 5-digit secret safe on a public tunnel.
export async function POST(req, ctx) {
  if (!ra.isEnabled()) return ra.applyCors(NextResponse.json({ ok: false, error: "Remote access is off." }, { status: 403 }), req);
  const ip = ra.clientIp(req);
  const wait = ra.lockRemaining(ip);
  if (wait > 0) return ra.applyCors(NextResponse.json({ ok: false, error: "Too many attempts.", lockedFor: wait }, { status: 429 }), req);

  let body = {};
  try { body = await req.json(); } catch {}
  const digits = String(body.code || "").replace(/\D/g, "");
  const code = digits ? dbm.getRemoteCodeByCode(digits) : null;
  if (!code) {
    ra.recordFail(ip);
    return ra.applyCors(NextResponse.json({ ok: false, error: "Invalid or disabled code.", lockedFor: ra.lockRemaining(ip) }, { status: 401 }), req);
  }
  ra.recordSuccess(ip);
  const token = ra.createSession(code.id, req);
  ra.audit(req, code, "login", code.scope === "world" ? code.world_id : null, null);
  const res = NextResponse.json({ ok: true, ...ra.sessionInfo(code) });
  return ra.applyCors(ra.setSessionCookie(res, req, token), req);
}

// Heartbeat: the guest UI polls this. Returns the current scope/tabs, or revoked:true once
// the code is disabled/deleted/rescoped so the client can end the session live.
export async function GET(req) {
  if (!ra.isEnabled()) return ra.applyCors(NextResponse.json({ ok: true, revoked: true }), req);
  const rs = ra.resolveSession(req);
  if (!rs) return ra.applyCors(NextResponse.json({ ok: true, revoked: true }), req);
  dbm.touchRemoteSession(rs.session.token);
  return ra.applyCors(NextResponse.json({ ok: true, ...ra.sessionInfo(rs.code) }), req);
}

// Sign out — drop the session row and clear the cookie.
export async function DELETE(req) {
  const tok = req.cookies.get(ra.SESSION_COOKIE)?.value;
  if (tok) { try { dbm.deleteRemoteSession(tok); } catch {} }
  return ra.applyCors(ra.clearSessionCookie(NextResponse.json({ ok: true })), req);
}
