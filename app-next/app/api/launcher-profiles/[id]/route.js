import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const LINK_HOSTS = {
  steam: ["steamcommunity.com", "store.steampowered.com"],
  epic: ["epicgames.com", "www.epicgames.com"],
  curseforge: ["curseforge.com", "www.curseforge.com"],
  nexus: ["nexusmods.com", "www.nexusmods.com"],
};

function cleanLinks(input) {
  const result = {};
  for (const [key, hosts] of Object.entries(LINK_HOSTS)) {
    const value = String(input?.[key] || "").trim();
    if (!value) { result[key] = ""; continue; }
    const url = new URL(value);
    if (url.protocol !== "https:" || !hosts.some((host) => url.hostname === host || url.hostname.endsWith(`.${host}`))) {
      throw new Error(`${key} must be an HTTPS link on ${hosts[0]}`);
    }
    result[key] = url.toString();
  }
  return result;
}

function cleanImage(value, label, maxBytes) {
  if (!value) return null;
  const text = String(value);
  if (!/^data:image\/(png|jpe?g|webp);base64,/i.test(text)) throw new Error(`${label} must be a PNG, JPEG, or WebP image.`);
  if (text.length > Math.ceil(maxBytes * 1.4)) throw new Error(`${label} is too large.`);
  return text;
}

function output(row) {
  if (!row) return null;
  const { links_json, ...safe } = row;
  let links = {};
  try { links = JSON.parse(links_json || "{}"); } catch {}
  return { ...safe, links };
}

export async function GET(req, { params }) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  const profile = dbm.getLauncherProfile(params.id);
  if (!profile) return NextResponse.json({ ok: false, error: "Profile not found" }, { status: 404 });
  const playerIds = new Set(dbm.listLauncherProfileWorldIds(profile.profile_id, "player"));
  const serverIds = new Set(dbm.listLauncherProfileWorldIds(profile.profile_id, "server"));
  return NextResponse.json({
    ok: true,
    profile: output(profile),
    worlds: dbm.listProfiles().filter((row) => playerIds.has(row.profile_id)).map((row) => ({ profile_id: row.profile_id, display_name: row.display_name })),
    servers: dbm.listWorlds().filter((row) => serverIds.has(row.world_id)).map((row) => ({ world_id: row.world_id, display_name: row.display_name, status: row.status })),
  });
}

export async function PATCH(req, { params }) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const current = dbm.getLauncherProfile(params.id);
    if (!current) return NextResponse.json({ ok: false, error: "Profile not found" }, { status: 404 });
    const body = await req.json();
    const patch = { profile_id: params.id };
    if (body.display_name !== undefined) patch.display_name = body.display_name;
    if (body.icon_data !== undefined) patch.icon_data = cleanImage(body.icon_data, "Icon", 1024 * 1024);
    if (body.banner_data !== undefined) patch.banner_data = cleanImage(body.banner_data, "Banner", 3 * 1024 * 1024);
    if (body.links !== undefined) patch.links = cleanLinks(body.links);
    return NextResponse.json({ ok: true, profile: output(dbm.upsertLauncherProfile(patch)) });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}

export async function DELETE(req, { params }) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  const result = dbm.deleteLauncherProfile(params.id);
  if (!result.changes) return NextResponse.json({ ok: false, error: "At least one profile must remain." }, { status: 409 });
  return NextResponse.json({ ok: true, ...result, activeId: dbm.getActiveLauncherProfileId() });
}
