import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ini = require("@/lib/ini");
const active = require("@/lib/active-server-profile");
const AdmZip = require("adm-zip");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MANAGED = new Set(["PublicPort","RESTAPIPort","RESTAPIEnabled","RCONPort","RCONEnabled","AdminPassword","WorldPassword","OwnerId","ServerName","DefaultWorldName","PublicIP"]);

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "settings", action: "settings.import", mutating: true });
  if (denied) return denied;
  const body = await req.json();  // { zipBase64 } or { iniText }
  let iniText = body.iniText;
  try {
    if (body.zipBase64) {
      const zip = new AdmZip(Buffer.from(body.zipBase64, "base64"));
      const entry = zip.getEntries().find((e) => e.entryName.endsWith(".ini"));
      if (!entry) return NextResponse.json({ ok: false, error: "No .ini in zip" }, { status: 400 });
      iniText = entry.getData().toString("utf8");
    }
  } catch (e) { return NextResponse.json({ ok: false, error: "Bad zip: " + e.message }, { status: 400 }); }
  if (!iniText) return NextResponse.json({ ok: false, error: "Nothing to import" }, { status: 400 });

  const incoming = ini.parseOptionSettings(iniText);
  if (!Object.keys(incoming).length) return NextResponse.json({ ok: false, error: "No OptionSettings found" }, { status: 400 });


  const profile = active.settingsFor(w);
  const merged = { ...profile.values };
  let applied = 0;
  for (const [k, v] of Object.entries(incoming)) {
    if (!MANAGED.has(k)) {
      merged[k] = v;
      applied++;
    }
  }

  const normalized = ini.withWorldNetworkSettings(merged, w);
  active.saveSettings(w.world_id, normalized, { baseRaw: profile.content });
  const isActive = active.readActiveId() === w.world_id;
  if (isActive) active.materialize(w);

  dbm.logEvent(w.world_id, "settings", `Imported ${applied} settings into Server profile (restart to apply)`);
  return NextResponse.json({ ok: true, applied, active: isActive });
}
