import { NextResponse } from "next/server";
const discovery = require("@/lib/sync/discovery");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() { return NextResponse.json({ ok: true, ...discovery.status() }); }
export async function POST(req) {
  try {
    const body = await req.json();
    return NextResponse.json({ ok: true, ...(body.enabled === false ? discovery.stop() : discovery.start(body.worldId, body)) });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
