import { NextResponse } from "next/server";
const discord = require("@/lib/discord-community");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try { return NextResponse.json({ ok: true, community: await discord.loadCommunity() }); }
  catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 502 }); }
}
