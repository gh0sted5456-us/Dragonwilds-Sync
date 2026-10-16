import { NextResponse } from "next/server";
const remoteauth = require("@/lib/remoteauth");
const syncClient = require("@/lib/sync/client");
const dbm = require("@/lib/db");
const clientIsolation = require("@/lib/client-isolation");
const jobs = require("@/lib/jobs");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  if (jobs.listJobs().some((job) => job.type === "sync" && job.status === "running")) return NextResponse.json({ ok: false, error: "Wait for file synchronization to finish before activating a World profile." }, { status: 409 });
  try {
    const profile = dbm.getProfile(params.id);
    if (!profile) throw new Error("World profile not found");
    const connection = JSON.parse(profile.connection_json || "{}");
    if (connection.localWorld) await clientIsolation.ensureLocalProfileSnapshot(params.id);
    const activation = await syncClient.activateProfileSnapshot(params.id);
    return NextResponse.json({ ok: true, activation });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
