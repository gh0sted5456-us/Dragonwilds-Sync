"use client";
import { useCallback, useEffect, useState } from "react";
import { api, Icon, toast } from "@/components/ui";
import { JobCard, useJobsPoll } from "@/components/jobsClient";
import RuntimeCleanControls from "@/components/RuntimeCleanControls";

export default function RuntimeLanePanel({ platform, installDir }) {
  const [state, setState] = useState(null), [busy, setBusy] = useState(false), [dragging, setDragging] = useState(null);
  const [error, setError] = useState(""), [revision, setRevision] = useState(0);
  const jobs = useJobsPoll(), job = jobs.find((item) => item.worldId === "runtime-lane:" + platform);
  const load = useCallback(() => {
    let cancelled = false;
    setError("");
    api("/api/runtime-lanes?platform=" + platform).then((result) => { if (!cancelled) setState(result.lane); }).catch((failure) => { if (!cancelled) setError(failure.message); });
    return () => { cancelled = true; };
  }, [platform, installDir, revision]);
  useEffect(load, [load, job?.status]);
  const disabled = busy || job?.status === "running" || !state?.installDir;
  async function install(component, zipPath) {
    if (disabled || !zipPath) return;
    if (!/\.zip$/i.test(zipPath)) return toast("Drop one loader ZIP archive.", "error");
    setBusy(true);
    try {
      const result = await api("/api/runtime-lanes", { method: "POST", body: { platform, component, zipPath } });
      window.dispatchEvent(new Event("rsdw-jobs-ping"));
      toast(result.alreadyRunning ? "This loader update is already running." : "Loader ZIP queued. Follow progress and file logs in Downloads.", "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  async function choose(component) {
    if (!window.desktop?.pickZip) return toast("Open the desktop launcher to select a ZIP.", "error");
    await install(component, await window.desktop.pickZip());
  }
  async function drop(event, component) {
    event.preventDefault(); setDragging(null);
    if (disabled) return;
    const dropped = Array.from(event.dataTransfer.files || []);
    if (dropped.length !== 1) return toast("Drop exactly one loader ZIP on its card.", "error");
    try {
      const zipPath = window.desktop?.getPathForFile?.(dropped[0]);
      if (!zipPath) return toast("Use Choose ZIP in the desktop launcher.", "error");
      await install(component, zipPath);
    } catch (error) { toast(error.message, "error"); }
  }
  return <section className="panel-inset" style={{ padding: "1rem", marginTop: 12, display: "grid", gap: 12 }}>
    {error && <div role="alert" style={{ color: "var(--red)" }}>{error} <button className="btn btn-ghost" onClick={() => setRevision((value) => value + 1)}>Retry</button></div>}
    <div>
      <h3 className="heading" style={{ margin: 0, fontSize: ".95rem" }}>Loader ZIP updates</h3>
      {state?.installDir && <code className="subtle" style={{ fontSize: ".68rem", overflowWrap: "anywhere" }}>{state.installDir}</code>}
      <p className="subtle" style={{ margin: "6px 0", fontSize: ".76rem" }}>Drop the correct platform ZIP on its card. RSDW creates a SHA-256 file manifest, replaces package files, and removes files retired by the previous managed version. Existing <code>mods.txt</code>, <code>runeschema.txt</code>, user mods, and saves are kept.</p>
      <p className="subtle" style={{ margin: 0, fontSize: ".72rem" }}>{platform === "server" ? "The installed version.dll is retained, never updated. Use a Steam UE4SS ZIP to update the server payload; its dwmapi.dll is excluded. A new installation still needs an initial server version.dll. Profiles take changed defaults on their next start, never a forced restart." : "Close Dragonwilds before updating. RuneSchema can require a specific UE4SS build. Updating one loader never silently updates the other."}</p>
    </div>
    <div className="runtime-package-grid">
      {(state?.packages || [{ component: "ue4ss-" + platform }, { component: "runeschema" }]).map((item) => <div key={item.component} className="panel" onDragOver={(event) => { event.preventDefault(); if (!disabled) setDragging(item.component); }} onDragLeave={() => setDragging(null)} onDrop={(event) => drop(event, item.component)} style={{ padding: "1rem", outline: dragging === item.component ? "2px solid var(--accent)" : undefined }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <img src={item.component === "runeschema" ? "/rsdw/platforms/runeschema.png" : "/rsdw/platforms/ue4ss.webp"} alt="" style={{ width: 28, height: 28, objectFit: "contain" }} />
          <strong>{item.component === "runeschema" ? "RuneSchema" : "UE4SS · " + (state?.label || platform)}</strong>
          {item.installed && <span className="chip">MANAGED</span>}
          {item.cleaned && <span className="chip">CLEANED · ADD ZIP</span>}
        </div>
        <p className="subtle" style={{ fontSize: ".72rem", overflowWrap: "anywhere" }}>{item.installed ? item.archive + " · " + item.files + " inventoried files" : "Drop ZIP here, or choose an archive below"}</p>
        <button className="btn btn-ghost" disabled={disabled} onClick={() => choose(item.component)}><Icon name="upload" size={14} /> {item.installed ? "Update from ZIP" : "Choose ZIP"}</button>
        <RuntimeCleanControls endpoint="/api/runtime-lanes" platform={platform} component={item.component} disabled={disabled} />
        {item.manifestPath && <details style={{ marginTop: 8 }}><summary className="subtle" style={{ cursor: "pointer", fontSize: ".7rem" }}>File manifest</summary><code style={{ display: "block", fontSize: ".68rem", overflowWrap: "anywhere", marginTop: 5 }}>{item.manifestPath}</code><code style={{ display: "block", fontSize: ".68rem", overflowWrap: "anywhere" }}>{item.sha256}</code></details>}
      </div>)}
    </div>
    <p className="subtle" style={{ margin: 0, fontSize: ".68rem" }}>Only files in an earlier RSDW manifest are removed. Unknown files are never swept away. ZIP defaults seed missing mod/plug-in/load-order lists but never replace an existing list. Failed/interrupted updates have recovery copies.</p>
    {job && <JobCard job={job} defaultShowLog logHeight={180} />}
  </section>;
}
