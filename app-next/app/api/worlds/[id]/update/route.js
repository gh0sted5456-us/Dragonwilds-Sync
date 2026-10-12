import { NextResponse } from "next/server";
const { startUpdateJob } = require("@/lib/scheduler");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "overview", action: "world.update", mutating: true });
  if (denied) return denied;
  const jobId = startUpdateJob(params.id);
  if (!jobId) return NextResponse.json({ ok: false, error: "World not found" }, { status: 404 });
  return NextResponse.json({ ok: true, jobId });
}
