import { NextResponse } from "next/server";
const remoteauth = require("@/lib/remoteauth");
const syncClient = require("@/lib/sync/client");
const dbm = require("@/lib/db");
const profileSaves = require("@/lib/profile-saves");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const profile = dbm.getProfile(params.id);
    if (!profile) throw new Error("World profile not found");
    const connection = JSON.parse(profile.connection_json || "{}");
    const activation = connection.localWorld
      ? { profileId: params.id, localWorld: true, deployment: { hardlink: 0, symlink: 0, copy: 0, unchanged: 0, removed: 0 }, saves: profileSaves.activateForProfile(params.id), changed: 0 }
      : await syncClient.activateProfileSnapshot(params.id);
    return NextResponse.json({ ok: true, activation });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
