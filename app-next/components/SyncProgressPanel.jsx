"use client";
import Link from "next/link";
import { fmtBytes } from "@/components/ui";
const { deliveryInfo, journeyState, safeSyncText } = require("@/lib/sync-progress");

const SOURCE_NAMES = { host: "World host", cloud: "Cloud storage", cache: "Profile cache", fallback: "Host fallback" };
export default function SyncProgressPanel({ stage, job, message, error, skipDownload, transport, share = false, compact = false }) {
  const transfer = job?.sync?.transfer;
  const delivery = deliveryInfo(transfer || transport);
  const journey = journeyState({ stage, job, error, skipDownload, share: share || job?.sync?.share });
  const percent = job?.percent == null ? null : Math.round(Math.max(0, Math.min(100, job.percent)));
  const running = job?.status === "running" && stage !== "ready";
  const sourceCounts = transfer?.sources || {};
  return <section className={`sync-progress ${compact ? "sync-progress-compact" : ""}`} aria-label="Verified file sync">
    <div className="sync-delivery">
      <span className="sync-delivery-icon" aria-hidden>{delivery.mode === "local" ? "↔" : delivery.mode === "hybrid" ? "⇄" : "☁"}</span>
      <div><strong>{delivery.label} delivery</strong><small>{delivery.source} · {delivery.detail}</small></div>
      <span className={`sync-state-chip ${journey.error ? "failed" : journey.complete ? "complete" : ""}`}>{journey.error ? "Needs attention" : journey.complete ? (share || job?.sync?.share ? "Files ready" : "Host approved") : running ? "Syncing" : journey.current === "download" ? "Ready to sync" : journey.current ? "In progress" : "Not checked yet"}</span>
    </div>
    <ol className="sync-steps" aria-label="Sync stages">
      {journey.steps.map((step, index) => <li key={step.id} className={`sync-step ${step.state}`} aria-current={step.state === "active" || step.state === "error" ? "step" : undefined}>
        <span className="sync-step-number" aria-hidden>{step.state === "done" ? "✓" : step.state === "error" ? "!" : index + 1}</span>
        <div><strong>{step.label}</strong>{!compact && <small>{step.skipped && step.state === "done" ? "No transfer needed" : step.detail}</small>}</div>
      </li>)}
    </ol>
    <p className={`sync-message ${journey.error ? "failed" : ""}`} role={journey.error ? "alert" : "status"}>{journey.error || safeSyncText((job && !stage ? job.message : running ? job.message : message) || "Check for changes, or sync to prepare this World's files.")}</p>
    {running && <div className={`sync-overall-bar ${percent == null ? "bar-indet" : ""}`} role="progressbar" aria-label="Overall sync progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined}>{percent != null && <span style={{ width: `${percent}%` }} />}</div>}
    {transfer && <div className="sync-transfer-summary">
      <span><strong>{transfer.filesDone} / {transfer.filesTotal}</strong> files prepared</span>
      <span><strong>{fmtBytes(transfer.bytesDone)} / {fmtBytes(transfer.bytesTotal)}</strong></span>
      {running && percent != null && <span>{percent}% overall</span>}
      {Object.entries(sourceCounts).filter(([, count]) => count > 0).map(([source, count]) => <span key={source}>{SOURCE_NAMES[source]} · {count}</span>)}
      {transfer.fallbackCount > 0 && <span className="sync-fallback-notice">Cloud retry → verified host fallback · {transfer.fallbackCount}</span>}
    </div>}
    {!compact && !!transfer?.activeFiles?.length && <ul className="sync-active-files" aria-label="Active files">
      {transfer.activeFiles.map((file) => <li key={file.id || file.name}><div><strong>{safeSyncText(file.name)}</strong><small>{SOURCE_NAMES[file.source] || "Preparing"} · {file.state === "verifying" ? "Checking SHA-256" : file.state === "retrying" ? "Retrying" : `${fmtBytes(file.bytes)} / ${fmtBytes(file.total)}`}</small></div><span>{file.total ? Math.min(100, Math.round(file.bytes / file.total * 100)) : 0}%</span></li>)}
    </ul>}
    {!compact && <div className="sync-footnote"><span>{share ? "Shared files stay in this World profile. File shares do not grant server login approval." : "Files stay in this World profile. Login details unlock only after host approval."}</span><Link href="/downloads">View in Downloads →</Link></div>}
  </section>;
}
