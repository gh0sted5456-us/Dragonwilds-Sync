// PalSchema support removed: this route is intentionally disabled.
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST() {
  return NextResponse.json({ ok: false, error: "PalSchema support removed" }, { status: 410 });
}
