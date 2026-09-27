import { NextResponse } from "next/server";
const fs = require("fs");
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");
const { P } = require("@/lib/paths");
const { lanAddresses } = require("@/lib/netinfo");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DEFAULT_PORT = 4317;

// The port the manager UI is actually reachable on = the port of the incoming request.
function managerPort(req) {
  try {
    const host = req.headers.get("host") || "";
    const p = host.split(":")[1];
    if (p) return Number(p);
  } catch {}
  return DEFAULT_PORT;
}

function urls(req) {
  const port = managerPort(req);
  const local = `http://127.0.0.1:${port}/remote`;
  const lan = lanAddresses().map((a) => ({
    address: a.address, primary: a.primary, url: `http://${a.address}:${port}/remote`,
  }));
  return { port, local, lan };
}

// Mirror the LAN-bind choice into a marker file electron/main.js reads at (re)start to
// pick 127.0.0.1 (loopback) vs 0.0.0.0 (LAN-reachable). The DB setting is the source of
// truth; this keeps main.js from needing to open sqlite before the server is up.
function writeBindMarker(lan) {
  try { fs.writeFileSync(P.remoteBind(), JSON.stringify({ host: lan ? "0.0.0.0" : "127.0.0.1" }), "utf8"); }
  catch { /* non-fatal — main.js falls back to loopback */ }
}

function state(req) {
  return {
    enabled: ra.isEnabled(),
    lanBind: ra.lanBindEnabled(),
    ...urls(req),
  };
}

export async function GET(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  return NextResponse.json({ ok: true, ...state(req) });
}

export async function POST(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  let b = {};
  try { b = await req.json(); } catch {}

  let enabledNow = false;
  if ("enabled" in b) { ra.setEnabled(!!b.enabled); enabledNow = !!b.enabled; }
  if ("lanBind" in b) { ra.setLanBind(!!b.lanBind); writeBindMarker(!!b.lanBind); }

  const res = NextResponse.json({ ok: true, ...state(req) });
  // The session that enables Remote Access must stay trusted afterwards: hand it the admin
  // cookie so it isn't locked out the instant the token check turns on.
  if (enabledNow) { ra.ensureAdminToken(); ra.setAdminCookie(res, req); }
  return res;
}
