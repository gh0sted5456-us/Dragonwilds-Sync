import { NextResponse } from "next/server";
import crypto from "crypto";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function output(row) {
  if (!row) return null;
  let links = {};
  try { links = JSON.parse(row.links_json || "{}"); } catch {}
  const { links_json, ...safe } = row;
  return { ...safe, links };
}

export async function GET(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  const activeId = dbm.getActiveLauncherProfileId();
  return NextResponse.json({ ok: true, activeId, profiles: dbm.listLauncherProfiles().map(output) });
}

export async function POST(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const body = await req.json();
    const profile = dbm.upsertLauncherProfile({ ...body, profile_id: crypto.randomUUID() });
    if (body.activate !== false) dbm.setActiveLauncherProfile(profile.profile_id);
    return NextResponse.json({ ok: true, activeId: dbm.getActiveLauncherProfileId(), profile: output(profile) });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
