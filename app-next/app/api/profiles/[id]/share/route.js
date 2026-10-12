import { NextResponse } from "next/server";
import crypto from "crypto";
const dbm = require("@/lib/db");
const manifests = require("@/lib/sync/manifest");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const output = (row) => row && ({ ...row, connection: JSON.parse(row.connection_json || "{}"), connection_json: undefined });

export async function POST(req, { params }) {
  try {
    const profile = dbm.getProfile(params.id);
    if (!profile) return NextResponse.json({ ok: false, error: "Player profile not found" }, { status: 404 });
    const body = await req.json();
    const connection = JSON.parse(profile.connection_json || "{}");
    if (body.enabled !== false) {
      // Prove a complete, verified cache exists before advertising anything.
      const temporarilyEnabled = { ...connection, shareEnabled: true, shareCode: connection.shareCode || crypto.randomBytes(5).toString("hex").toUpperCase() };
      const pending = dbm.upsertProfile({ profile_id: params.id, connection: temporarilyEnabled });
      try { manifests.buildProfileManifest(params.id); }
      catch (error) { dbm.upsertProfile({ profile_id: params.id, connection }); throw error; }
      return NextResponse.json({ ok: true, profile: output(pending), shareId: manifests.profileShareId(params.id) });
    }
    const saved = dbm.upsertProfile({ profile_id: params.id, connection: { ...connection, shareEnabled: false } });
    return NextResponse.json({ ok: true, profile: output(saved), shareId: manifests.profileShareId(params.id) });
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}
