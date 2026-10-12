"use client";

import { useCallback, useEffect, useState } from "react";
import ApplicationToolsBack from "@/components/ApplicationToolsBack";
import { api, fmtBytes, fmtTime, Icon, toast } from "@/components/ui";
import { PageHeader, SegmentedMenu } from "@/components/PageChrome";

export default function SaveCleanerPage() {
  const [kind, setKind] = useState("player");
  return <div>
    <ApplicationToolsBack />
    <PageHeader eyebrow="APPLICATION TOOLS" title="Save Cleaner" description="Inspect against RSDW's current Dragonwilds registry, preview every eligible record, and keep a recoverable backup before the launcher changes anything." icon="shield" />
    <SegmentedMenu value={kind} onChange={setKind} ariaLabel="Save cleaner type" items={[
      { id: "player", icon: "users", label: "Player Save Cleaner", detail: "Registry-aware character cleanup" },
      { id: "world", icon: "globe", label: "World Cleaner", detail: "Safe SPUD cache rebuild" },
    ]} />
    <Cleaner key={kind} kind={kind} />
  </div>;
}

function Cleaner({ kind }) {
  const [data, setData] = useState({ candidates: [], catalog: null });
  const [sourcePath, setSourcePath] = useState("");
  const [job, setJob] = useState(null);
  const [preview, setPreview] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const result = await api(`/api/save-cleaner?kind=${kind}`);
      setData(result);
      setSourcePath((current) => current || result.candidates?.[0]?.path || "");
    } catch (error) { toast(error.message, "error"); }
  }, [kind]);
  useEffect(() => { load(); }, [load]);

  async function waitForJob(jobId) {
    setBusy(true);
    try {
      for (;;) {
        const result = await api(`/api/save-cleaner?jobId=${encodeURIComponent(jobId)}`);
        setJob(result.job);
        if (result.job.status !== "running") {
          if (result.job.status === "error") throw new Error(result.job.error || "Save cleaner failed");
          return result.job.result || null;
        }
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
    } finally { setBusy(false); }
  }

  async function browse() {
    const value = kind === "world" ? await window.desktop?.pickWorldSave?.() : await window.desktop?.pickDirectory?.();
    if (value) { setSourcePath(value); setPreview(null); setConfirmed(false); }
  }

  async function inspect() {
    if (!sourcePath.trim()) return toast(`Choose a ${kind} save first.`, "error");
    setPreview(null); setConfirmed(false); setJob(null);
    try {
      const started = await api("/api/save-cleaner", { method: "POST", body: { action: "preview", kind, path: sourcePath.trim() } });
      const result = await waitForJob(started.jobId);
      setPreview(result);
      toast(result.summary, result.removed?.length || result.cacheFiles?.length ? "success" : "info");
      await load();
    } catch (error) { toast(error.message, "error"); }
  }

  async function clean() {
    if (!confirmed || !preview?.previewId) return;
    try {
      const started = await api("/api/save-cleaner", { method: "POST", body: { action: "clean", previewId: preview.previewId } });
      const result = await waitForJob(started.jobId);
      setConfirmed(false);
      setPreview((value) => ({ ...value, applied: result }));
      toast(result.changed ? (kind === "player" ? `Verified cleaned copy exported to ${result.backup}` : `Cleanup complete. Recovery backup: ${result.backup}`) : "Nothing needed cleaning.", "success");
    } catch (error) { toast(error.message, "error"); }
  }

  const actionable = kind === "player" ? Number(preview?.removed?.length || 0) : Number(preview?.cacheFiles?.length || 0);
  return <div style={{ display: "grid", gap: 14, maxWidth: 980 }}>
    <div className="panel" style={{ padding: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 14, flexWrap: "wrap" }}>
        <div>
          <h2 className="heading" style={{ fontSize: "1.08rem", margin: 0 }}>{kind === "player" ? "Player character registry scrub" : "World SPUD cache cleaner"}</h2>
          <p className="subtle" style={{ maxWidth: 720, lineHeight: 1.55, marginBottom: 0 }}>
            {kind === "player"
              ? "Checks inventory, loadout, discoveries, recipes, and quests. A record is eligible only when it is absent from a freshly downloaded, complete RSDW game registry. Malformed or unsupported fields remain untouched, and cleanup exports a verified copy instead of editing the original."
              : "Archives the disposable SpudCache beside the selected world and lets Dragonwilds rebuild it from the .sav. Binary world records are not guessed at: RuneSchema explicitly requires a dedicated SPUD adapter for placed-world content."}
          </p>
        </div>
        <span className="chip" style={{ background: kind === "player" ? "var(--green)" : "var(--yellow)", color: "#17130b" }}>{kind === "player" ? "REGISTRY GUARDED" : "CACHE ONLY"}</span>
      </div>

      <div style={{ display: "grid", gap: 8, marginTop: 16 }}>
        <label className="label">{kind === "player" ? "SaveCharacter folder" : "World .sav file"}</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input className="input" style={{ flex: 1 }} value={sourcePath} onChange={(event) => { setSourcePath(event.target.value); setPreview(null); }} placeholder={kind === "player" ? "Choose a SaveCharacter folder" : "Choose a SaveGames .sav file"} />
          <button className="btn btn-ghost" onClick={browse}><Icon name="folder" size={15} /> Browse</button>
          <button className="btn btn-primary" disabled={busy || !sourcePath.trim()} onClick={inspect}><Icon name="search" size={15} /> {kind === "player" ? "Compare & Preview" : "Inspect Cache"}</button>
        </div>
        {!!data.candidates?.length && <select className="input" value={data.candidates.some((row) => row.path === sourcePath) ? sourcePath : ""} onChange={(event) => { if (event.target.value) setSourcePath(event.target.value); }}>
          <option value="">Detected saves on this computer…</option>
          {data.candidates.map((row) => <option key={row.path} value={row.path}>{row.name} · {row.service} · {fmtBytes(row.size)}</option>)}
        </select>}
      </div>
    </div>

    {(busy || job) && <Progress job={job} />}

    {kind === "player" && (preview?.catalog || data.catalog) && <CatalogCard catalog={preview?.catalog || data.catalog} />}

    {preview && <div className="panel" style={{ padding: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div><div className="eyebrow">PREVIEW</div><h2 className="heading" style={{ fontSize: "1.08rem", margin: "4px 0" }}>{preview.summary}</h2></div>
        {preview.applied && <span className="chip" style={{ background: "var(--green)", color: "#08140c" }}>CLEANED &amp; VERIFIED</span>}
      </div>

      {kind === "player" ? <>
        <div className="subtle" style={{ fontSize: ".76rem", marginTop: 5 }}>{preview.filesScanned} gameplay save(s) compared · {preview.filesSkipped} unsupported/profile-only file(s) preserved</div>
        {!!preview.removed?.length && <RemovalList rows={preview.removed} />}
        {!!preview.skipped?.length && <details style={{ marginTop: 12 }}><summary className="subtle">Preserved without changes ({preview.skipped.length})</summary><div style={{ display: "grid", gap: 5, marginTop: 8 }}>{preview.skipped.map((row) => <div key={row.path} className="subtle" style={{ fontSize: ".7rem" }}>{row.path} · {row.reason}</div>)}</div></details>}
      </> : <>
        <div className="subtle" style={{ fontSize: ".76rem", marginTop: 5 }}>{fmtBytes(preview.bytes || 0)} in rebuildable streaming cache · original world .sav remains untouched</div>
        {!!preview.cacheFiles?.length && <div style={{ display: "grid", gap: 5, marginTop: 12 }}>{preview.cacheFiles.slice(0, 100).map((row) => <div className="panel-inset" key={row.path} style={{ padding: "7px 9px", display: "flex", justifyContent: "space-between", gap: 10 }}><span style={{ fontSize: ".74rem" }}>{row.name}</span><span className="subtle" style={{ fontSize: ".7rem" }}>{fmtBytes(row.size)}</span></div>)}</div>}
      </>}

      {!preview.applied && actionable > 0 && <div className="panel-inset" style={{ marginTop: 16, padding: 12 }}>
        <label style={{ display: "flex", gap: 9, alignItems: "flex-start", fontSize: ".78rem", fontWeight: 700 }}>
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
          <span>{kind === "player" ? "I reviewed the preview and understand the cleaned export omits the listed records. My original character save will remain untouched." : "I closed Dragonwilds and want to archive this rebuildable cache. The world .sav will not be modified."}</span>
        </label>
        <button className="btn btn-primary" style={{ marginTop: 10 }} disabled={!confirmed || busy} onClick={clean}><Icon name="shield" size={15} /> {kind === "player" ? "Export Verified Cleaned Copy" : "Archive & Rebuild World Cache"}</button>
      </div>}
      {preview.applied?.backup && <div className="panel-inset" style={{ marginTop: 12, padding: 10, overflowWrap: "anywhere", fontSize: ".72rem" }}>{kind === "player" ? "Cleaned export (original untouched)" : "Recovery backup"}: {preview.applied.backup} <button className="btn btn-ghost" style={{ marginLeft: 8 }} onClick={() => window.desktop?.openPath?.(preview.applied.backup)}>Open</button></div>}
    </div>}
  </div>;
}

function Progress({ job }) {
  const percent = Number.isFinite(Number(job?.percent)) ? Number(job.percent) : null;
  return <div className="panel" style={{ padding: 15 }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginBottom: 8 }}><strong style={{ fontSize: ".82rem" }}>{job?.message || "Starting save cleaner…"}</strong><span className="subtle" style={{ fontSize: ".72rem" }}>{percent == null ? "Working…" : `${Math.round(percent)}%`}</span></div>
    <div style={{ height: 8, borderRadius: 999, overflow: "hidden", background: "var(--card-2)" }}><div style={{ width: `${percent == null ? 35 : percent}%`, height: "100%", borderRadius: 999, background: "var(--accent)", transition: "width .2s ease" }} /></div>
  </div>;
}

function CatalogCard({ catalog }) {
  return <div className="panel-inset" style={{ padding: 12, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
    <div><strong style={{ fontSize: ".8rem" }}>RSDW native registry · game {catalog.version || "current"}</strong><div className="subtle" style={{ fontSize: ".69rem", marginTop: 3 }}>{catalog.source} · generated {fmtTime(catalog.generatedAt)}{catalog.stale ? " · cached fallback (refresh failed)" : ""}</div></div>
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><span className="chip">{catalog.counts?.items || 0} ITEMS</span><span className="chip">{catalog.counts?.recipes || 0} RECIPES</span><span className="chip">{catalog.counts?.quests || 0} QUESTS</span></div>
  </div>;
}

function RemovalList({ rows }) {
  return <div style={{ marginTop: 13 }}><div className="eyebrow">ELIGIBLE REMOVALS</div><div style={{ display: "grid", gap: 5, marginTop: 7, maxHeight: 330, overflow: "auto" }}>{rows.map((row, index) => <div className="panel-inset" key={`${row.file}-${row.kind}-${row.id}-${index}`} style={{ padding: "7px 9px", display: "grid", gridTemplateColumns: "minmax(110px,.6fr) minmax(180px,1.5fr) minmax(100px,.7fr)", gap: 8, fontSize: ".72rem" }}><strong>{row.kind}</strong><span style={{ overflowWrap: "anywhere" }}>{row.id}</span><span className="subtle">{row.file}</span></div>)}</div></div>;
}
