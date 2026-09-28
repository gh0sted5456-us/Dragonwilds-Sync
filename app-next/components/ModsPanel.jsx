"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, Icon, toast } from "@/components/ui";

const GROUPS = [
  ["runeschema", "RuneSchema mods"],
  ["ue4ss", "UE4SS mods"],
  ["pak", "PAK mods"],
  ["framework", "Detected runtimes"],
];

export default function ModsPanel({ worldId, running }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [activeLane, setActiveLane] = useState("server");
  const [browser, setBrowser] = useState(null);
  const [prerequisites, setPrerequisites] = useState({ ue4ss: "", runeSchema: "" });
  const [runtimePackages, setRuntimePackages] = useState(null);
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

  const lanes = data?.modLanes || [];
  const lane = lanes.find((item) => item.id === activeLane) || lanes[0];
  const selected = useMemo(() => new Set(data?.modLaneSelections || []), [data]);

  async function uploadRuntime(component) {
    if (!isElectron) return toast("Runtime ZIP selection is available in the desktop app.", "error");
    if (running) return toast("Stop the active server before replacing a runtime.", "error");
    const zipPath = await window.desktop.pickZip();
    if (!zipPath) return;
    setBusy(true);
    try {
      const result = await api(`/api/worlds/${worldId}/runtime`, { method: "POST", body: { component, zipPath } });
      setRuntimePackages(result.packages || null);
      const label = component === "ue4ss" ? "UE4SS" : "RuneSchema";
      toast(`${label} staged for the host and verified client Sync.`, "success");
      await load();
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
      else await api("/api/client-installs", { method: "POST", body: { [targetLane]: install } });
      await load();
      toast(`${targetLane === "server" ? "Server" : targetLane === "steam" ? "Steam" : "PC Game Pass"} install routed.`, "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  }

  async function toggleFolder(mod) {
    if (!mod.syncEligible || running) return;
    const keys = new Set(selected);
    if (keys.has(mod.selectionKey)) keys.delete(mod.selectionKey); else keys.add(mod.selectionKey);
    setBusy(true);
    try {
      const result = await api(`/api/worlds/${worldId}/mods/sync`, { method: "POST", body: { keys: [...keys] } });
      setData((current) => ({ ...current, ...result }));
      toast("Selected mod folders saved and synchronized.", "success");
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
          Upload complete UE4SS and RuneSchema ZIPs for this World. RSDW Sync installs them on the host, publishes only client-compatible files, verifies hashes, and places them into the connected player’s Steam or PC Game Pass install automatically.
        </p>
        <div className="runtime-package-grid">
          {["ue4ss","runeschema"].map((component) => {
            const row = runtimePackages?.[component] || {};
            const label = component === "ue4ss" ? "UE4SS" : "RuneSchema";
            return <div key={component} className="panel" style={{ padding: "0.9rem 1rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <img src={component === "ue4ss" ? "/rsdw/platforms/ue4ss.webp" : "/rsdw/platforms/runeschema.webp"} alt="" style={{ width: 28, height: 28, objectFit: "contain" }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontWeight: 850 }}>{label}</div>
                  <div className="subtle" style={{ fontSize: "0.68rem", overflowWrap: "anywhere" }}>
                    {row.installed ? `${row.archive} · ${row.clientFiles} client files` : "No managed runtime ZIP"}
                  </div>
                </div>
                <span className="chip" style={{ background: row.installed ? "var(--green)" : "var(--line)" }}>{row.installed ? "MANAGED" : "OPTIONAL"}</span>
              </div>
              <button className="btn btn-ghost" style={{ marginTop: 10, width: "100%" }} disabled={busy || running} onClick={() => uploadRuntime(component)}>
                <Icon name="upload" size={14} /> {row.installed ? `Replace ${label} ZIP` : `Upload ${label} ZIP`}
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
        <div className="heading" style={{ fontSize: "0.96rem", marginBottom: 4 }}>Install lanes</div>
        <p className="subtle" style={{ fontSize: "0.76rem", margin: "0 0 10px" }}>
          Route the host, Steam, and PC Game Pass installs once. Each lane is scanned through PAKs, UE4SS, RuneSchema, and nested mod folders.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8 }}>
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
                  {items.map((mod) => <ModFolder key={mod.selectionKey} mod={mod} selected={selected.has(mod.selectionKey)} busy={busy || running} onToggle={() => toggleFolder(mod)} />)}
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

function ModFolder({ mod, selected, busy, onToggle }) {
  return <div className="panel-inset" style={{ padding: "0.65rem 0.75rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: "0.82rem", fontWeight: 720 }}>{mod.name}</div>
      <div className="subtle" style={{ fontSize: "0.67rem", wordBreak: "break-all" }}>{mod.path}</div>
    </div>
    {mod.syncEligible
      ? <button className={`btn ${selected ? "btn-primary" : "btn-ghost"}`} disabled={busy} onClick={onToggle}>{selected ? "Selected" : "Select folder"}</button>
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
