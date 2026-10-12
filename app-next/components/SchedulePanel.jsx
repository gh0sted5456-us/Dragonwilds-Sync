"use client";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, Icon, fmtTime, toast } from "@/components/ui";

export default function SchedulePanel({ worldId, world, schedules, onChange }) {
  const { t } = useTranslation();
  const [jobType, setJobType] = useState("restart");
  const [mode, setMode] = useState("interval");
  const [intervalHours, setIntervalHours] = useState(6);
  const [intervalMinutes, setIntervalMinutes] = useState(30);
  const [timeOfDay, setTimeOfDay] = useState("04:00");
  const [busy, setBusy] = useState(false);

  const add = async () => {
    setBusy(true);
    try {
      await api(`/api/worlds/${worldId}/schedules`, {
        method: "POST",
        body: {
          job_type: jobType, mode,
          interval_hours: mode === "interval" ? Number(intervalHours) : null,
          interval_minutes: mode === "minutes" ? Number(intervalMinutes) : null,
          time_of_day: mode === "daily" ? timeOfDay : null,
        },
      });
      toast(t("schedule.added"), "success");
      onChange();
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };

  const remove = async (sid) => {
    try {
      await api(`/api/worlds/${worldId}/schedules?sid=${sid}`, { method: "DELETE" });
      onChange();
    } catch (e) { toast(e.message, "error"); }
  };

  // Arm/disarm "skip the next run" for one schedule. The schedule stays on; only its
  // next occurrence is cancelled.
  const setSkipNext = async (sid, on) => {
    try {
      await api(`/api/worlds/${worldId}/schedules`, { method: "PATCH", body: { id: sid, skipNext: on } });
      onChange();
    } catch (e) { toast(e.message, "error"); }
  };

  const describeWhen = (s) => {
    if (s.mode === "minutes") return t("schedule.everyMinutes", { minutes: s.interval_minutes });
    if (s.mode === "daily") return t("schedule.dailyAt", { time: s.time_of_day });
    return t("schedule.everyHours", { hours: s.interval_hours });
  };
  const describe = (s) => `${t(`schedule.jobType.${s.job_type}`, { defaultValue: s.job_type })} · ${describeWhen(s)}`;

  return (
    <div>
      <div className="panel-inset" style={{ padding: "0.9rem", marginBottom: "1rem", display: "grid", gap: "0.6rem" }}>
        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "flex-end" }}>
          <div>
            <label className="label">{t("schedule.job")}</label>
            <select className="input" value={jobType} onChange={(e) => setJobType(e.target.value)}>
              <option value="restart">{t("schedule.jobType.restart")}</option>
              <option value="stop">{t("schedule.jobType.stop")}</option>
              <option value="backup">{t("schedule.jobType.backup")}</option>
              <option value="update">{t("schedule.jobType.update")}</option>
            </select>
          </div>
          <div>
            <label className="label">{t("schedule.when")}</label>
            <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="interval">{t("schedule.everyNHours")}</option>
              <option value="minutes">{t("schedule.everyNMinutes")}</option>
              <option value="daily">{t("schedule.dailyAtTime")}</option>
            </select>
          </div>
          {mode === "interval" && (
            <div>
              <label className="label">{t("schedule.hours")}</label>
              <input className="input" type="number" min="1" value={intervalHours} onChange={(e) => setIntervalHours(e.target.value)} style={{ width: 90 }} />
            </div>
          )}
          {mode === "minutes" && (
            <div>
              <label className="label">{t("schedule.minutes")}</label>
              <input className="input" type="number" min="1" value={intervalMinutes} onChange={(e) => setIntervalMinutes(e.target.value)} style={{ width: 90 }} />
            </div>
          )}
          {mode === "daily" && (
            <div>
              <label className="label">{t("schedule.time")}</label>
              <input className="input" type="time" value={timeOfDay} onChange={(e) => setTimeOfDay(e.target.value)} style={{ width: 120 }} />
            </div>
          )}
          <button className="btn btn-primary" onClick={add} disabled={busy}><Icon name="plus" /> {t("schedule.add")}</button>
        </div>
      </div>

      {schedules.length === 0 ? (
        <p className="subtle" style={{ fontWeight: 700 }}>{t("schedule.empty")}</p>
      ) : (
        <div style={{ display: "grid", gap: "0.5rem" }}>
          {schedules.map((s) => (
            <div key={s.id} className="panel-inset" style={{ padding: "0.6rem 0.8rem", display: "flex", alignItems: "center", gap: "0.8rem" }}>
              <Icon name="clock" size={16} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 800, fontSize: "0.84rem" }}>{describe(s)}</div>
                <div className="subtle" style={{ fontSize: "0.72rem", fontWeight: 700 }}>
                  {t("schedule.lastRun", { time: s.last_run ? fmtTime(s.last_run) : t("schedule.never") })}
                  {s.skip_next ? <span style={{ color: "var(--yellow)" }}> · {t("schedule.willSkipNext")}</span> : null}
                </div>
              </div>
              <button
                className={`btn ${s.skip_next ? "btn-primary" : "btn-ghost"}`}
                style={{ padding: "0.3rem 0.6rem", fontSize: "0.72rem" }}
                title={t("schedule.skipNextTip")}
                onClick={() => setSkipNext(s.id, !s.skip_next)}
              >
                {s.skip_next ? t("schedule.undoSkip") : t("schedule.skipNext")}
              </button>
              <button className="btn btn-danger" style={{ padding: "0.3rem 0.6rem" }} onClick={() => remove(s.id)}><Icon name="trash" size={14} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
