"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Icon, toast } from "@/components/ui";

export default function PlayerCapPanel({ worldId }) {
  const [record, setRecord] = useState(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const result = await api(`/api/worlds/${worldId}/player-cap`);
    setRecord(result);
    setDraft(String(result.maxPlayers));
  }, [worldId]);

  useEffect(() => { load().catch((error) => toast(error.message, "error")); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      const result = await api(`/api/worlds/${worldId}/player-cap`, { method: "POST", body: { maxPlayers: draft } });
      setRecord(result);
      setDraft(String(result.maxPlayers));
      toast(result.running ? "Player cap saved. Restart this server to apply it." : "Player cap saved for this server profile.", "success");
      if (result.warning) toast(result.warning, "info");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  };

  return <section className="panel-inset" style={{ padding: "1rem", marginBottom: "1rem" }}>
    <div className="heading" style={{ fontSize: ".95rem" }}>Dedicated server player cap</div>
    <p className="subtle" style={{ fontSize: ".76rem", margin: ".3rem 0 .75rem" }}>
      Each server profile owns its cap. RSDW writes <code>Game.ini</code> → <code>[/Script/Engine.GameSession]</code> → <code>MaxPlayers</code> when the server starts. Six players is the documented game limit; higher values are experimental and may require a compatible mod.
    </p>
    <div style={{ display: "flex", gap: ".6rem", alignItems: "end", flexWrap: "wrap" }}>
      <label className="label" style={{ minWidth: 150 }}>Player cap
        <input className="input" type="number" min="1" max="128" step="1" value={draft}
          onChange={(event) => setDraft(event.target.value)} disabled={!record || busy} />
      </label>
      <button className="btn btn-primary" onClick={save} disabled={busy || !record || draft === String(record.maxPlayers)}>
        <Icon name="download" size={14} /> {busy ? "Saving…" : "Save player cap"}
      </button>
      {record?.running && <span className="chip" style={{ background: "var(--yellow)", color: "#1e1f22" }}>Restart required</span>}
    </div>
    {record && <details style={{ marginTop: ".75rem" }}>
      <summary className="subtle" style={{ cursor: "pointer", fontSize: ".73rem" }}>View Game.ini and its path</summary>
      <div className="subtle" style={{ fontSize: ".68rem", overflowWrap: "anywhere", margin: ".5rem 0" }}>{record.path}</div>
      <pre className="panel" style={{ fontSize: ".7rem", padding: ".6rem", maxHeight: 220, overflow: "auto", whiteSpace: "pre-wrap" }}>
        {record.content || "Game.ini does not exist yet. It will be created at the next server start."}
      </pre>
      {!record.active && <div className="subtle" style={{ fontSize: ".7rem" }}>This install can be shared by several server profiles. The live file may currently belong to another profile.</div>}
    </details>}
  </section>;
}
