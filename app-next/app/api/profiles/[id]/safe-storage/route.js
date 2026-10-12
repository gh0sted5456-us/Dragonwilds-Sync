import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const isolation = require("@/lib/client-isolation");
const remoteauth = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function profileInstall(profileId) {
  const profile = dbm.getProfile(profileId);
  if (!profile) throw new Error("World profile not found");
  const connection = JSON.parse(profile.connection_json || "{}");
  const service = ["steam", "epic", "gamepass"].includes(connection.service) ? connection.service : (connection.platform === "gamepass" ? "gamepass" : "steam");
  const install = profile.client_install || dbm.getSetting(`clientInstall:${service}`, null);
  if (!install) throw new Error("Choose this World's game installation before managing native mods.");
  return { profile, service, install };
}

export async function GET(req, { params }) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const { service, install } = profileInstall(params.id);
    return NextResponse.json({ ok: true, storage: isolation.scan(install, service) });
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}

export async function POST(req, { params }) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const { profile, service, install } = profileInstall(params.id);
    const body = await req.json();
    let result;
    if (body.action === "archive") {
      if (!/^[a-f0-9]{64}$/i.test(String(body.fingerprint || ""))) throw new Error("Review the current mod inventory before archiving.");
      result = await isolation.archive(install, service, body.fingerprint);
      if (JSON.parse(profile.connection_json || "{}").localWorld) result.localFork = await isolation.ensureLocalProfileSnapshot(params.id);
    } else if (body.action === "restore") {
      result = await isolation.restore(install, service);
    } else if (body.action === "recover") {
      isolation.assertGameStopped(install);
      await isolation.recoverPendingRestores(install);
      await isolation.recoverPending(install);
      result = { recovered: true };
    } else if (body.action === "fork-local") {
      result = await isolation.ensureLocalProfileSnapshot(params.id);
    } else throw new Error("Unknown Safe Storage action");
    return NextResponse.json({ ok: true, result, storage: isolation.scan(install, service) });
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 409 }); }
}
