"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, fmtBytes, fmtTime, Icon, toast } from "@/components/ui";

export default function LocalWorldScanner({ service, onService, onCreated, onClose }) {
  const [data, setData] = useState({ discoveries: [], managed: [], roots: [] });
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setBusy(true);
    try { setData(await api("/api/profile-saves")); }
    catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const worlds = useMemo(() => {
    const byId = new Map();
    for (const item of data.managed || []) if (item.kind === "world") byId.set(item.id, { ...item, managed: true });
    for (const item of data.discoveries || []) if (item.kind === "world" && !byId.has(item.id)) byId.set(item.id, item);
    return [...byId.values()].sort((a, b) => Number(b.modifiedAt || 0) - Number(a.modifiedAt || 0));
  }, [data]);
  const wgs = (data.discoveries || []).filter((item) => item.kind === "wgs");

  async function scanFolder() {
    const root = await window.desktop?.pickDirectory?.();
    if (!root) return;
    setBusy(true);
    try { setData(await api("/api/profile-saves", { method: "POST", body: { action: "scan", roots: [root] } })); }
    catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function extract(item) {
    setBusy(true);
    try {
      const result = await api("/api/profile-saves", { method: "POST", body: { action: "extract-wgs", sourcePath: item.sourcePath } });
      toast(`Extracted ${result.worlds} Game Pass world save(s).`, "success");
      await load();
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function create(item) {
    setBusy(true);
    try {
      const result = await api("/api/profile-saves", { method: "POST", body: { action: "create-profile", id: item.managed ? item.id : null, sourcePath: item.managed ? null : item.sourcePath, service } });
      toast(`${result.profile.display_name} added to My Worlds.`, "success");
      await load();
      await onCreated?.(result.profile);
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  return <section className="panel" style={{ padding: "1rem", marginBottom: "1rem", borderColor: "var(--accent)" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
      <div><div className="eyebrow">LOCAL WORLD DISCOVERY</div><h2 className="heading" style={{ margin: ".2rem 0" }}>Scan for Worlds</h2><p className="subtle" style={{ margin: 0 }}>Find standard `.sav` worlds and Game Pass WGS containers, then turn a save into a managed World profile.</p></div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><button className="btn btn-ghost" disabled={busy} onClick={scanFolder}><Icon name="folder" size={15} /> Scan another folder</button><button className="btn btn-subtle" disabled={busy} onClick={load}><Icon name="refresh" size={15} /> Rescan</button><button className="btn btn-ghost" onClick={onClose}>Close</button></div>
    </header>
    <div className="panel-inset" style={{ padding: 10, marginTop: 12, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <strong>Launch imported Worlds with</strong>
      <button className={`btn ${service === "steam" ? "btn-primary" : "btn-ghost"}`} onClick={() => onService("steam")}>Steam</button>
      <button className={`btn ${service === "epic" ? "btn-primary" : "btn-ghost"}`} onClick={() => onService("epic")}>Epic Games</button>
      <span className="subtle">Game Pass write-back uses the verified converter.</span>
    </div>
    {!!wgs.length && <div style={{ display: "grid", gap: 7, marginTop: 12 }}>{wgs.map((item) => <SaveCandidate key={item.id} item={item} action={<button className="btn btn-primary" disabled={busy} onClick={() => extract(item)}>Extract Game Pass Worlds</button>} />)}</div>}
    <div style={{ display: "grid", gap: 7, marginTop: 12 }}>
      {worlds.map((item) => <SaveCandidate key={item.id} item={item} action={item.assignment?.scope === "world" ? <span className="chip">ALREADY IN MY WORLDS</span> : <button className="btn btn-primary" disabled={busy} onClick={() => create(item)}>Add to My Worlds</button>} />)}
      {!worlds.length && !wgs.length && <div className="panel-inset subtle" style={{ padding: 18, textAlign: "center" }}>{busy ? "Scanning Dragonwilds save locations…" : "No worlds found. Launch Dragonwilds once or choose Scan another folder."}</div>}
    </div>
  </section>;
}

function SaveCandidate({ item, action }) {
  return <div className="panel-inset" style={{ padding: 11, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
    <div style={{ minWidth: 0, flex: 1 }}><div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}><strong>{item.name}</strong><span className="chip">{item.kind === "wgs" ? "GAME PASS WGS" : "WORLD .SAV"}</span>{item.service === "gamepass" && <span className="chip">GAME PASS SOURCE</span>}</div><div className="subtle" style={{ fontSize: ".68rem", marginTop: 4, overflowWrap: "anywhere" }}>{item.originalPath || item.sourcePath}</div><div className="subtle" style={{ fontSize: ".65rem", marginTop: 2 }}>{item.files || 1} file(s) · {fmtBytes(item.size || 0)} · {fmtTime(item.modifiedAt)}</div></div>
    {action}
  </div>;
}
