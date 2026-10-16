"use client";
import { useCallback, useEffect, useState } from "react";
import { api, Icon, toast } from "@/components/ui";

export default function LanDiscoveryPanel() {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(() => api("/api/sync/broadcast").then(setState).catch((e) => setError(e.message)), []);
  useEffect(() => { void load(); }, [load]);
  async function toggle(enabled = !state?.enabled || !state?.broadcasting) {
    if (!state || busy) return;
    setBusy(true); setError("");
    try {
      const result = await api("/api/sync/broadcast", { method: "POST", body: { enabled } });
      setState(result);
      toast(result.enabled ? "LAN discovery enabled. Nearby clients can find your published worlds." : "LAN discovery disabled.", "success");
    } catch (e) { setError(e.message); toast(e.message, "error"); }
    finally { setBusy(false); }
  }
  return <section className="panel lan-discovery-card" aria-label="LAN discovery">
    <div><strong><Icon name="globe" size={16} /> Discoverable on your network</strong>
      <p className="subtle">Opt in to let nearby RSDW clients find your published servers and player shares. This does not start the game or open remote administration. Passwords and sync verification still apply.</p>
      <p className="subtle">Allow UDP 27051 and your Sync TCP port through the host firewall. LAN discovery does not cross routers; friends elsewhere can use your IP.</p>
      {error && <p role="alert" style={{ color: "var(--red)" }}>{error} <button className="btn btn-ghost" onClick={() => { setError(""); void load(); }}>Retry status</button></p>}
    </div>
    <div className="library-action-group">
      <button className={`btn ${state?.broadcasting ? "btn-primary" : "btn-ghost"}`} aria-pressed={!!state?.broadcasting} disabled={!state || busy} onClick={() => toggle()}>{busy ? "Applying…" : !state ? "Loading…" : state.broadcasting ? "LAN discovery on" : state.enabled ? "Retry LAN discovery" : "Enable LAN discovery"}</button>
      {state?.enabled && !state.broadcasting && <button className="btn btn-ghost" disabled={busy} onClick={() => toggle(false)}>Turn discovery off</button>}
    </div>
  </section>;
}
