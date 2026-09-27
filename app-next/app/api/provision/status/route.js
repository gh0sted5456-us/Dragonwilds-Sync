import { NextResponse } from "next/server";
const prov = require("@/lib/provision");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req) {
  const jobId = new URL(req.url).searchParams.get("job");
  const job = prov.getJob(jobId);
  if (!job) return NextResponse.json({ ok: false, error: "job not found" }, { status: 404 });
  return NextResponse.json({ ok: true, job });
}
