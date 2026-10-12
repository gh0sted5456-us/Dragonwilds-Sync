import { NextResponse } from "next/server";
const syncManifest = require("@/lib/sync/manifest");
const { authorizeWorldRequest, signWorldAdmission } = require("@/lib/sync/auth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  try {
    if (String(params.id).startsWith("profile-")) return NextResponse.json({ ok: false, error: "Player shares do not issue server admission" }, { status: 400 });
    const auth = authorizeWorldRequest(params.id, req);
    if (!auth.ok) return NextResponse.json({ ok: false, error: auth.error }, { status: auth.status });
    const platform = req.headers.get("x-rsdw-client-platform") === "gamepass" ? "gamepass" : "steam";
    const manifest = syncManifest.buildWorldManifest(params.id, { platform });
    const attestation = await req.json();
    const verified = syncManifest.verifyClientAttestation(manifest, attestation);
    const permit = signWorldAdmission(params.id, manifest.revision);
    return NextResponse.json({ ok: true, admission: { ...verified, token: permit.token, expiresAt: permit.expires, approvedAt: Date.now(), world: { id: manifest.world.id, name: manifest.world.name, gamePort: manifest.world.gamePort, type: manifest.world.type } } });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 409 });
  }
}
