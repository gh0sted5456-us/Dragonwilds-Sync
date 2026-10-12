import { NextResponse } from "next/server";
const { authorizeWorldRequest, authorizeProfileRequest } = require("@/lib/sync/auth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const playerShare = String(params.id).startsWith("profile-");
  const profileId = playerShare ? String(params.id).slice("profile-".length) : null;
  const auth = playerShare ? authorizeProfileRequest(profileId, req) : authorizeWorldRequest(params.id, req);
  if (!auth.ok) return NextResponse.json({ ok: false, error: auth.error }, { status: auth.status });
  const world = auth.world;
  const profile = auth.profile;
  const connection = profile ? JSON.parse(profile.connection_json || "{}") : null;
  return NextResponse.json({
    ok: true,
    world: {
      id: playerShare ? `profile-${profile.profile_id}` : world.world_id,
      name: profile?.display_name || world.display_name,
      type: playerShare ? "Player Share" : "Dedicated",
      gamePort: world?.game_port || connection?.rules?.gamePort || null,
    },
    serverTime: new Date().toISOString(),
  });
}
