import { NextResponse } from "next/server";
const { boot } = require("@/lib/bootstrap");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Kick the background engines (world autostart, scheduler, metrics, presence, Discord
// bots) without a page being open. The desktop app calls this once, right after the
// local server answers, so an autostart-to-tray launch (which shows no window and thus
// loads no page) still brings autostart worlds up and puts the Discord bot online.
//
// Without this, boot() only ran when a page hit a heavier API route — so a hidden login
// launch left everything idle until the user manually opened the window. boot() is
// idempotent (guarded by a global boot sentinel, every engine dedupes via its own
// global flag), so calling this repeatedly, or alongside the route-driven boot(), is a
// harmless no-op.
export async function GET() {
  boot();
  return NextResponse.json({ ok: true });
}
