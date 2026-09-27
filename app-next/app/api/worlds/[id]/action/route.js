import { NextResponse } from "next/server";
const sup = require("@/lib/supervisor");
const warn = require("@/lib/warn");
const { notify } = require("@/lib/notify");
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const { action } = await req.json();
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "overview", action: `world.${action}`, mutating: true });
  if (denied) return denied;
  try {
    let result;
    if (action === "start") { result = await sup.startWorld(params.id); notify(params.id, "start", `${w.display_name} started`); }
    // The manual Stop button is a deliberate admin action — stop the world promptly
    // with a graceful (native ~15s) shutdown, not a multi-minute warning countdown.
    // Player warnings apply to *scheduled* stops/restarts (unattended) and to the
    // Restart button; a hands-on Stop should not wait out warn_lead_minutes. Force-stop
    // (below) is the immediate SIGKILL escape hatch.
    else if (action === "stop") { result = await sup.stopWorld(params.id, { graceful: true }); notify(params.id, "stop", `${w.display_name} stopped`); }
    else if (action === "restart") {
      // If this world warns players before shutdown, the countdown can run for
      // several minutes — don't block the HTTP request on it. Kick the warned
      // restart off in the background and return immediately.
      if (warn.shouldWarn(w, sup.isRunning, params.id)) {
        notify(params.id, "restart", `${w.display_name} restarting — warning players first`);
        warn.warnedRestart(params.id);
        return NextResponse.json({ ok: true, result: { warned: true, leadMinutes: w.warn_lead_minutes } });
      }
      result = await sup.restartWorld(params.id); notify(params.id, "restart", `${w.display_name} restarted`);
    }
    else if (action === "force-stop") { result = await sup.stopWorld(params.id, { graceful: false }); }
    else return NextResponse.json({ ok: false, error: "unknown action" }, { status: 400 });
    return NextResponse.json({ ok: true, result });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 });
  }
}
