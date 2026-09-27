import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const output = (row) => row && ({ ...row, connection: JSON.parse(row.connection_json || "{}"), connection_json: undefined });
export async function GET(_req, { params }) {
  const profile = dbm.getProfile(params.id);
  return profile ? NextResponse.json({ ok: true, profile: output(profile) }) : NextResponse.json({ ok: false, error: "Profile not found" }, { status: 404 });
}
export async function PATCH(req, { params }) {
  try { return NextResponse.json({ ok: true, profile: output(dbm.upsertProfile({ ...(await req.json()), profile_id: params.id })) }); }
  catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
export async function DELETE(_req, { params }) { dbm.deleteProfile(params.id); return NextResponse.json({ ok: true }); }
