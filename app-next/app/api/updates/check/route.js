import { NextResponse } from "next/server";
const { checkUpdates } = require("@/lib/scheduler");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function GET() {
  const r = await checkUpdates();
  return NextResponse.json({ ok: true, ...r });
}
