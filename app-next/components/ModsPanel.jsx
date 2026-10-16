"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, Icon, toast } from "@/components/ui";
import { useJobsPoll } from "@/components/jobsClient";
import ModCodeEditor from "@/components/ModCodeEditor";
import CloudStoragePanel from "@/components/CloudStoragePanel";

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
  const [editor, setEditor] = useState(null);
  const [editorSaving, setEditorSaving] = useState(false);
  const [prerequisites, setPrerequisites] = useState({ ue4ss: "", runeSchema: "" });
  const [runtimePackages, setRuntimePackages] = useState(null);
  const [updates, setUpdates] = useState({});
  const [checkingUpdates, setCheckingUpdates] = useState(false);
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

  useEffect(() => window.desktop?.onModProviderDownloadComplete?.((result) => {
    toast(`${result.modName} download staged. Open Downloads for the saved path.`, "success");
    try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {}
  }), []);

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

  async function checkModUpdates() {
    setCheckingUpdates(true);
    try {
      const result = await api(`/api/worlds/${worldId}/mods/updates`, { method: "POST", body: {} });
      setUpdates(result.updates || {});
      const count = Object.values(result.updates || {}).filter((entry) => entry.updateAvailable).length;
      toast(count ? `${count} mod update${count === 1 ? "" : "s"} available.` : "Linked mod checks complete.", "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setCheckingUpdates(false); }
  }

  async function viewProvider(mod) {
    const url = mod.identity?.projectUrl;
    if (!url) return toast("Add ProjectURL to this mod's ID.txt first.", "error");
    try {
      if (window.desktop?.openExternal) await window.desktop.openExternal(url);
      else window.open(url, "_blank", "noopener,noreferrer");
    } catch (error) { toast(error.message, "error"); }
  }

  async function downloadProvider(mod) {
    const url = mod.identity?.projectUrl;
    if (!url || !window.desktop?.openModProvider) return viewProvider(mod);
    try {
      await window.desktop.openModProvider({ url, targetPath: mod.path, worldId, modName: mod.name });
      toast("Download browser opened. Files from this session are assigned to the selected mod profile.", "success");
    } catch (error) { toast(error.message, "error"); }
  }

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

  async function toggleLoader(mod) {
    if (running || busy) return;
    setBusy(true);
    try {
      const enabled = mod.loaderEnabled !== true;
      const result = await api(`/api/worlds/${worldId}/mods`, { method: "PUT", body: { lane: mod.lane, selectionKey: mod.selectionKey, enabled } });
      setData((current) => ({ ...current, ...result }));
      toast(`${mod.name} ${enabled ? "enabled" : "disabled"} in its loader list. Restart the game or server to apply it.`, "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  }

  async function deleteMod(mod) {
    if (running || busy || !data?.canDeleteServerMods || mod.lane !== "server") return;
    const contents = mod.type === "pak" ? `${mod.files?.length || 0} PAK companion files` : "the entire mod entry";
    if (!window.confirm(`Delete ${mod.name} from this Server profile? This moves ${contents} to the OS Recycle Bin/Trash and removes its loader-list entry. It will not delete copies in other profiles or client installs.`)) return;
    setBusy(true);
    try {
      const result = await api(`/api/worlds/${worldId}/mods`, { method: "DELETE", body: { selectionKey: mod.selectionKey } });
      setData((current) => ({ ...current, ...result }));
      toast(`${mod.name} moved to the OS Recycle Bin/Trash.`, "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
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

  async function openEditor(file) {
    try {
      const result = await api(`/api/worlds/${worldId}/mods/editor?lane=${encodeURIComponent(activeLane)}&path=${encodeURIComponent(file.relative)}`);
      setEditor(result.file);
    } catch (e) { toast(e.message, "error"); }
  }

  async function saveEditor(content) {
    setEditorSaving(true);
    try {
      const result = await api(`/api/worlds/${worldId}/mods/editor`, { method: "PUT", body: { lane: activeLane, path: editor.relative, content, etag: editor.etag } });
      setEditor(result.file);
      toast(result.file.hotload && running ? `${result.file.modName} hotload file updated.` : `${result.file.name} saved.`, "success");
      return true;
    } catch (e) { toast(e.message, "error"); return false; }
    finally { setEditorSaving(false); }
  }

  if (!data) return <p className="subtle">Detecting routed installs and mods…</p>;

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <CloudStoragePanel worldId={worldId} />
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
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn btn-ghost" disabled={checkingUpdates} onClick={checkModUpdates}><Icon name="refresh" size={14} /> {checkingUpdates ? "Checking…" : "Check mod updates"}</button>
            <span className="chip">{selections.size} managed</span><span className="chip">{clientCount} client</span><span className="chip">{serverCount} server</span>
          </div>
        </div>
        <p className="subtle" style={{ fontSize: "0.76rem", margin: "0 0 10px" }}>
          Enable or disable UE4SS and RuneSchema mods in their loader lists. Manage mod controls synchronization; Unmanage leaves the source alone but can remove a copy this launcher synchronized into the Server profile. For stopped RSDW-managed Server profiles, Delete files moves the actual mod to the OS Recycle Bin/Trash. Disabled loader mods are not published in the downloadable manifest. Restart the game or server after changing loader state.
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
                  {items.map((mod) => <ModFolder key={mod.selectionKey} mod={mod} update={updates[mod.selectionKey]} selection={selections.get(mod.selectionKey)} busy={busy || running} canDelete={lane.id === "server" && data.canDeleteServerMods} onDelete={() => deleteMod(mod)} onToggle={() => toggleFolder(mod)} onLoaderToggle={() => toggleLoader(mod)} onScope={(scope) => setScope(mod, scope)} onExplore={() => browse(relativeModPath(lane.root, mod.path))} onView={() => viewProvider(mod)} onDownload={() => downloadProvider(mod)} />)}
                </div>
              </div>;
            })}
            {!lane.mods.length && <Notice>No supported mod folders were detected in this install.</Notice>}
          </div>
        )}
      </section>}

      {browser && <FolderExplorer data={browser} onBrowse={browse} onEdit={openEditor} onClose={() => setBrowser(null)} />}
      {editor && <ModCodeEditor file={editor} running={running} saving={editorSaving} onSave={saveEditor} onClose={() => setEditor(null)} />}
    </div>
  );
}

function ModFolder({ mod, update, selection, busy, canDelete, onDelete, onToggle, onLoaderToggle, onScope, onExplore, onView, onDownload }) {
  const selected = !!selection;
  const scope = selection?.scope || "both";
  const runtimeLabel = { runeschema: "RuneSchema", ue4ss: "UE4SS", framework: "RuneSchema runtime", pak: "PAK" }[mod.type] || mod.type;
  const loaderLabel = mod.loaderEnabled === true ? "Enabled" : mod.loaderStateSource === "not in loader list" ? "Not enabled (no list entry)" : mod.loaderEnabled === false ? "Disabled" : "Status unknown";
  return <div className="panel-inset" style={{ padding: "0.65rem 0.75rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: "0.82rem", fontWeight: 720, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>{mod.name}<span className="chip">{runtimeLabel}</span></div>
      {mod.identity && <div style={{ display: "flex", gap: 5, flexWrap: "wrap", margin: "3px 0" }}>
        <span className="chip">ID · {mod.identity.modId}</span>
        {mod.identity.author && <span className="chip">BY {mod.identity.author}</span>}
        {mod.identity.version && <span className="chip">v{mod.identity.version}</span>}
        {mod.identity.provider && <span className="chip">{mod.identity.provider === "nexus" ? "NEXUS MODS" : "CURSEFORGE"}</span>}
        {update?.updateAvailable && <span className="chip" style={{ background: "var(--yellow)", color: "var(--accent-ink)" }}>UPDATE · {update.latestVersion || update.latestFileId}</span>}
        {update?.checked && !update.updateAvailable && <span className="chip" style={{ background: "var(--green)" }}>CURRENT</span>}
        {update && !update.checked && mod.identity.projectUrl && <span className="chip" title={update.reason}>CHECK PROVIDER</span>}
        <span className="chip">{mod.identity.runtimeRole.toUpperCase()}</span><span className="chip">HOTLOAD {mod.identity.hotload ? "YES" : "NO"}</span>
      </div>}
      <div className="subtle" style={{ fontSize: "0.67rem", wordBreak: "break-all" }}>{mod.path}</div>
      {mod.loaderListFile && <div className="subtle" style={{ fontSize: "0.67rem" }}>{runtimeLabel} status: {loaderLabel} · {mod.loaderStateSource}</div>}
      {mod.loaderBlockedByFramework && <div className="subtle" style={{ fontSize: "0.67rem", color: "var(--yellow)" }}>RuneSchema runtime is not enabled in UE4SS.</div>}
    </div>
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
      {mod.loaderListFile && <button className={`btn ${mod.loaderEnabled === true ? "btn-ghost" : "btn-primary"}`} disabled={busy} onClick={onLoaderToggle}>{mod.loaderEnabled === true ? "Disable" : "Enable"}</button>}
      {mod.syncEligible
        ? <>
            <button className="btn btn-subtle" onClick={onExplore}><Icon name="file" size={14} /> Code</button>
            {mod.identity?.projectUrl && <button className="btn btn-subtle" title="Open the linked mod project in your default browser" onClick={onView}><Icon name="upload" size={14} /> View mod</button>}
            {mod.identity?.projectUrl && update?.updateAvailable && <button className="btn btn-primary" title={update?.reason || "Download the available update into this profile"} onClick={onDownload}><Icon name="download" size={14} /> Download update</button>}
            {selected && <div className="panel" style={{ padding: 3, display: "flex", gap: 3 }}>
              {["client", "server", "both"].map((value) => <button key={value} className={`btn ${scope === value ? "btn-primary" : "btn-subtle"}`} style={{ padding: ".35rem .55rem" }} disabled={busy} onClick={() => onScope(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}
            </div>}
            <button className={`btn ${selected ? "btn-ghost" : "btn-primary"}`} disabled={busy} onClick={onToggle}>{selected ? "Unmanage" : "Manage mod"}</button>
            {canDelete && <button className="btn btn-danger" disabled={busy} title="Move this profile's mod files to the OS Recycle Bin/Trash" onClick={onDelete}>Delete files</button>}
          </>
        : <span className="chip">Detected runtime</span>}
    </div>
  </div>;
}

function FolderExplorer({ data, onBrowse, onEdit, onClose }) {
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
      {(data.files || []).map((file) => <button key={file.relative} className="btn btn-ghost" style={{ justifyContent: "flex-start" }} onClick={() => onEdit(file)}><Icon name="file" size={14} /> <span style={{ flex: 1, textAlign: "left" }}>{file.name}</span><span className="chip">{file.language.toUpperCase()}</span>{file.hotload && <span className="chip" style={{ background: "var(--green)" }}>HOTLOAD</span>}</button>)}
      {!data.directories.length && !(data.files || []).length && <div className="subtle" style={{ fontSize: "0.75rem" }}>No child folders or editable JSON, JSONC, or Lua files.</div>}
    </div>
  </section>;
}

function relativeModPath(root, target) {
  const base = String(root || "").replace(/\\/g, "/").replace(/\/$/, "");
  const file = String(target || "").replace(/\\/g, "/");
  return file.toLowerCase().startsWith(`${base.toLowerCase()}/`) ? file.slice(base.length + 1) : "";
}

function Notice({ children }) {
  return <div className="panel-inset" style={{ padding: "0.7rem 0.85rem", marginTop: 10, borderLeft: "3px solid var(--line-strong)", fontSize: "0.78rem", fontWeight: 620 }}>{children}</div>;
}
