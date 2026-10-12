import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  const { profileId } = await req.json();
  const profile = dbm.setActiveLauncherProfile(profileId);
  if (!profile) return NextResponse.json({ ok: false, error: "Profile not found" }, { status: 404 });
  return NextResponse.json({ ok: true, activeId: profile.profile_id });
}
