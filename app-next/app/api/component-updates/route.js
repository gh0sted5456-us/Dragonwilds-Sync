import { NextResponse } from "next/server";
const updates = require("@/lib/component-updates");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req) {
  try {
    const force = new URL(req.url).searchParams.get("force") === "1";
    return NextResponse.json(await updates.getStatus({ force }));
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message, updateAvailable: false, items: [] }, { status: 500 });
  }
}
