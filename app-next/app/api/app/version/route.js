import { NextResponse } from "next/server";
const appver = require("@/lib/appversion");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Serves the app-version status from the shared cache. A deliberate footer click
// can force a refresh; normal navigation stays on the 30-minute cache.
export async function GET(request) {
  if (new URL(request.url).searchParams.get("refresh") === "1") await appver.refresh();
  const status = await appver.getStatus();
  return NextResponse.json({ ok: true, ...status });
}
