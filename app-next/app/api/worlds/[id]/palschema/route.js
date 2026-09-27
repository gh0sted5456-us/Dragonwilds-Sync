// PalSchema support removed: this route is no longer available.
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ ok: false, error: "PalSchema support removed" }, { status: 410 });
}

export async function POST() {
  return NextResponse.json({ ok: false, error: "PalSchema support removed" }, { status: 410 });
}
