import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function GET(req) {
  const wid = new URL(req.url).searchParams.get("world");
  return NextResponse.json({ ok: true, events: dbm.listEvents(wid, 100) });
}
