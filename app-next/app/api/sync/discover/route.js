import { NextResponse } from "next/server";
const discovery = require("@/lib/sync/discovery");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Local administrator access required." }, { status: 403 });
  try {
    const body = await req.json();
    const address = String(body.address || "").trim();
    const worlds = body.mode === "lan" || !address || address === "255.255.255.255"
      ? await discovery.probe()
      : await discovery.probeDirect(address);
    return NextResponse.json({ ok: true, worlds });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
