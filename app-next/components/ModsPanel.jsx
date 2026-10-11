"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, Icon, toast } from "@/components/ui";
import { useJobsPoll } from "@/components/jobsClient";

const GROUPS = [
  ["runeschema", "RuneSchema mods"],
  ["ue4ss", "UE4SS mods"],
  ["pak", "PAK mods"],
  ["framework", "Detected runtimes"],
];

const RUNTIME_PACKAGES = [
  { component: "ue4ss-server", stateKey: "ue4ssServer", label: "UE4SS · Dedicated Server", icon: "/rsdw/platforms/ue4ss.webp", note: "Win64 · server-only · version.dll loader" },
  { component: "ue4ss-steam", stateKey: "ue4ssSteam", label: "UE4SS · Steam", icon: "/rsdw/platforms/ue4ss.webp", note: "Win64 client · dwmapi.dll loader" },
  { component: "ue4ss-gamepass", stateKey: "ue4ssGamepass", label: "UE4SS · PC Game Pass", icon: "/rsdw/platforms/ue4ss.webp", note: "WinGDK client" },
  { component: "runeschema", stateKey: "runeschema", label: "RuneSchema", icon: "/rsdw/platforms/runeschema.png", note: "Routed to server / Win64 / WinGDK as applicable" },
];

export default function ModsPanel({ worldId, running }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [activeLane, setActiveLane] = useState("server");
  const [browser, setBrowser] = useState(null);
  const [prerequisites, setPrerequisites] = useState({ ue4ss: "", runeSchema: "" });
  const [runtimePackages, setRuntimePackages] = useState(null);
  const jobs = useJobsPoll();
  const isElectron = typeof window !== "undefined" && window.desktop?.isElectron;

  const load = useCallback(async () => {
    try { setData(await api(`/api/worlds/${worldId}/mods`)); }
    catch (e) { toast(e.message, "error"); }
  }, [worldId]);

  useEffect(() => {
    load();
    api(`/api/worlds/${worldId}/sync/manifest`).then((result) => setPrerequisites({
      ue4ss: result.manifest?.prerequisites?.ue4ss || "",
      runeSchema: result.manifest?.prerequisites?.runeSchema || "",
    })).catch(() => {});
    api(`/api/worlds/${worldId}/runtime`).then((result) => setRuntimePackages(result.packages || null)).catch(() => {});
  }, [load, worldId]);

  const runtimeJobState = jobs.filter((job) => job.type === "runtime" && job.worldId === worldId).map((job) => `${job.id}:${job.status}`).join("|");
  const runtimeJobSucceeded = jobs.some((job) => job.type === "runtime" && job.worldId === worldId && job.status === "success");
  useEffect(() => {
    if (!runtimeJobState || !runtimeJobSucceeded) return;
    api(`/api/worlds/${worldId}/runtime`).then((result) => setRuntimePackages(result.packages || null)).catch(() => {});
    load();
  }, [runtimeJobState, runtimeJobSucceeded, load, worldId]);

  const lanes = data?.modLanes || [];
  const lane = lanes.find((item) => item.id === activeLane) || lanes[0];
  const selections = useMemo(() => new Map((data?.modSelections || (data?.modLaneSelections || []).map((key) => ({ key, scope: "both" }))).map((item) => [item.key, item])), [data]);
  const clientCount = useMemo(() => [...selections.values()].filter((item) => item.scope !== "server").length, [selections]);
  const serverCount = useMemo(() => [...selections.values()].filter((item) => item.scope !== "client").length, [selections]);

  async function uploadRuntime(component) {
    if (!isElectron) return toast("Runtime ZIP selection is available in the desktop app.", "error");
    if (running) return toast("Stop the active server before replacing a runtime.", "error");
    const zipPath = await window.desktop.pickZip();
    if (!zipPath) return;
    setBusy(true);
    try {
      const result = await api(`/api/worlds/${worldId}/runtime`, { method: "POST", body: { component, zipPath } });
      try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {}
      const label = RUNTIME_PACKAGES.find((item) => item.component === component)?.label || component;
      toast(result.alreadyRunning ? `${label} installation is already running.` : `${label} installation queued. Follow it in Downloads.`, "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  }

  async function savePrerequisites() {
    setBusy(true);
    try {
      await api(`/api/worlds/${worldId}/sync/manifest`, { method: "PATCH", body: { prerequisites } });
      toast("Runtime requirements published for this World.", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  }

  async function chooseInstall(targetLane) {
    if (!isElectron) return toast("Folder selection is available in the desktop app.", "error");
    const install = await window.desktop.pickDirectory();
    if (!install) return;
    setBusy(true);
    try {
      if (targetLane === "server") await api(`/api/worlds/${worldId}`, { method: "PATCH", body: { install_dir: install } });
      else if (targetLane === "required") await api(`/api/worlds/${worldId}/mods/source`, { method: "POST", body: { path: install } });
      else await api("/api/client-installs", { method: "POST", body: { [targetLane]: install } });
      await load();
      toast(`${targetLane === "server" ? "Server" : targetLane === "required" ? "Required player mods" : targetLane === "steam" ? "Steam" : "PC Game Pass"} install routed.`, "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  }

  async function toggleFolder(mod) {
    if (!mod.syncEligible || running) return;
    const next = new Map(selections);
    if (next.has(mod.selectionKey)) next.delete(mod.selectionKey); else next.set(mod.selectionKey, { key: mod.selectionKey, scope: "both" });
    await saveSelections([...next.values()]);
  }

  async function setScope(mod, scope) {
    if (running || !selections.has(mod.selectionKey)) return;
    const next = new Map(selections);
    next.set(mod.selectionKey, { ...next.get(mod.selectionKey), scope });
    await saveSelections([...next.values()]);
  }

  async function saveSelections(next) {
    setBusy(true);
    try {
      const result = await api(`/api/worlds/${worldId}/mods/sync`, { method: "POST", body: { selections: next } });
      setData((current) => ({ ...current, ...result }));
      toast("Managed mods saved and synchronized.", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  }

  async function setPakInstallMode(pakInstallMode) {
    if (running || data?.pakInstallMode === pakInstallMode) return;
    setBusy(true);
    try {
      const result = await api(`/api/worlds/${worldId}/mods`, { method: "PATCH", body: { pakInstallMode } });
      setData((current) => ({ ...current, ...result }));
      toast(pakInstallMode === "runeschema" ? "PAK mods will be installed through RuneSchema folders." : "PAK mods will be installed in Content/Paks/~mods.", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  }

  async function browse(relative = "") {
    try {
      const result = await api(`/api/worlds/${worldId}/mods/explorer?lane=${encodeURIComponent(activeLane)}&path=${encodeURIComponent(relative)}`);
      setBrowser(result);
    } catch (e) { toast(e.message, "error"); }
  }

  if (!data) return <p className="subtle">Detecting routed installs and mods…</p>;

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <section className="panel-inset" style={{ padding: "0.95rem 1rem" }}>
        <div className="heading" style={{ fontSize: "0.96rem" }}>World runtimes</div>
        <p className="subtle" style={{ fontSize: "0.76rem", margin: "4px 0 10px" }}>
          Each World profile owns its runtime packages. Dedicated-server UE4SS is separate from client UE4SS: the server uses version.dll, Steam uses dwmapi.dll, and Game Pass uses its WinGDK lane. Sync publishes only client-compatible files and verifies every download by hash.
        </p>
        <div className="runtime-package-grid">
          {RUNTIME_PACKAGES.map((pkg) => {
            const row = runtimePackages?.[pkg.stateKey] || {};
            return <div key={pkg.component} className="panel" style={{ padding: "0.9rem 1rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <img src={pkg.icon} alt="" style={{ width: 28, height: 28, objectFit: "contain" }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontWeight: 850 }}>{pkg.label}</div>
                  <div className="subtle" style={{ fontSize: "0.68rem", overflowWrap: "anywhere" }}>
                    {row.installed ? `${row.archive} · ${row.clientFiles} client files` : pkg.note}
                  </div>
                </div>
                <span className="chip" style={{ background: row.installed ? "var(--green)" : "var(--line)" }}>{row.installed ? "MANAGED" : "OPTIONAL"}</span>
              </div>
              <button className="btn btn-ghost" style={{ marginTop: 10, width: "100%" }} disabled={busy || running} onClick={() => uploadRuntime(pkg.component)}>
                <Icon name="upload" size={14} /> {row.installed ? `Replace ${pkg.label} ZIP` : `Upload ${pkg.label} ZIP`}
              </button>
            </div>;
          })}
        </div>
        {running && <Notice>Runtime ZIPs are optional and never gate launch. Stop this World only when you want to replace one.</Notice>}
        <details style={{ marginTop: 10 }}>
          <summary className="subtle" style={{ cursor: "pointer", fontWeight: 750 }}>Optional version labels</summary>
          <p className="subtle" style={{ fontSize: "0.72rem" }}>Labels are informational; the uploaded files and their hashes are the actual Sync contract.</p>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(150px, 1fr) minmax(150px, 1fr) auto", gap: 8 }}>
            <input className="input" placeholder="UE4SS version label" value={prerequisites.ue4ss} onChange={(e) => setPrerequisites((value) => ({ ...value, ue4ss: e.target.value }))} />
            <input className="input" placeholder="RuneSchema version label" value={prerequisites.runeSchema} onChange={(e) => setPrerequisites((value) => ({ ...value, runeSchema: e.target.value }))} />
            <button className="btn btn-primary" disabled={busy} onClick={savePrerequisites}>Save labels</button>
          </div>
        </details>
      </section>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div className="heading" style={{ fontSize: "0.96rem", marginBottom: 4 }}>Managed mods</div>
          <div style={{ display: "flex", gap: 6 }}><span className="chip">{selections.size} managed</span><span className="chip">{clientCount} client</span><span className="chip">{serverCount} server</span></div>
        </div>
        <p className="subtle" style={{ fontSize: "0.76rem", margin: "0 0 10px" }}>
          Select a discovered mod, then choose where it belongs: Client, Server, or Both. Client files are published in the downloadable manifest; Server files are materialized on the host. Existing selections migrate to Both automatically.
        </p>
        <div className="panel-inset" style={{ padding: ".8rem", marginBottom: 10, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 220 }}><strong>PAK destination</strong><div className="subtle" style={{ fontSize: ".7rem" }}>Choose classic <code>Content/Paks/~mods</code>, or let RuneSchema load each triplet from <code>RuneSchema/mods/&lt;ModID&gt;/paks</code>.</div></div>
          <div className="panel" style={{ padding: 3, display: "flex", gap: 3 }}>
            <button className={`btn ${data.pakInstallMode !== "runeschema" ? "btn-primary" : "btn-subtle"}`} disabled={busy || running} onClick={() => setPakInstallMode("classic")}>Classic ~mods</button>
            <button className={`btn ${data.pakInstallMode === "runeschema" ? "btn-primary" : "btn-subtle"}`} disabled={busy || running} onClick={() => setPakInstallMode("runeschema")}>RuneSchema</button>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
          {lanes.map((item) => (
            <button key={item.id} className={`panel-inset ${activeLane === item.id ? "lane-active" : ""}`} onClick={() => { setActiveLane(item.id); setBrowser(null); }} style={{ padding: "0.85rem", textAlign: "left", cursor: "pointer", color: "inherit" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <strong>{item.label}</strong><span className="chip">{item.ready ? `${item.mods.length} found` : "Not routed"}</span>
              </div>
              <div className="subtle" style={{ fontSize: "0.68rem", marginTop: 6, wordBreak: "break-all" }}>{item.root || item.error}</div>
            </button>
          ))}
        </div>
      </section>

      {lane && <section className="panel-inset" style={{ padding: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div>
            <div className="heading" style={{ fontSize: "0.94rem" }}>{lane.label}</div>
            <div className="subtle" style={{ fontSize: "0.72rem", wordBreak: "break-all" }}>{lane.root || lane.error}</div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn btn-ghost" disabled={busy || running} onClick={() => chooseInstall(lane.id)}><Icon name="folder" size={14} /> Choose install</button>
            {lane.ready && <button className="btn btn-ghost" disabled={busy} onClick={() => browse("")}><Icon name="folder" size={14} /> Explore</button>}
            <button className="btn btn-subtle" disabled={busy} onClick={load}><Icon name="refresh" size={14} /> Rescan</button>
          </div>
        </div>

        {running && <Notice>Stop the active server before changing synchronized folders.</Notice>}
        {!lane.ready ? <Notice>{lane.error || "Choose an install to begin detection."}</Notice> : (
          <div style={{ display: "grid", gap: 12, marginTop: 14 }}>
            {GROUPS.map(([type, title]) => {
              const items = lane.mods.filter((mod) => type === "framework" ? !mod.syncEligible : mod.type === type && mod.syncEligible);
              if (!items.length) return null;
              return <div key={type}>
                <div className="subtle" style={{ fontSize: "0.7rem", fontWeight: 750, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 5 }}>{title}</div>
                <div style={{ display: "grid", gap: 5 }}>
                  {items.map((mod) => <ModFolder key={mod.selectionKey} mod={mod} selection={selections.get(mod.selectionKey)} busy={busy || running} onToggle={() => toggleFolder(mod)} onScope={(scope) => setScope(mod, scope)} />)}
                </div>
              </div>;
            })}
            {!lane.mods.length && <Notice>No supported mod folders were detected in this install.</Notice>}
          </div>
        )}
      </section>}

      {browser && <FolderExplorer data={browser} onBrowse={browse} onClose={() => setBrowser(null)} />}
    </div>
  );
}

function ModFolder({ mod, selection, busy, onToggle, onScope }) {
  const selected = !!selection;
  const scope = selection?.scope || "both";
  return <div className="panel-inset" style={{ padding: "0.65rem 0.75rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: "0.82rem", fontWeight: 720 }}>{mod.name}</div>
      {mod.identity && <div style={{ display: "flex", gap: 5, flexWrap: "wrap", margin: "3px 0" }}><span className="chip">ID · {mod.identity.modId}</span>{mod.identity.author && <span className="chip">BY {mod.identity.author}</span>}<span className="chip">{mod.identity.runtimeRole.toUpperCase()}</span><span className="chip">HOTLOAD {mod.identity.hotload ? "YES" : "NO"}</span></div>}
      <div className="subtle" style={{ fontSize: "0.67rem", wordBreak: "break-all" }}>{mod.path}</div>
    </div>
    {mod.syncEligible
      ? <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {selected && <div className="panel" style={{ padding: 3, display: "flex", gap: 3 }}>
            {["client", "server", "both"].map((value) => <button key={value} className={`btn ${scope === value ? "btn-primary" : "btn-subtle"}`} style={{ padding: ".35rem .55rem" }} disabled={busy} onClick={() => onScope(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}
          </div>}
          <button className={`btn ${selected ? "btn-ghost" : "btn-primary"}`} disabled={busy} onClick={onToggle}>{selected ? "Remove" : "Manage mod"}</button>
        </div>
      : <span className="chip">Detected only</span>}
  </div>;
}

function FolderExplorer({ data, onBrowse, onClose }) {
  const parent = data.relative.split("/").filter(Boolean).slice(0, -1).join("/");
  return <section className="panel-inset" style={{ padding: "1rem" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
      <div>
        <div className="heading" style={{ fontSize: "0.92rem" }}>Install explorer</div>
        <div className="subtle" style={{ fontSize: "0.68rem", wordBreak: "break-all" }}>{data.current}</div>
      </div>
      <button className="btn btn-ghost" onClick={onClose}>Close</button>
    </div>
    <div style={{ display: "flex", gap: 5, margin: "10px 0", flexWrap: "wrap" }}>
      <button className="btn btn-subtle" onClick={() => onBrowse("")}>Install</button>
      {data.breadcrumbs.map((crumb) => <button key={crumb.relative} className="btn btn-subtle" onClick={() => onBrowse(crumb.relative)}>{crumb.name}</button>)}
    </div>
    <div style={{ display: "grid", gap: 5 }}>
      {data.relative && <button className="btn btn-ghost" style={{ justifyContent: "flex-start" }} onClick={() => onBrowse(parent)}>← Parent folder</button>}
      {data.directories.map((folder) => <button key={folder.relative} className="btn btn-ghost" style={{ justifyContent: "flex-start" }} onClick={() => onBrowse(folder.relative)}><Icon name="folder" size={14} /> {folder.name}</button>)}
      {!data.directories.length && <div className="subtle" style={{ fontSize: "0.75rem" }}>No child folders.</div>}
    </div>
  </section>;
}

function Notice({ children }) {
  return <div className="panel-inset" style={{ padding: "0.7rem 0.85rem", marginTop: 10, borderLeft: "3px solid var(--line-strong)", fontSize: "0.78rem", fontWeight: 620 }}>{children}</div>;
}
