import { NextResponse } from "next/server";
const remoteauth = require("@/lib/remoteauth");
const saves = require("@/lib/profile-saves");
const saveConverter = require("@/lib/save-converter");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const url = new URL(req.url);
    return NextResponse.json({ ok: true, ...saves.scanCached(url.searchParams.get("profileId") || null) });
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}

export async function POST(req) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const body = await req.json();
    if (body.action === "scan") return NextResponse.json({ ok: true, ...saves.scan(body.profileId || null, body.roots || []) });
    if (body.action === "adopt") return NextResponse.json({ ok: true, item: saves.adopt(body) });
    if (body.action === "assign") return NextResponse.json({ ok: true, item: saves.assign(body.id, body.scope, body.profileId) });
    if (body.action === "extract-wgs") return NextResponse.json({ ok: true, ...saves.extractWgs(body.sourcePath) });
    if (body.action === "create-profile") return NextResponse.json({ ok: true, ...saves.createProfileFromSave(body) });
    if (body.action === "converter") return NextResponse.json({ ok: true, converter: await saveConverter.ensureConverter() });
    throw new Error("Unsupported save-profile action");
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}

export async function DELETE(req) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const id = new URL(req.url).searchParams.get("id");
    return NextResponse.json({ ok: true, removed: saves.remove(id) });
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}
