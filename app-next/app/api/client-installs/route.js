import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const steamlib = require("@/lib/steamlibrary");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const read = () => ({
  steam: dbm.getSetting("clientInstall:steam", null),
  gamepass: dbm.getSetting("clientInstall:gamepass", null),
});

export async function GET() { return NextResponse.json({ ok: true, installs: read() }); }

export async function POST(req) {
  try {
    const body = await req.json();
    for (const platform of ["steam", "gamepass"]) {
      if (!(platform in body)) continue;
      const raw = String(body[platform] || "").trim();
      const normalized = raw ? steamlib.normalizeGameInstall(raw) : null;
      if (raw && !normalized) throw new Error(`${platform === "steam" ? "Steam" : "PC Game Pass"} path is not a Dragonwilds installation. Select the folder containing RSDragonwilds\\Binaries and RSDragonwilds\\Content.`);
      dbm.setSetting(`clientInstall:${platform}`, normalized);
    }
    return NextResponse.json({ ok: true, installs: read() });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
