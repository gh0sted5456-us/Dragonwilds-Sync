"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import ApplicationToolsBack from "@/components/ApplicationToolsBack";
import { api, fmtBytes, fmtTime, Icon, toast } from "@/components/ui";
import { PageHeader, SegmentedMenu } from "@/components/PageChrome";
import { ProgressBar, useJobsPoll } from "@/components/jobsClient";

export default function SaveCleanerPage() {
  const [kind, setKind] = useState("player");
  const [visited, setVisited] = useState(["player"]);
  function selectTool(value) {
    setKind(value);
    setVisited((current) => current.includes(value) ? current : [...current, value]);
  }
  return <div>
    <ApplicationToolsBack />
    <PageHeader eyebrow="APPLICATION TOOLS" title="Save Tools" description="Inspect saves, review changes, and keep your originals safe." icon="shield" />
    <SegmentedMenu value={kind} onChange={selectTool} ariaLabel="Save tool" items={[
      { id: "player", icon: "users", label: "Player Save Cleaner", detail: "Review & export a cleaned copy" },
      { id: "world", icon: "globe", label: "World Inspector", detail: "Inspect saves & clear rebuildable cache" },
      { id: "converter", icon: "refresh", label: "Save Converter", detail: "Steam → PC Game Pass" },
    ]} />
    {visited.map((tool) => <div key={tool} hidden={kind !== tool}>
      {tool === "converter" ? <WorldConverter /> : <Cleaner kind={tool} />}
    </div>)}
  </div>;
}

function WorldConverter() {
  const [busy, setBusy] = useState(false);
  const activeRequest = useRef(false);
  const alive = useRef(false);
  const jobs = useJobsPoll();
  const converterJob = jobs.find((job) => job.worldName === "RSDW Save Converter");
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => window.dispatchEvent(new Event("rsdw-jobs-ping")), 1000);
    return () => clearInterval(timer);
  }, [busy]);
  async function launch() {
    if (activeRequest.current) return;
    if (!window.desktop?.openPath) {
      window.open("https://github.com/RSDWArchive/RSDWSaveConverter/releases/latest", "_blank", "noopener,noreferrer");
      return;
    }
    activeRequest.current = true;
    setBusy(true);
    try {
      const result = await api("/api/profile-saves", { method: "POST", body: { action: "converter" } });
      if (!alive.current) return;
      const error = await window.desktop.openPath(result.converter.path);
      if (error) throw new Error(error);
      toast(`Opened verified RSDW Save Converter ${result.converter.version}.`, "success");
    } catch (error) { if (alive.current) toast(error.message, "error"); }
    finally { activeRequest.current = false; if (alive.current) setBusy(false); }
  }
  return <div className="panel" style={{ padding: 18, maxWidth: 980 }}>
    <h2 className="heading" style={{ fontSize: "1.08rem", marginTop: 0 }}>RSDW Save Converter</h2>
    <p className="subtle" style={{ lineHeight: 1.55 }}>Import Steam worlds and characters into an existing PC Game Pass save slot. Close Dragonwilds first. The converter runs locally and backs up the destination before making changes.</p>
    <div className="panel-inset" style={{ padding: 12, fontSize: ".76rem", marginBottom: 12 }}>
      Steam → PC Game Pass only. Create the destination slot in Game Pass before importing. Game Pass → Steam conversion is not currently supported.
    </div>
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <button className="btn btn-primary" disabled={busy || converterJob?.status === "running"} onClick={launch}><Icon name="refresh" size={15} /> {busy || converterJob?.status === "running" ? "Preparing converter…" : "Open Save Converter"}</button>
      <a className="btn btn-ghost" href="https://github.com/RSDWArchive/RSDWSaveConverter" target="_blank" rel="noopener noreferrer">About the converter</a>
    </div>
    <p className="subtle" style={{ fontSize: ".74rem" }}>RSDW checks the downloaded tool before opening it. Download progress is also available in Downloads.</p>
    {(busy || converterJob) && <Progress job={converterJob} startingLabel="Checking converter…" />}
  </div>;
}

function Cleaner({ kind }) {
  const [data, setData] = useState({ candidates: [], catalog: null });
  const [sourcePath, setSourcePath] = useState("");
  const [job, setJob] = useState(null);
  const [preview, setPreview] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [starting, setStarting] = useState(false);
  const [operation, setOperation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [desktopAvailable, setDesktopAvailable] = useState(false);
  const activeRequest = useRef(false);
  const alive = useRef(false);
  const jobs = useJobsPoll();
  const activeJob = operation ? jobs.find((item) => item.id === operation.id) : null;
  const busy = starting || !!operation;

  const load = useCallback(async (signal) => {
    setLoading(true);
    try {
      const result = await api(`/api/save-cleaner?kind=${kind}`, { signal });
      if (!alive.current || signal?.aborted) return;
      setData(result);
      setSourcePath((current) => current || result.candidates?.[0]?.path || "");
    } catch (error) { if (alive.current && !signal?.aborted) toast(error.message, "error"); }
    finally { if (alive.current && !signal?.aborted) setLoading(false); }
  }, [kind]);
  useEffect(() => {
    const controller = new AbortController();
    alive.current = true;
    setDesktopAvailable(!!(kind === "world" ? window.desktop?.pickWorldSave : window.desktop?.pickDirectory));
    load(controller.signal);
    return () => { alive.current = false; controller.abort(); };
  }, [kind, load]);

  // Reuse Downloads' single job poller. Leaving this page never leaves an
  // independent polling loop behind; the actual job continues in Downloads.
  useEffect(() => {
    if (!activeJob || activeJob.status === "running") return;
    setJob(activeJob);
    setOperation(null);
    setConfirmed(false);
    if (activeJob.status === "error" || !activeJob.result) {
      setPreview(null);
      toast(activeJob.error || "Save operation failed. Inspect the save again before retrying.", "error");
      return;
    }
    const result = activeJob.result;
    if (operation.action === "preview") {
      setPreview(result);
      toast(result.summary, "info");
    } else {
      setPreview((value) => ({ ...value, applied: result }));
      toast(result.changed ? (kind === "player" ? "Cleaned copies exported. Original saves are unchanged." : "Reviewed cache files archived. The game will rebuild them on its next launch.") : "No changes needed.", "success");
    }
  }, [activeJob, operation, kind]);

  function selectSource(value) {
    setSourcePath(value);
    setPreview(null);
    setConfirmed(false);
    setJob(null);
  }

  async function browse() {
    try {
      const value = kind === "world" ? await window.desktop?.pickWorldSave?.() : await window.desktop?.pickDirectory?.();
      if (value && alive.current) selectSource(value);
    } catch (error) { if (alive.current) toast(error.message, "error"); }
  }

  async function startOperation(action) {
    if (activeRequest.current || busy) return;
    if (action === "preview" && !sourcePath.trim()) return toast(`Choose a ${kind} save first.`, "error");
    if (action === "clean" && (!confirmed || !preview?.previewId)) return;
    activeRequest.current = true;
    setStarting(true);
    setConfirmed(false);
    setJob(null);
    if (action === "preview") setPreview(null);
    try {
      const body = action === "preview" ? { action, kind, path: sourcePath.trim() } : { action, previewId: preview.previewId };
      const started = await api("/api/save-cleaner", { method: "POST", body });
      window.dispatchEvent(new Event("rsdw-jobs-ping"));
      if (alive.current) setOperation({ id: started.jobId, action });
    } catch (error) { if (alive.current) toast(error.message, "error"); }
    finally { activeRequest.current = false; if (alive.current) setStarting(false); }
  }

  async function openBackup() {
    try {
      const error = await window.desktop.openPath(preview.applied.backup);
      if (error) throw new Error(error);
    } catch (error) { toast(error.message, "error"); }
  }

  const actionable = kind === "player" ? Number(preview?.removed?.length || 0) : Number(preview?.cacheFiles?.length || 0);
  return <div style={{ display: "grid", gap: 14, maxWidth: 980 }}>
    <div className="panel" style={{ padding: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 14, flexWrap: "wrap" }}>
        <div>
          <h2 className="heading" style={{ fontSize: "1.08rem", margin: 0 }}>{kind === "player" ? "Player save cleanup" : "World inspection & cache maintenance"}</h2>
          <p className="subtle" style={{ maxWidth: 720, lineHeight: 1.55, marginBottom: 0 }}>
            {kind === "player"
              ? "Compare characters with the latest RSDW game registry, review unrecognized items, recipes and quests, then export cleaned copies. Original saves and unsupported fields stay untouched. Close Dragonwilds before exporting."
              : "Check a world save without changing it, then optionally archive its rebuildable cache. Only the listed cache files are cleared; the game recreates them on its next launch. Buildings, nodes and other world content remain unchanged."}
          </p>
        </div>
        <span className="chip" style={{ background: "var(--card-2)" }}>{kind === "player" ? "EXPORT ONLY" : "WORLD SAVE UNCHANGED"}</span>
      </div>

      <div style={{ display: "grid", gap: 8, marginTop: 16 }}>
        <label className="label" htmlFor={`${kind}-save-path`}>{kind === "player" ? "Character JSON file or SaveCharacter folder" : "World .sav file"}</label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input id={`${kind}-save-path`} className="input" style={{ flex: "1 1 280px", minWidth: 0 }} disabled={busy} value={sourcePath} onChange={(event) => selectSource(event.target.value)} placeholder={kind === "player" ? "Choose a character save or folder" : "Choose a world .sav file"} />
          <button className="btn btn-ghost" disabled={busy || !desktopAvailable} title={desktopAvailable ? "Choose a save on this computer" : "Browse is available in the desktop app; you can enter a path above"} onClick={browse}><Icon name="folder" size={15} /> Browse</button>
          <button className="btn btn-primary" disabled={busy || !sourcePath.trim()} onClick={() => startOperation("preview")}><Icon name="search" size={15} /> {kind === "player" ? "Compare & Preview" : "Inspect World & Cache"}</button>
        </div>
        {!!data.candidates?.length && <select className="input" aria-label="Detected saves" disabled={busy} value={data.candidates.some((row) => row.path === sourcePath) ? sourcePath : ""} onChange={(event) => { if (event.target.value) selectSource(event.target.value); }}>
          <option value="">Detected saves on this computer…</option>
          {data.candidates.map((row) => <option key={row.path} value={row.path}>{row.name} · {row.service} · {fmtBytes(row.size)}</option>)}
        </select>}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span className="subtle" style={{ fontSize: ".72rem" }}>{loading ? "Finding saves on this computer…" : `${data.candidates?.length || 0} detected save(s)`}</span>
          <button className="btn btn-ghost" disabled={busy || loading} onClick={() => load()}><Icon name="refresh" size={14} /> Refresh detected saves</button>
        </div>
      </div>
    </div>

    {(busy || job) && <Progress job={activeJob || job} />}

    {kind === "player" && (preview?.catalog || data.catalog) && <CatalogCard catalog={preview?.catalog || data.catalog} />}

    {preview && <div className="panel" style={{ padding: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div><div className="eyebrow">{preview.applied ? "RESULT" : "PREVIEW"}</div><h2 className="heading" style={{ fontSize: "1.08rem", margin: "4px 0" }}>{preview.applied ? (kind === "player" ? `${preview.applied.changed} cleaned copy/copies exported` : `${preview.applied.changed} reviewed cache file(s) archived`) : preview.summary}</h2></div>
        {preview.applied && <span className="chip" style={{ background: "var(--green)", color: "#08140c" }}>{kind === "player" ? "ORIGINALS UNCHANGED" : "CACHE ARCHIVED"}</span>}
      </div>
      <div className="subtle" style={{ fontSize: ".72rem", marginTop: 6, overflowWrap: "anywhere" }}>{preview.sourcePath}</div>

      {kind === "player" ? <>
        <div className="subtle" style={{ fontSize: ".76rem", marginTop: 5 }}>{preview.filesScanned} gameplay save(s) compared · {preview.filesSkipped} unsupported/profile-only file(s) preserved</div>
        {!!preview.removed?.length && <RemovalList rows={preview.removed} />}
        {!!preview.skipped?.length && <details style={{ marginTop: 12 }}><summary className="subtle">Preserved without changes ({preview.skipped.length})</summary><div style={{ display: "grid", gap: 5, marginTop: 8, maxHeight: 250, overflow: "auto" }}>{preview.skipped.map((row) => <div key={row.path} className="subtle" style={{ fontSize: ".7rem", overflowWrap: "anywhere" }}>{row.path} · {row.reason}</div>)}</div></details>}
      </> : <>
        <div className="subtle" style={{ fontSize: ".76rem", marginTop: 5 }}>{fmtBytes(preview.bytes || 0)} in rebuildable streaming cache · original world .sav remains untouched</div>
        <div className="subtle" style={{ fontSize: ".72rem", marginTop: 5, overflowWrap: "anywhere" }}>Cache folder: {preview.cachePath}. Worlds in the same save location may share this cache.</div>
        {preview.world && <div className="panel-inset" style={{ marginTop: 12, padding: 12, fontSize: ".76rem" }}>
          <strong>World save inspection</strong>
          <div className="subtle" style={{ marginTop: 5 }}>Detected mode: {preview.world.worldType || "Unknown"} · {fmtBytes(preview.world.size)} · {preview.world.formatStatus === "verified" ? "Basic file checks passed" : "Basic file checks need review"}</div>
          {preview.world.formatWarning && <div style={{ color: "var(--yellow)", marginTop: 5 }}>{preview.world.formatWarning}</div>}
          <div className="subtle" style={{ marginTop: 6 }}>These checks do not guarantee the game can load the world. The save remains untouched.</div>
          <details style={{ marginTop: 8 }}><summary className="subtle">Technical details</summary><div className="subtle" style={{ marginTop: 4 }}>SAVE envelope: {preview.world.formatStatus} · Raw mode: {preview.world.rawMode ?? "unknown"}<br />Top-level chunks: {preview.world.chunks?.map((chunk) => chunk.tag).join(" · ") || "Not verified"}</div></details>
        </div>}
        {!!preview.cacheFiles?.length && <div style={{ marginTop: 12 }}><div className="eyebrow">REVIEWED CACHE FILES</div><div style={{ display: "grid", gap: 5, marginTop: 7, maxHeight: 330, overflow: "auto" }}>{preview.cacheFiles.slice(0, 100).map((row) => <div className="panel-inset" key={row.path} style={{ padding: "7px 9px", display: "flex", justifyContent: "space-between", gap: 10 }}><span style={{ fontSize: ".74rem", overflowWrap: "anywhere", minWidth: 0 }}>{row.name}</span><span className="subtle" style={{ fontSize: ".7rem", flexShrink: 0 }}>{fmtBytes(row.size)}</span></div>)}</div>{preview.cacheFiles.length > 100 && <details style={{ marginTop: 8 }}><summary className="subtle">Show remaining {preview.cacheFiles.length - 100} file names</summary><div className="subtle" style={{ fontSize: ".72rem", maxHeight: 250, overflow: "auto", overflowWrap: "anywhere" }}>{preview.cacheFiles.slice(100).map((row) => <div key={row.path}>{row.name} · {fmtBytes(row.size)}</div>)}</div></details>}</div>}
      </>}

      {!preview.applied && actionable > 0 && <div className="panel-inset" style={{ marginTop: 16, padding: 12 }}>
        <label style={{ display: "flex", gap: 9, alignItems: "flex-start", fontSize: ".78rem", fontWeight: 700 }}>
          <input type="checkbox" disabled={busy} checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
          <span>{kind === "player" ? "I closed Dragonwilds and reviewed the listed records. Export cleaned copies without changing my original saves." : "I closed Dragonwilds and reviewed these cache files. Archive and clear only these files; leave the world save untouched."}</span>
        </label>
        <button className="btn btn-primary" style={{ marginTop: 10 }} disabled={!confirmed || busy} onClick={() => startOperation("clean")}><Icon name="shield" size={15} /> {kind === "player" ? "Export Verified Cleaned Copy" : "Archive & Clear Reviewed Cache"}</button>
      </div>}
      {preview.applied?.backup && <div className="panel-inset" style={{ marginTop: 12, padding: 10, overflowWrap: "anywhere", fontSize: ".72rem" }}>{kind === "player" ? "Cleaned export (original untouched)" : "Recovery backup"}: {preview.applied.backup} <button className="btn btn-ghost" style={{ marginLeft: 8 }} disabled={!desktopAvailable} onClick={openBackup}>Open folder</button></div>}
    </div>}

    {kind === "world" && <div className="panel-inset" style={{ padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}><strong style={{ fontSize: ".85rem" }}>World Cleaner</strong><span className="chip">PLANNED</span></div>
      <p className="subtle" style={{ fontSize: ".78rem", lineHeight: 1.55, marginBottom: 0 }}>Removing non-vanilla buildings, actors and nodes from a cleaned world copy is a future feature. It is not available in this release.</p>
    </div>}
  </div>;
}

function Progress({ job, startingLabel = "Starting save tool…" }) {
  const percent = job?.percent != null && Number.isFinite(Number(job.percent)) ? Math.max(0, Math.min(100, Number(job.percent))) : null;
  const status = job?.status || "running";
  return <div className="panel" style={{ padding: 15 }}>
    <div role="status" style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginBottom: 8 }}><strong style={{ fontSize: ".82rem", color: status === "error" ? "var(--red)" : undefined }}>{job?.error || job?.message || startingLabel}</strong><span className="subtle" style={{ fontSize: ".72rem" }}>{status === "error" ? "Failed" : status === "success" ? "Complete" : percent == null ? "Working…" : `${Math.round(percent)}%`}</span></div>
    {status === "running" && <div role="progressbar" aria-label="Save tool progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined}><ProgressBar percent={percent} /></div>}
    <Link href="/downloads" className="subtle" style={{ display: "inline-block", marginTop: 9, fontSize: ".72rem" }}>View progress & logs in Downloads</Link>
  </div>;
}

function CatalogCard({ catalog }) {
  return <div className="panel-inset" style={{ padding: 12, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
    <div><strong style={{ fontSize: ".8rem" }}>RSDW native registry · game {catalog.version || "current"}</strong><div className="subtle" style={{ fontSize: ".69rem", marginTop: 3 }}>{catalog.source} · generated {fmtTime(catalog.generatedAt)}{catalog.stale ? " · cached fallback (refresh failed)" : ""}</div></div>
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><span className="chip">{catalog.counts?.items || 0} ITEMS</span><span className="chip">{catalog.counts?.recipes || 0} RECIPES</span><span className="chip">{catalog.counts?.quests || 0} QUESTS</span></div>
  </div>;
}

function RemovalList({ rows }) {
  return <div style={{ marginTop: 13 }}><div className="eyebrow">RECORDS OMITTED FROM THE CLEANED COPY</div><div style={{ display: "grid", gap: 5, marginTop: 7, maxHeight: 330, overflow: "auto" }}>{rows.map((row, index) => <div className="panel-inset" key={`${row.file}-${row.kind}-${row.id}-${index}`} style={{ padding: "7px 9px", display: "flex", flexWrap: "wrap", gap: 8, fontSize: ".72rem" }}><strong style={{ flex: "1 1 110px" }}>{row.kind}</strong><span style={{ flex: "2 1 180px", minWidth: 0, overflowWrap: "anywhere" }}>{row.id}</span><span className="subtle" style={{ flex: "1 1 100px", overflowWrap: "anywhere" }}>{row.file}</span></div>)}</div></div>;
}
