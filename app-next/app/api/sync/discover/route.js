import { NextResponse } from "next/server";
const discovery = require("@/lib/sync/discovery");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req) {
  try {
    const body = await req.json();
    const worlds = await discovery.probe(body.address || "255.255.255.255", body);
    return NextResponse.json({ ok: true, worlds });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
