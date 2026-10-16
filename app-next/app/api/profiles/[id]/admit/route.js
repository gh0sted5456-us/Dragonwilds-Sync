import { NextResponse } from "next/server";
const { requestClientAdmission } = require("@/lib/sync/client-admission");
const { safeSyncText } = require("@/lib/sync-progress");
const remoteauth = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try { return NextResponse.json({ ok: true, admission: await requestClientAdmission(params.id) }); }
  catch (error) { return NextResponse.json({ ok: false, error: error.name === "AbortError" ? "The host did not answer the approval request in time." : safeSyncText(error.message) }, { status: 409 }); }
}
