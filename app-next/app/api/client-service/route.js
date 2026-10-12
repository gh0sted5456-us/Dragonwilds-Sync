import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const steamlib = require("@/lib/steamlibrary");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const body = await req.json();
    const profile = body.profileId ? dbm.getProfile(body.profileId) : null;
    const connection = profile ? JSON.parse(profile.connection_json || "{}") : {};
    const preferred = ["steam", "epic", "gamepass"].includes(body.service) ? body.service : null;
    const fallbackInstall = preferred ? dbm.getSetting(`clientInstall:${preferred}`, null) : null;
    const resolved = steamlib.resolveClientInstallation(body.installDir || profile?.client_install || fallbackInstall || body.executablePath, {
      executablePath: body.executablePath || connection.executablePath || null,
      savePath: body.savePath ?? connection.savePath ?? null,
      preferred,
    });
    if (!resolved) throw new Error("Choose a Dragonwilds game folder or executable before detecting its service.");
    if (body.persist && profile) {
      const nextConnection = {
        ...connection,
        service: resolved.service,
        platform: resolved.modPlatform,
        executablePath: resolved.executablePath,
        savePath: resolved.savePath,
        serviceDetection: { confidence: resolved.confidence, reasons: resolved.reasons, detectedAt: Date.now() },
      };
      dbm.upsertProfile({ profile_id: profile.profile_id, client_install: resolved.installDir, connection: nextConnection });
    }
    return NextResponse.json({ ok: true, installation: resolved });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
