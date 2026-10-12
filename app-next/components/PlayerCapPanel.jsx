"use client";

import { useCallback, useEffect, useState } from "react";
import { api, toast } from "@/components/ui";

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

  return <div>
    <label className="label" htmlFor={`max-players-${worldId}`} style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
      <span>Max players</span><span className="subtle" style={{ fontSize: ".6rem" }}>GAME.INI</span>
    </label>
    <div style={{ display: "flex", gap: 6 }}>
      <input id={`max-players-${worldId}`} className="input" type="number" min="1" max="128" step="1" value={draft}
        onChange={(event) => setDraft(event.target.value)} disabled={!record || busy} style={{ minWidth: 72, flex: 1 }} />
      <button className="btn btn-ghost" type="button" onClick={save} disabled={busy || !record || draft === String(record.maxPlayers)}
        title="The player cap is saved separately from DedicatedServer.ini settings">
        {busy ? "Saving…" : "Save cap"}
      </button>
    </div>
    <div className="subtle" style={{ fontSize: ".66rem", marginTop: 4 }}>
      Per-server profile. Six is the standard limit; higher values may require a compatible mod.
      {record?.running && <strong style={{ color: "var(--yellow)", marginLeft: 4 }}>Restart required.</strong>}
    </div>
    {record && <details style={{ marginTop: 4, fontSize: ".68rem" }}>
      <summary className="subtle" style={{ cursor: "pointer" }}>Game.ini path and current content</summary>
      <div className="subtle" style={{ overflowWrap: "anywhere", margin: ".4rem 0" }}>{record.path}</div>
      <pre className="panel" style={{ fontSize: ".66rem", padding: ".5rem", maxHeight: 180, overflow: "auto", whiteSpace: "pre-wrap" }}>
        {record.content || "Game.ini does not exist yet. It will be created at the next server start."}
      </pre>
      {!record.active && <div className="subtle">The live file may currently belong to another server profile.</div>}
    </details>}
  </div>;
}
