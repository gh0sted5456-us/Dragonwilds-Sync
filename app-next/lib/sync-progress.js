// Shared, URL-free presentation model for the World page and Downloads.
const STEPS = [
  { id: "auth", label: "Authenticate", detail: "Get the host's manifest" },
  { id: "compare", label: "Compare", detail: "Find new or changed files" },
  { id: "download", label: "Transfer", detail: "Download or reuse cache" },
  { id: "verify", label: "Verify", detail: "Check sizes and SHA-256" },
  { id: "install", label: "Activate", detail: "Prepare this profile's files" },
  { id: "ack", label: "Host approval", detail: "Submit the verified manifest" },
  { id: "ready", label: "Ready", detail: "Review credentials and launch" },
];
const PHASES = { starting: "auth", auth: "auth", prepare: "compare", compare: "compare", download: "download", verify: "verify", install: "install", prepared: "ack", ack: "ack", ready: "ready", "files-ready": "ready" };
function stageForPhase(phase) { return PHASES[phase] || null; }
function safeSyncText(value) { return String(value || "").replace(/https?:\/\/[^\s"'<>]+/gi, "[hidden link]"); }
function deliveryInfo(value = {}) {
  const mode = value.storageMode || value.deliveryMode || value.mode || "local";
  const provider = value.storageProvider || value.deliveryProvider || value.provider || "generic";
  const providerName = ({ google: "Google Drive", onedrive: "OneDrive", dropbox: "Dropbox", generic: "HTTPS storage" })[provider] || "Cloud storage";
  return mode === "hybrid" ? { mode, provider, label: "Hybrid", source: providerName, detail: "Cloud first · verified host fallback" }
    : mode === "cloud" ? { mode, provider, label: "Cloud", source: providerName, detail: "Cloud downloads · no direct fallback" }
    : { mode: "local", provider: "local", label: "Direct", source: "World host", detail: "Files delivered by the host" };
}
function journeyState({ stage, job, error, skipDownload = false, share = false } = {}) {
  const sync = job?.sync;
  const current = stage === "ready" && !error ? "ready" : job?.status === "running" || (!stage && job) ? sync?.stage || stageForPhase(job?.phase) || stage : stage;
  const failure = error || (job?.status === "error" ? job.error : null);
  const selected = sync?.failedStage || current;
  const steps = STEPS.filter((step) => !share || step.id !== "ack").map((step) => share && step.id === "ready" ? { ...step, label: "Files ready", detail: "Saved to this World profile" } : step);
  const index = steps.findIndex((step) => step.id === selected);
  const complete = !failure && current === "ready";
  return {
    current, error: failure ? safeSyncText(failure) : null, complete,
    steps: steps.map((step, i) => ({ ...step, state: i === index && failure ? "error" : complete || (index >= 0 && i < index) ? "done" : i === index ? "active" : "pending", skipped: step.id === "download" && (skipDownload || sync?.transfer?.filesTotal === 0) })),
  };
}
module.exports = { STEPS, stageForPhase, safeSyncText, deliveryInfo, journeyState };
