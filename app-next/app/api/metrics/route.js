import { NextResponse } from "next/server";
const metrics = require("@/lib/metrics");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Live CPU / RAM usage for every running world, plus per-world rolling history.
export async function GET() {
  metrics.ensureSampler();
  return NextResponse.json({ ok: true, ...metrics.getSnapshot() });
}
