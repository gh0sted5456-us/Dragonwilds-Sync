import { NextResponse } from "next/server";
const { updateAll } = require("@/lib/scheduler");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function POST() {
  const results = await updateAll();
  return NextResponse.json({ ok: true, results });
}
