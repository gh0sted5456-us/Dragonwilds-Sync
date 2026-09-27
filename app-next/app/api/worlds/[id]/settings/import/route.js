import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ini = require("@/lib/ini");
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

  const unquote = (value) => {
    const text = value == null ? "" : String(value);
    if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
      return text.slice(1, -1);
    }
    return text;
  };

  // merge incoming (minus managed keys) onto current ini
  const cur = ini.readSettings(w.install_dir, w.platform).options;
  const merged = { ...cur };
  let applied = 0;
  for (const [k, v] of Object.entries(incoming)) { if (!MANAGED.has(k)) { merged[k] = v; applied++; } }
  // re-assert identity
  merged.PublicPort = String(w.game_port);
  merged.RESTAPIPort = String(w.rest_api_port);
  merged.RESTAPIEnabled = w.rest_api_enabled ? "True" : "False";
  merged.RCONPort = w.rcon_port != null ? String(w.rcon_port) : "";
  merged.AdminPassword = unquote(w.admin_password);
  merged.WorldPassword = unquote(w.server_password);
  merged.OwnerId = w.owner_id || "";
  merged.ServerName = w.display_name || "";
  merged.DefaultWorldName = w.default_world_name || "";
  merged.PublicIP = w.public_ip || "";
  merged.RCONEnabled = w.rcon_enabled ? "True" : "False";
  ini.writeSettings(w.install_dir, merged, w.platform);
  dbm.logEvent(w.world_id, "settings", `Imported ${applied} settings (restart to apply)`);
  return NextResponse.json({ ok: true, applied });
}
