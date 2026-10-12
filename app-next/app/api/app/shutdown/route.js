import { NextResponse } from "next/server";
const sup = require("@/lib/supervisor");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Desktop-only lifecycle endpoint. Electron supplies a per-launch secret that is
// also injected into the local Next process; LAN/remote clients never receive it.
export async function POST(req) {
  const expected = String(process.env.DWSM_ADMIN_TOKEN || "");
  const supplied = String(req.headers.get("x-rsdw-admin-token") || "");
  if (!expected || supplied !== expected) {
    return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  }

  const results = await sup.stopManagedWorlds({ waittime: 5 });
  return NextResponse.json({ ok: true, results });
}
