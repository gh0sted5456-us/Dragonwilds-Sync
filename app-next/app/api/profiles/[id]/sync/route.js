import { NextResponse } from "next/server";
const clientSync = require("@/lib/sync/client");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(_req, { params }) {
  try { return NextResponse.json({ ok: true, result: await clientSync.synchronizeProfile(params.id) }); }
  catch (e) { return NextResponse.json({ ok: false, error: e.name === "AbortError" ? "The World did not respond in time" : e.message }, { status: 400 }); }
}
