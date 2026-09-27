import { NextResponse } from "next/server";
const rest = require("@/lib/restclient");
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const { command, message, userid, waittime } = await req.json();
  const denied = ra.guardResponse(req, { worldId: params.id, tab: ra.tabForRestCommand(command), action: `rest.${command}`, mutating: true });
  if (denied) return denied;
  try {
    let out;
    switch (command) {
      case "kick": out = await rest.kick(w, userid, message); break;
      case "ban": out = await rest.ban(w, userid, message); break;
      case "unban": out = await rest.unban(w, userid); break;
      case "save": out = await rest.save(w); break;
      case "shutdown": out = await rest.shutdown(w, waittime ?? 30, message); break;
      default: return NextResponse.json({ ok: false, error: "unknown command" }, { status: 400 });
    }
    dbm.logEvent(w.world_id, "admin", `REST ${command}${userid ? " " + userid : ""}`);
    return NextResponse.json({ ok: true, result: out });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 });
  }
}
