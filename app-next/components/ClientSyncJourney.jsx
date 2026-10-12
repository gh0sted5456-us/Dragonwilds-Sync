"use client";
import Link from "next/link";
import { ProgressBar } from "@/components/jobsClient";

const STEPS = [
  { id: "auth", label: "Authenticate", detail: "Request the World manifest" },
  { id: "compare", label: "Compare", detail: "Check managed files" },
  { id: "download", label: "Download", detail: "Transfer & install mods" },
  { id: "verify", label: "Verify", detail: "Check SHA-256 & profile" },
  { id: "ack", label: "Server ACK", detail: "Host approves your manifest" },
  { id: "ready", label: "Ready", detail: "Review login & launch" },
];

export default function ClientSyncJourney({ stage, job, message, error, skipDownload }) {
  const jobStage = job?.status === "running" ?
    ({ prepare: "compare", download: "download", verify: "verify", install: "verify", finalizing: "verify" }[job.phase] || null) : null;
  const current = ["auth", "compare", "download", "verify"].includes(stage) && jobStage ? jobStage : stage;
  const currentIndex = STEPS.findIndex((step) => step.id === current);

  return <div aria-live="polite">
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(125px, 1fr))", gap: 7 }}>
      {STEPS.map((step, index) => {
        const done = current === "ready" || (currentIndex >= 0 && index < currentIndex);
        const active = index === currentIndex && current !== "ready";
        const skipped = step.id === "download" && skipDownload && done;
        return <div key={step.id} className="panel-inset" style={{ padding: ".65rem", borderColor: active ? "var(--accent)" : done ? "var(--green-bright)" : "var(--line)", opacity: done || active ? 1 : .65 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ color: done ? "var(--green-bright)" : active ? "var(--accent)" : "var(--ink-muted)", fontWeight: 850 }}>{done || current === "ready" && step.id === "ready" ? "✓" : index + 1}</span><strong style={{ fontSize: ".75rem" }}>{step.label}</strong></div>
          <div className="subtle" style={{ fontSize: ".67rem", marginTop: 4 }}>{skipped ? "No download needed" : step.detail}</div>
        </div>;
      })}
    </div>
    <div className="subtle" style={{ fontSize: ".75rem", marginTop: 10, color: error ? "var(--red-hover)" : undefined }}>{error || job?.message || message || "Connect to begin the verified World entry sequence."}</div>
    {job?.status === "running" && <div style={{ marginTop: 9 }}><ProgressBar percent={job.percent} /><div className="subtle" style={{ fontSize: ".67rem", marginTop: 4 }}>{job.percent == null ? "Sync in progress" : `${job.percent}%`} · <Link href="/downloads">Open Downloads for file details</Link></div></div>}
  </div>;
}
