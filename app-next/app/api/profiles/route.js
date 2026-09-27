import { NextResponse } from "next/server";
import crypto from "crypto";
const dbm = require("@/lib/db");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const publicProfile = (row) => ({ ...row, connection: JSON.parse(row.connection_json || "{}"), connection_json: undefined });

export async function GET() { return NextResponse.json({ ok: true, profiles: dbm.listProfiles().map(publicProfile) }); }
export async function POST(req) {
  try {
    const body = await req.json();
    const row = dbm.upsertProfile({ ...body, profile_id: body.profile_id || crypto.randomUUID() });
    return NextResponse.json({ ok: true, profile: publicProfile(row) });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
