import { NextResponse } from "next/server";
const crypto = require("crypto");
const dbm = require("@/lib/db");
const { ensureScheduler } = require("@/lib/scheduler");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "schedule" });
  if (denied) return denied;
  return NextResponse.json({ ok: true, schedules: dbm.listSchedules(params.id) });
}

const JOB_TYPES = ["restart", "stop", "backup", "update", "system_message", "idle_stop", "custom_http"];
const MODES = ["interval", "daily", "minutes", "on_join"];
const MESSAGE_JOBS = ["system_message"];
const HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];

export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "schedule", action: "schedule.create", mutating: true });
  if (denied) return denied;
  const b = await req.json();
  const job_type = String(b.job_type || "");
  const mode = String(b.mode || "");
  if (!JOB_TYPES.includes(job_type)) return NextResponse.json({ ok: false, error: "Invalid job type." }, { status: 400 });
  if (!MODES.includes(mode)) return NextResponse.json({ ok: false, error: "Invalid schedule mode." }, { status: 400 });

  // idle_stop is presence-driven: its mode carries how long "nobody online" must last
  // before the world stops, so only the elapsed-time modes make sense. It takes no
  // message and never uses daily/on_join.
  if (job_type === "idle_stop" && !["interval", "minutes"].includes(mode)) {
    return NextResponse.json({ ok: false, error: "Idle auto-stop uses an hours or minutes threshold." }, { status: 400 });
  }

  // How long to wait after the join before sending. Capped at an hour — past that
  // it isn't a reaction to the join any more, and the timer only lives in memory.
  const join_delay_seconds = mode === "on_join"
    ? Math.min(3600, Math.max(0, Math.round(Number(b.join_delay_seconds) || 0)))
    : null;

  const interval_hours = mode === "interval" ? Math.max(1, Number(b.interval_hours) || 0) : null;
  const interval_minutes = mode === "minutes" ? Math.max(1, Number(b.interval_minutes) || 0) : null;
  const time_of_day = mode === "daily" ? (b.time_of_day ?? null) : null;
  if (mode === "interval" && !interval_hours) return NextResponse.json({ ok: false, error: "Interval hours must be at least 1." }, { status: 400 });
  if (mode === "minutes" && !interval_minutes) return NextResponse.json({ ok: false, error: "Interval minutes must be at least 1." }, { status: 400 });
  if (mode === "daily" && !/^\d{1,2}:\d{2}$/.test(String(time_of_day || ""))) return NextResponse.json({ ok: false, error: "A valid time is required for a daily schedule." }, { status: 400 });

  const s = {
    id: crypto.randomUUID(),
    world_id: params.id,
    job_type,
    mode,
    interval_hours,
    interval_minutes,
    time_of_day,
    join_match: mode === "on_join" ? (String(b.join_match ?? "").trim() || null) : null,
    join_delay_seconds,
    enabled: b.enabled === false ? 0 : 1,
    created_at: Date.now(),
  };
  dbm.insertSchedule(s);
  ensureScheduler();
  return NextResponse.json({ ok: true, schedule: s });
}

// Toggle a schedule's one-shot "skip the next run" flag. Only mutates schedules that
// belong to this world, so a stray id can't touch another world's rules.
export async function PATCH(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "schedule", action: "schedule.update", mutating: true });
  if (denied) return denied;
  const b = await req.json();
  const sid = String(b.id ?? new URL(req.url).searchParams.get("sid") ?? "");
  if (!sid) return NextResponse.json({ ok: false, error: "A schedule id is required." }, { status: 400 });
  const owned = dbm.listSchedules(params.id).some((s) => s.id === sid);
  if (!owned) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  if (typeof b.skipNext === "boolean") dbm.setScheduleSkipNext(sid, b.skipNext);
  return NextResponse.json({ ok: true });
}

export async function DELETE(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "schedule", action: "schedule.delete", mutating: true });
  if (denied) return denied;
  const id = new URL(req.url).searchParams.get("sid");
  if (id) dbm.deleteSchedule(id);
  return NextResponse.json({ ok: true });
}
