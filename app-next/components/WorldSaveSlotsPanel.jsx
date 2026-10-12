"use client";
import { useEffect, useState } from "react";
import { api, Icon, fmtBytes, toast } from "@/components/ui";

export default function WorldSaveSlotsPanel({ worldId, running, onChange }) {
  const [slots, setSlots] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedSaveError, setSelectedSaveError] = useState(null);
  const isElectron = typeof window !== "undefined" && window.desktop?.isElectron;

  useEffect(() => {
    let live = true;
    setLoading(true);
    api(`/api/worlds/${worldId}/save-slots`)
      .then((response) => { if (live) { setSlots(response.slots || []); setSelectedSaveError(response.selectedSaveError || null); } })
      .catch((error) => { if (live) toast(error.message, "error"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [worldId]);

  const importSave = async () => {
    if (!isElectron) return toast("Import a world save from the Windows desktop app.", "info");
    const savePath = await window.desktop.pickWorldSave();
    if (!savePath) return;
    if (!confirm(`Use the selected save for this server? RSDW will ${running ? "save and stop the server, " : ""}back up the current world, verify the replacement, and start with the selected save.`)) return;
    setBusy(true);
    try {
      const { check } = await api(`/api/worlds/${worldId}/import`, { method: "POST", body: { savePath } });
      setSlots(check.slots || []);
      setSelectedSaveError(null);
      toast(`${check.activeSave} was staged and verified. The server ${check.restarted ? "restarted" : "started"} with it.`, "success");
      onChange?.();
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  };

  const activateSlot = async (name) => {
    if (!confirm(`Load ${name} now? RSDW will ${running ? "save and stop the server, " : ""}back up the current world, place this save alone in SaveGames, verify it, and start the server.`)) return;
    setBusy(true);
    try {
      const { result } = await api(`/api/worlds/${worldId}/save-slots`, { method: "POST", body: { name, startAfter: true } });
      setSlots(result.slots || []);
      setSelectedSaveError(null);
      toast(`${name} was staged and verified. The server ${result.restarted ? "restarted" : "started"} with it.`, "success");
      onChange?.();
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  };

  return <section className="panel-inset" style={{ padding: "0.9rem 1rem", marginBottom: "1rem" }} aria-label="World save selection">
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
      <div>
        <h4 className="heading" style={{ fontSize: ".93rem", margin: 0 }}>World save</h4>
        <div className="subtle" style={{ fontSize: ".74rem", marginTop: 4, lineHeight: 1.5 }}>
          Select a save in this server profile, or import a new <code>.sav</code> or single-save ZIP. Switching keeps the server&apos;s login, Owner ID, ports, and mods.
        </div>
      </div>
      <button type="button" className="btn btn-ghost" disabled={busy || !isElectron} onClick={importSave}><Icon name="upload" size={15} /> {busy ? "Working…" : "Import world save"}</button>
    </div>
    <div className="subtle" style={{ fontSize: ".68rem", margin: "8px 0", wordBreak: "break-all" }}>Live location: RSDragonwilds/Saved/SaveGames · RSDW places only the selected .sav there before launch.</div>
    {selectedSaveError && <div className="panel-inset" role="alert" style={{ padding: ".55rem .7rem", borderColor: "var(--red)", color: "var(--ink)", fontSize: ".74rem", marginBottom: 8 }}>{selectedSaveError}</div>}
    {loading ? <p className="subtle">Scanning save slots…</p> : slots.length === 0 ? <p className="subtle">No world saves found for this server profile. Import a world save before starting if you don&apos;t want a new Standard world.</p> :
      <div style={{ display: "grid", gap: 7 }}>
        {slots.map((slot) => <div key={slot.name} className="panel-inset" style={{ padding: ".55rem .7rem", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <Icon name={slot.active ? "check" : "globe"} size={15} />
          <div style={{ flex: 1, minWidth: 170 }}><strong style={{ fontSize: ".8rem", wordBreak: "break-all" }}>{slot.name}</strong><div className="subtle" style={{ fontSize: ".68rem" }}>{fmtBytes(slot.size)} · {new Date(slot.modifiedAt).toLocaleString()}</div></div>
          {slot.active ? <span className="chip" style={{ background: "var(--accent)", color: "var(--accent-ink)" }}>ACTIVE</span> : <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => activateSlot(slot.name)}>{running ? "Swap & Restart" : "Activate & Start"}</button>}
        </div>)}
      </div>}
  </section>;
}
