"use client";
import { useCallback, useEffect, useState } from "react";
import { api, Icon, fmtBytes, toast } from "@/components/ui";

const TYPES = ["Standard", "HardMode", "Creative", "Custom"];
function WorldType({ item }) {
  const label = item.worldType || "Unknown type";
  return <span className="chip" title={item.typeSource === "manual" ? "Set by server manager; not verified in save data" : item.typeSource === "save" ? "Read from world save data" : "World mode could not be verified"} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
    <img src="/rsdw/dragonwilds-mark.png" alt="" width="17" height="17" style={{ objectFit: "contain", borderRadius: 3 }} /> {label}{item.typeSource === "manual" ? " · manual" : ""}
  </span>;
}

export default function WorldSaveSlotsPanel({ worldId, running, onChange }) {
  const [slots, setSlots] = useState([]);
  const [repository, setRepository] = useState([]);
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedSaveError, setSelectedSaveError] = useState(null);
  const [activeFilename, setActiveFilename] = useState(null);
  const isElectron = typeof window !== "undefined" && window.desktop?.isElectron;

  const applyResponse = (response) => {
    setSlots(response.slots || []);
    setRepository(response.repository || []);
    setPending(response.pending || null);
    setSelectedSaveError(response.selectedSaveError || null);
    setActiveFilename(response.activeFilename || null);
  };
  const load = useCallback(async () => applyResponse(await api(`/api/worlds/${worldId}/save-slots`)), [worldId]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    api(`/api/worlds/${worldId}/save-slots`)
      .then((response) => { if (live) applyResponse(response); })
      .catch((error) => { if (live) toast(error.message, "error"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [worldId, running]);

  const importSave = async () => {
    if (!isElectron) return toast("Import world saves from the Windows desktop app.", "info");
    const savePath = await window.desktop.pickWorldSave();
    if (!savePath) return;
    setBusy(true);
    try {
      const { item } = await api(`/api/worlds/${worldId}/import`, { method: "POST", body: { savePath } });
      await load();
      toast(`${item.name} added to the World Repository. No server was restarted.`, "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  };

  const setType = async (repositoryId, worldType) => {
    if (!worldType) return;
    setBusy(true);
    try {
      await api(`/api/worlds/${worldId}/import`, { method: "POST", body: { repositoryId, worldType } });
      await load();
      toast("World type label saved. The world save itself was not changed.", "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  };

  const activate = async (selection, label) => {
    const message = running
      ? `Queue ${label} for this server? The running world will keep playing; the new save will be installed as ${activeFilename} on its next start.`
      : `Place ${label} into this server profile's SaveGames as ${activeFilename}? The current save will be backed up. The server will remain stopped.`;
    if (!confirm(message)) return;
    setBusy(true);
    try {
      const { result } = await api(`/api/worlds/${worldId}/save-slots`, { method: "POST", body: selection });
      await load();
      toast(result.queued ? `${label} queued for the next start. Server was not interrupted.` : `${label} verified in this profile's SaveGames. Server remains stopped.`, "success");
      onChange?.();
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  };

  const remove = async (selection, label, shared) => {
    const scope = shared
      ? "the shared World Repository. Existing copies in server profiles will remain"
      : "this server's saved aliases. Its live world will not be touched";
    if (!confirm(`Move ${label} from ${scope} to the OS trash?`)) return;
    setBusy(true);
    try {
      await api(`/api/worlds/${worldId}/save-slots`, { method: "DELETE", body: selection });
      await load();
      toast(`${label} moved to the OS trash.`, "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  };

  return <section className="panel-inset" style={{ padding: "0.9rem 1rem", marginBottom: "1rem" }} aria-label="World save selection">
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
      <div>
        <h4 className="heading" style={{ fontSize: ".93rem", margin: 0 }}>World Repository</h4>
        <div className="subtle" style={{ fontSize: ".74rem", marginTop: 4, lineHeight: 1.5 }}>
          Import once, then choose a world for any Server profile. Original names remain aliases in the repository; only <code>{activeFilename || "Profile Name.sav"}</code> is placed in this server&apos;s SaveGames. Login, Owner ID, ports, and mods stay with the server.
        </div>
      </div>
      <button type="button" className="btn btn-ghost" disabled={busy || !isElectron} onClick={importSave}><Icon name="upload" size={15} /> {busy ? "Working…" : "Import world"}</button>
    </div>
    {pending && <div className="panel-inset" role="status" style={{ padding: ".55rem .7rem", marginTop: 10, fontSize: ".74rem" }}><Icon name="clock" size={14} /> World swap queued for the next server start. The running world has not been touched.</div>}
    {selectedSaveError && <div className="panel-inset" role="alert" style={{ padding: ".55rem .7rem", borderColor: "var(--red)", fontSize: ".74rem", marginTop: 10 }}>{selectedSaveError}</div>}
    {loading ? <p className="subtle">Loading world repository…</p> : <>
      {repository.length === 0 ? <p className="subtle" style={{ margin: "12px 0" }}>No worlds in the repository yet. Import a Dragonwilds <code>.sav</code> or a single-save ZIP.</p> :
        <div style={{ display: "grid", gap: 7, marginTop: 12 }}>
          {repository.map((item) => <div key={item.id} className="panel-inset" style={{ padding: ".65rem .75rem", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <img src="/rsdw/dragonwilds-logo.png" alt="Dragonwilds" style={{ width: 62, height: 35, objectFit: "contain" }} />
            <div style={{ flex: 1, minWidth: 180 }}><strong style={{ fontSize: ".8rem", wordBreak: "break-all" }}>{item.name}</strong><div className="subtle" style={{ fontSize: ".68rem", marginTop: 3 }}>{fmtBytes(item.size)} · <WorldType item={item} /> {!item.available && <span style={{ color: "var(--red)" }}>Missing file</span>}</div></div>
            <select aria-label={`World type for ${item.name}`} title="Correct the label if automatic detection is unavailable or inaccurate" value={item.typeSource === "manual" ? item.worldType : ""} disabled={busy} onChange={(event) => setType(item.id, event.target.value)} style={{ maxWidth: 140 }}>
              <option value="">Label type…</option>{TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
            </select>
            <button type="button" className="btn btn-ghost" disabled={busy || !item.available || pending?.repositoryId === item.id} onClick={() => activate({ repositoryId: item.id }, item.name)}>{pending?.repositoryId === item.id ? "Queued" : running ? "Queue swap" : "Use for server"}</button>
            <button type="button" className="btn btn-ghost" title={`Delete ${item.name} from the shared repository`} aria-label={`Delete ${item.name} from the shared repository`} disabled={busy || pending?.repositoryId === item.id} onClick={() => remove({ repositoryId: item.id }, item.name, true)}><Icon name="trash" size={15} /></button>
          </div>)}
        </div>}
      <h5 className="heading" style={{ fontSize: ".78rem", margin: "16px 0 7px" }}>This server&apos;s world aliases</h5>
      {slots.length === 0 ? <p className="subtle" style={{ fontSize: ".72rem" }}>No profile save yet. Choose a repository world before starting to avoid a fallback Standard world.</p> :
        <div style={{ display: "grid", gap: 7 }}>
          {slots.map((slot) => <div key={slot.name} className="panel-inset" style={{ padding: ".5rem .7rem", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <img src="/rsdw/dragonwilds-mark.png" alt="" width="24" height="24" style={{ objectFit: "contain", borderRadius: 4 }} />
            <div style={{ flex: 1, minWidth: 170 }}><strong style={{ fontSize: ".8rem", wordBreak: "break-all" }}>{slot.name}</strong><div className="subtle" style={{ fontSize: ".68rem" }}>{fmtBytes(slot.size)} · {new Date(slot.modifiedAt).toLocaleString()}{slot.active && activeFilename ? ` · Live as ${activeFilename}` : ""}</div></div>
            {slot.active ? <span className="chip" style={{ background: "var(--accent)", color: "var(--accent-ink)" }}>ACTIVE WORLD</span> : <button type="button" className="btn btn-ghost" disabled={busy || pending?.slotName === slot.name} onClick={() => activate({ name: slot.name }, slot.name)}>{pending?.slotName === slot.name ? "Queued" : running ? "Queue swap" : "Use for server"}</button>}
            {!slot.active && <button type="button" className="btn btn-ghost" title={`Delete saved alias ${slot.name}`} aria-label={`Delete saved alias ${slot.name}`} disabled={busy || pending?.slotName === slot.name} onClick={() => remove({ name: slot.name }, slot.name, false)}><Icon name="trash" size={15} /></button>}
          </div>)}
        </div>}
    </>}
  </section>;
}
