import { NextResponse } from "next/server";
const detect = require("@/lib/detect");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function GET(req) {
  const p = new URL(req.url).searchParams.get("path");
  if (!p) return NextResponse.json({ ok: false, error: "path required" }, { status: 400 });
  const info = detect.inspect(p);
  return NextResponse.json({ ok: true, info });
}
