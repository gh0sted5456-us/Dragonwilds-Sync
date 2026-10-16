"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { Icon } from "@/components/ui";
import SyncProgressPanel from "@/components/SyncProgressPanel";
import Link from "next/link";

// Shared client helpers for the downloads/updates system: a polling hook used by
// both the sidebar indicator and the Downloads page, plus the job card UI.

const PHASE_LABELS = {
  starting: "Starting", steamcmd: "Updating SteamCMD", prepare: "Preparing",
  download: "Downloading server files", verify: "Verifying files", install: "Installing",
  backup: "Backing up", settings: "Writing settings", finalizing: "Finishing up",
  runtime: "Installing mod loader", mod: "Downloading mod", cleanup: "Cleaning saves",
  copy: "Refreshing Server profile files",
};
export function phaseLabel(phase) { return PHASE_LABELS[phase] || "Working"; }
export function labelFor(job) { return job.worldName || (job.type === "install" ? "New server" : job.type === "redist" ? "Prerequisites" : job.type === "runtime" ? "Mod loader" : job.type === "sync" ? "World mod sync" : job.type === "mod" ? "Mod download" : job.type === "cleanup" ? "Save cleaner" : "Server update"); }

// One external store serves every consumer (sidebar + Downloads), preventing
// duplicate HTTP polling and duplicate React updates. Hidden windows back off
// aggressively while an explicit ping still refreshes immediately.
const EMPTY_JOBS = Object.freeze([]);
let sharedJobs = EMPTY_JOBS;
let sharedSignature = "[]";
let pollTimer = null;
let pollInFlight = null;
const listeners = new Set();

function getJobsSnapshot() { return sharedJobs; }
function getEmptySnapshot() { return EMPTY_JOBS; }
function emitJobs(next) {
  const signature = JSON.stringify(next);
  if (signature === sharedSignature) return;
  sharedSignature = signature;
  sharedJobs = next;
  listeners.forEach((listener) => listener());
}
async function pollJobs() {
  if (pollInFlight) return pollInFlight;
  pollInFlight = fetch("/api/jobs", { cache: "no-store" })
    .then((response) => response.json())
    .then((result) => { if (result.ok) emitJobs(result.jobs || EMPTY_JOBS); })
    .catch(() => {})
    .finally(() => { pollInFlight = null; });
  return pollInFlight;
}
function pollDelay() {
  const active = sharedJobs.some((job) => job.status === "running");
  if (document.visibilityState === "hidden") return active ? 4000 : 60000;
  return active ? 1000 : 10000;
}
function scheduleJobsPoll(immediate = false) {
  clearTimeout(pollTimer);
  if (!listeners.size) return;
  pollTimer = setTimeout(async () => {
    await pollJobs();
    scheduleJobsPoll();
  }, immediate ? 0 : pollDelay());
}
function requestJobsRefresh() {
  void pollJobs().finally(() => scheduleJobsPoll());
}
function subscribeJobs(listener) {
  listeners.add(listener);
  if (listeners.size === 1) {
    window.addEventListener("rsdw-jobs-ping", requestJobsRefresh);
    document.addEventListener("visibilitychange", requestJobsRefresh);
    scheduleJobsPoll(true);
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      clearTimeout(pollTimer);
      pollTimer = null;
      window.removeEventListener("rsdw-jobs-ping", requestJobsRefresh);
      document.removeEventListener("visibilitychange", requestJobsRefresh);
    }
  };
}
function subscribeDisabled() { return () => {}; }

export function useJobsPoll(enabled = true) {
  return useSyncExternalStore(enabled ? subscribeJobs : subscribeDisabled, enabled ? getJobsSnapshot : getEmptySnapshot, getEmptySnapshot);
}

export function ProgressBar({ percent, style }) {
  const indeterminate = percent == null;
  return (
    <div style={{ position: "relative", height: 7, borderRadius: 999, background: "var(--line)", overflow: "hidden", ...style }}
      className={indeterminate ? "bar-indet" : undefined}>
      {!indeterminate && (
        <div style={{ position: "absolute", inset: 0, width: `${percent}%`, background: "var(--accent)", borderRadius: 999, transition: "width 0.3s ease" }} />
      )}
    </div>
  );
}

export function JobCard({ job, onDismiss, defaultShowLog = false, logHeight = 200 }) {
  const { t } = useTranslation();
  const [showLog, setShowLog] = useState(defaultShowLog);
  const logRef = useRef(null);
  useEffect(() => { if (showLog && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [job.lines, showLog]);

  const color = job.status === "error" ? "var(--red)" : job.status === "success" ? "var(--green-bright)" : "var(--accent)";
  const running = job.status === "running";
  const typeLabel = job.type === "sync" ? "World file sync" : job.type === "mod" ? "Mod download" : job.type === "cleanup" ? "Save cleanup" : t(job.type === "install" ? "job.install" : job.type === "redist" ? "job.prereqs" : "job.update");
  const cardLabel = labelFor(job);

  return (
    <div className="panel-inset" style={{ padding: "0.9rem 1rem", borderLeft: `3px solid ${color}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
        <span style={{ color, display: "grid", placeItems: "center", flexShrink: 0 }}>
          <Icon name={job.status === "error" ? "alert" : job.status === "success" ? "check" : "download"} size={20} />
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
            <span style={{ fontWeight: 700, fontSize: "0.92rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{cardLabel}</span>
            <span className="subtle" style={{ fontSize: "0.68rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.04em" }}>{typeLabel}</span>
          </div>
          <div className="subtle" style={{ fontSize: "0.78rem", fontWeight: 600 }}>
            {job.type === "sync" ? job.message : running ? (job.message || t(`job.phase.${job.phase}`, { defaultValue: phaseLabel(job.phase) })) : (job.status === "success" ? t("job.completed") : (job.error || t("job.failed")))}
          </div>
        </div>
        {running && job.percent != null && <span style={{ fontSize: "0.9rem", fontWeight: 800, color }}>{job.percent}%</span>}
        {!running && onDismiss && (
          <button onClick={onDismiss} title={t("common.dismiss")} style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--ink-soft)", padding: 3, display: "grid", placeItems: "center" }}>
            <Icon name="x" size={16} />
          </button>
        )}
      </div>
      {job.type === "sync" ? <SyncProgressPanel job={job} compact /> : running && <ProgressBar percent={job.percent} style={{ marginTop: "0.7rem" }} />}
      <div style={{ marginTop: 8, display: "flex", gap: "0.8rem", alignItems: "center" }}>
        {job.type === "sync" && job.worldId && <Link href={`/profiles/${encodeURIComponent(job.worldId)}/player`} style={{ fontSize: ".75rem" }}>{job.status === "error" ? "Retry in World →" : "Open World →"}</Link>}
        <button onClick={() => setShowLog((s) => !s)} className="subtle" style={{ background: "transparent", border: "none", cursor: "pointer", fontSize: "0.72rem", fontWeight: 700, padding: 0 }}>
          {showLog ? t("job.hideLog") : t("job.showLog")}
        </button>
        {job.startedAt && <span className="subtle" style={{ fontSize: "0.7rem", fontWeight: 600 }}>{new Date(job.startedAt).toLocaleTimeString()}</span>}
      </div>
      {showLog && (
        <div ref={logRef} className="console" style={{ height: logHeight, marginTop: 8 }}>
          {(job.lines || []).length === 0
            ? <div className="ln subtle">{t("job.waiting")}</div>
            : job.lines.map((l, i) => <div key={i} className="ln">{l}</div>)}
        </div>
      )}
    </div>
  );
}

// Aggregate summary for the sidebar indicator.
export function summarize(jobs) {
  const running = jobs.filter((j) => j.status === "running");
  const activeCount = running.length;
  const percent = activeCount === 1 ? running[0].percent : null;
  const anyError = jobs.some((j) => j.status === "error");
  return { activeCount, percent, anyError, running };
}
