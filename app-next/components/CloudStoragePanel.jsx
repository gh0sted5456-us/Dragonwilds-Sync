"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Icon, fmtBytes, toast } from "@/components/ui";

const PROVIDER_MARKS = {
  google: { mark: "▲", colors: "#4285f4,#34a853,#fbbc04,#ea4335" },
  onedrive: { mark: "☁", colors: "#1686d9,#43a5ee" },
  dropbox: { mark: "◆", colors: "#0061ff,#3984ff" },
  generic: { mark: "↗", colors: "#8c72d9,#b89cff" },
};

export default function CloudStoragePanel({ worldId }) {
  const [storage, setStorage] = useState(null);
  const [providers, setProviders] = useState([]);
  const [hostTypes, setHostTypes] = useState([]);
  const [manifestUrl, setManifestUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [exportJob, setExportJob] = useState(null);
  const [exportPlatform, setExportPlatform] = useState("steam");
  const load = useCallback(() => api(`/api/worlds/${worldId}/storage`).then((result) => { setStorage(result.storage); setProviders(result.providers || []); setHostTypes(result.hostTypes || []); }).catch((error) => toast(error.message, "error")), [worldId]);
  useEffect(() => {
    load();
    api(`/api/worlds/${worldId}/storage?export=status`).then((result) => setExportJob(result.export)).catch(() => {});
  }, [load, worldId]);
  useEffect(() => {
    if (!["copying", "verifying"].includes(exportJob?.phase)) return;
    const timer = setInterval(() => {
      api(`/api/worlds/${worldId}/storage?export=status`).then((result) => setExportJob(result.export)).catch((error) => toast(error.message, "error"));
    }, 1000);
    return () => clearInterval(timer);
  }, [worldId, exportJob?.phase]);

  async function prepareExport() {
    try {
      const result = await api(`/api/worlds/${worldId}/storage`, { method: "POST", body: { prepareExport: true, platform: exportPlatform } });
      setExportJob(result.export);
      toast("Preparing verified files and a cloud manifest template.", "info");
    } catch (error) { toast(error.message, "error"); }
  }

  async function save(refresh = false, changes = {}) {
    setBusy(true);
    try {
      const result = await api(`/api/worlds/${worldId}/storage`, { method: "POST", body: { mode: storage.mode, hostType: storage.hostType, provider: storage.provider, manifestUrl, refresh, ...changes } });
      setStorage(result.storage); setProviders(result.providers || providers);
      setHostTypes(result.hostTypes || hostTypes);
      if (manifestUrl) setManifestUrl("");
      toast(refresh ? `Cloud manifest verified: ${result.storage.fileCount} file(s) ready.` : "File delivery settings saved.", "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function copyTemplate() {
    try {
      const result = await api(`/api/worlds/${worldId}/storage?template=1`);
      await navigator.clipboard.writeText(JSON.stringify(result.template, null, 2));
      toast("Cloud manifest template copied with the exact selected paths, sizes, and hashes.", "success");
    } catch (error) { toast(error.message, "error"); }
  }

  if (!storage) return <section className="panel-inset" style={{ padding: "1rem" }}><span className="subtle">Loading file delivery…</span></section>;
  return <section className="panel-inset" style={{ padding: "1rem" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
      <div><div className="heading" style={{ fontSize: ".96rem" }}>Hosting &amp; client file delivery</div><div className="subtle" style={{ fontSize: ".74rem", marginTop: 3 }}>Where the game runs and where clients download files are independent choices.</div></div>
      <span className="chip" style={{ background: storage.lastError ? "var(--red)" : storage.syncedAt ? "var(--green)" : "var(--card-2)" }}>{storage.lastError ? "NEEDS ATTENTION" : storage.syncedAt ? `${storage.fileCount} CLOUD FILES READY` : storage.mode === "local" ? "DIRECT DELIVERY READY" : "CLOUD MANIFEST NEEDS TEST"}</span>
    </div>
    <div style={{ marginTop: 12 }}>
      <div className="label">SERVER HOSTING</div>
      <div className="panel" style={{ padding: 4, display: "flex", gap: 4, width: "fit-content", flexWrap: "wrap" }}>
        {hostTypes.map((host) => <button key={host.id} className={`btn ${storage.hostType === host.id ? "btn-primary" : "btn-subtle"}`} disabled={busy} onClick={() => { setStorage((current) => ({ ...current, hostType: host.id })); save(false, { hostType: host.id }); }}>{host.label}</button>)}
      </div>
      <div className="subtle" style={{ fontSize: ".7rem", marginTop: 5 }}>Classification only: a rented or managed host can still publish its manifest and serve files directly, through cloud storage, or both.</div>
    </div>
    <div className="label" style={{ marginTop: 12 }}>CLIENT FILE SOURCE</div>
    <div className="panel" style={{ padding: 4, display: "flex", gap: 4, marginTop: 6, width: "fit-content", flexWrap: "wrap" }}>
      {[['local','Direct from RSDW host'],['cloud','Cloud only'],['hybrid','Cloud + direct fallback']].map(([value,label]) => <button key={value} className={`btn ${storage.mode === value ? "btn-primary" : "btn-subtle"}`} disabled={busy} onClick={() => { setStorage((current) => ({ ...current, mode: value })); if (value === "local") save(false, { mode: value }); }}>{label}</button>)}
    </div>
    {storage.mode !== "local" && <>
      <div className="panel" style={{ padding: ".8rem", marginTop: 12 }}>
        <strong>Prepare public folder</strong>
        <div className="subtle" style={{ fontSize: ".72rem", margin: ".3rem 0 .65rem" }}>Copy the selected client-required files into one verified folder with an exact <code>rsdw-manifest.json</code> template. Upload the files, add their public links in that JSON, and then test the manifest below. Cloud account sign-in and upload are not automatic.</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select className="input" style={{ width: "auto" }} value={exportPlatform} onChange={(event) => setExportPlatform(event.target.value)} disabled={["copying", "verifying"].includes(exportJob?.phase)}>
            <option value="steam">Steam / Epic files</option><option value="gamepass">Game Pass files</option>
          </select>
          <button className="btn btn-primary" onClick={prepareExport} disabled={["copying", "verifying"].includes(exportJob?.phase)}><Icon name="download" size={14} /> Prepare Cloud Folder</button>
          {exportJob?.phase === "ready" && typeof window !== "undefined" && window.desktop?.isElectron && <button className="btn btn-ghost" onClick={() => window.desktop.openPath(exportJob.folder)}><Icon name="folder" size={14} /> Open Folder</button>}
        </div>
        {exportJob && exportJob.phase !== "idle" && <div className="subtle" style={{ fontSize: ".7rem", marginTop: 8 }}>
          {exportJob.phase === "failed" ? `Export failed: ${exportJob.error}` : exportJob.phase === "ready" ? `${exportJob.totalFiles} verified file(s) ready in ${exportJob.folder}` : `${exportJob.phase === "verifying" ? "Verifying" : "Copying"} ${exportJob.copiedFiles}/${exportJob.totalFiles} files · ${fmtBytes(exportJob.copiedBytes)} / ${fmtBytes(exportJob.totalBytes)} · ${exportJob.currentFile || "Starting…"}`}
        </div>}
        {["copying", "verifying"].includes(exportJob?.phase) && <progress style={{ width: "100%", marginTop: 6 }} value={exportJob.copiedFiles} max={Math.max(1, exportJob.totalFiles)} />}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 8, marginTop: 12 }}>
        {providers.map((provider) => { const art = PROVIDER_MARKS[provider.id] || PROVIDER_MARKS.generic; const active = storage.provider === provider.id; return <button key={provider.id} className={`panel ${active ? "lane-active" : ""}`} disabled={busy} onClick={() => setStorage((current) => ({ ...current, provider: provider.id, hasManifestUrl: active ? current.hasManifestUrl : false }))} style={{ padding: ".75rem", color: "inherit", cursor: "pointer", textAlign: "left", display: "flex", alignItems: "center", gap: 9 }}><span aria-hidden style={{ width: 31, height: 31, borderRadius: 9, display: "grid", placeItems: "center", color: "white", fontWeight: 900, background: `linear-gradient(135deg,${art.colors})` }}>{art.mark}</span><strong>{provider.label}</strong></button>; })}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(220px,1fr) auto auto", gap: 8, marginTop: 10 }}>
        <input className="input" type="password" autoComplete="off" placeholder={storage.hasManifestUrl ? "Public manifest link saved — enter only to replace" : "Paste public rsdw-manifest.json link"} value={manifestUrl} onChange={(event) => setManifestUrl(event.target.value)} />
        <button className="btn btn-ghost" disabled={busy || (!manifestUrl && !storage.hasManifestUrl)} onClick={() => save(false)}><Icon name="check" size={14} /> Save</button>
        <button className="btn btn-primary" disabled={busy || (!manifestUrl && !storage.hasManifestUrl)} onClick={() => save(true)}><Icon name="refresh" size={14} /> Test & refresh</button>
      </div>
      {storage.lastError && <div className="panel-inset" style={{ marginTop: 8, padding: ".65rem .75rem", borderLeft: "3px solid var(--red)", fontSize: ".74rem" }}>{storage.lastError}</div>}
      <details style={{ marginTop: 10 }}><summary className="subtle" style={{ cursor: "pointer", fontWeight: 780 }}>Public folder setup and manifest format</summary>
        <ol className="subtle" style={{ fontSize: ".73rem", lineHeight: 1.6, paddingLeft: 20 }}><li>Prepare the cloud folder above, upload its files to {storage.providerLabel}, and enable <strong>Anyone with the link / Viewer</strong> on each file.</li><li>Replace each placeholder in the generated <code>rsdw-manifest.json</code> with that file&apos;s public share link, then upload the JSON file too.</li><li>Paste the public JSON link above and choose <strong>Test & refresh</strong>. Repeat after changing files.</li></ol>
        <button className="btn btn-ghost" style={{ marginBottom: 8 }} onClick={copyTemplate}><Icon name="file" size={14} /> Copy exact manifest template</button>
        <pre className="panel" style={{ padding: ".7rem", fontSize: ".68rem", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{`{\n  "schema": "${storage.schema}",\n  "revision": "release-1",\n  "files": [{\n    "target": "RSDragonwilds/Content/Paks/~mods/Example.pak",\n    "size": 12345,\n    "sha256": "64 lowercase hex characters",\n    "url": "https://public-provider-link"\n  }]\n}`}</pre>
      </details>
      <div className="subtle" style={{ fontSize: ".7rem", marginTop: 8 }}><Icon name="shield" size={13} /> RSDW never returns the saved provider link in its UI API, World profile, manifest, or logs. A client’s network tools can still observe the cloud host during transfer.</div>
    </>}
    {storage.mode === "local" && <div className="subtle" style={{ fontSize: ".74rem", marginTop: 10 }}>Authenticated clients download from the RSDW instance attached to this server, using signed file routes. This works on this PC, a VPS, or a paid game host when its Sync port is reachable.</div>}
  </section>;
}
