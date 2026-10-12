import { NextResponse } from "next/server";
const jobs = require("@/lib/jobs");
const remote = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req) {
  const desktopToken = req.headers.get("x-rsdw-admin-token");
  if (!remote.requireAdmin(req) && (!desktopToken || desktopToken !== remote.adminToken())) {
    return NextResponse.json({ ok: false, error: "Desktop authorization required" }, { status: 403 });
  }
  try { return NextResponse.json({ ok: true, job: jobs.reportExternalJob(await req.json()) }); }
  catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}
