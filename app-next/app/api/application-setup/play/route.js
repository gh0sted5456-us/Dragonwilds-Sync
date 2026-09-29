import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const steamlib = require("@/lib/steamlibrary");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function readLane(platform) {
  const installDir = dbm.getSetting(`clientInstall:${platform}`, null);
  return { platform, installDir, ready: !!installDir };
}
function state() {
  return { steam: readLane("steam"), gamepass: readLane("gamepass") };
}

export async function GET() {
  return NextResponse.json({ ok: true, play: state() });
}

export async function POST(req) {
  try {
    const body = await req.json();
    const platform = body.platform === "gamepass" ? "gamepass" : "steam";
    const raw = String(body.installDir || "").trim();
    if (!raw) {
      dbm.setSetting(`clientInstall:${platform}`, null);
      return NextResponse.json({ ok: true, play: state() });
    }
    const normalized = steamlib.normalizeGameInstall(raw);
    if (!normalized) {
      throw new Error(`${platform === "steam" ? "Steam" : "PC Game Pass"} path is not a Dragonwilds installation. Select the folder containing RSDragonwilds\\Binaries and RSDragonwilds\\Content.`);
    }
    dbm.setSetting(`clientInstall:${platform}`, normalized);
    return NextResponse.json({ ok: true, play: state() });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
