"use client";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, Icon, fmtBytes, fmtTime, toast } from "@/components/ui";

export default function BackupsPanel({ worldId, backups, running, onChange }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [loc, setLoc] = useState(null);
  const [slots, setSlots] = useState([]);
  const isElectron = typeof window !== "undefined" && window.desktop?.isElectron;

  useEffect(() => {
    api(`/api/settings/backup-dir?worldId=${encodeURIComponent(worldId)}`).then((r) => setLoc(r.backup)).catch(() => {});
    api(`/api/worlds/${worldId}/save-slots`).then((r) => setSlots(r.slots || [])).catch(() => {});
  }, [worldId]);

  const openFolder = () => { if (isElectron && loc?.worldPath) window.desktop.openPath(loc.worldPath); };

  const create = async () => {
    setBusy(true);
    try {
      await api(`/api/worlds/${worldId}/backups`, { method: "POST" });
      toast(t("backups.created"), "success");
      onChange();
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };

  const restore = async (backupId) => {
    if (running) return toast(t("backups.stopBeforeRestore"), "error");
    if (!confirm(t("backups.confirmRestore"))) return;
    setBusy(true);
    try {
      await api(`/api/worlds/${worldId}/backups/restore`, { method: "POST", body: { backupId } });
      toast(t("backups.restored"), "success");
      onChange();
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };

  const importSave = async () => {
    if (!isElectron) return toast(t("backups.importPickerDesktop"));
    const savePath = await window.desktop.pickWorldSave();
    if (!savePath) return;
    if (!confirm(`Replace this server's active world with the selected save? RSDW will ${running ? "save and stop the running server, " : ""}create a safety backup, verify the replacement, and start the server with it.`)) return;
    setImporting(true);
    try {
      const { check } = await api(`/api/worlds/${worldId}/import`, { method: "POST", body: { savePath } });
      setSlots(check.slots || []);
      toast(`World save slot ${check.activeSave} was verified and the server ${check.restarted ? "restarted" : "started"} with it. Login and profile settings were retained.`, "success");
      onChange();
    } catch (e) { toast(e.message, "error"); }
    finally { setImporting(false); }
  };

  const activateSlot = async (name) => {
    if (!confirm(`Load ${name} now? RSDW will ${running ? "save and stop the server, " : ""}back up the current world, verify that only this save is active, and start the server again.`)) return;
    setImporting(true);
    try {
      const { result } = await api(`/api/worlds/${worldId}/save-slots`, { method: "POST", body: { name, startAfter: true } });
      setSlots(result.slots || []);
      toast(`${name} is verified and the server ${result.restarted ? "restarted" : "started"} with it.`, "success");
      onChange();
    } catch (e) { toast(e.message, "error"); }
    finally { setImporting(false); }
  };

  return (
    <div>
      <div style={{ display: "flex", gap: "0.6rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        <button className="btn btn-primary" onClick={create} disabled={busy}>
          <Icon name="download" /> {busy ? t("backups.working") : t("backups.backupNow")}
        </button>
        <button className="btn btn-ghost" onClick={importSave} disabled={importing}>
          <Icon name="upload" /> {importing ? t("backups.importing") : t("backups.importSave")}
        </button>
        {isElectron && loc?.worldPath && (
          <button className="btn btn-ghost" onClick={openFolder} title={loc.worldPath}>
            <Icon name="folder" /> {t("backups.openFolder")}
          </button>
        )}
      </div>

      <div className="panel-inset" style={{ padding: "0.7rem 0.85rem", marginBottom: "1rem" }}>
        <strong style={{ fontSize: "0.82rem" }}>World replacement</strong>
        <p className="subtle" style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", lineHeight: 1.5 }}>
          Import one <code>.sav</code> file, or a ZIP containing exactly one save. Each file becomes a reusable slot. Switching saves safely stops the server, snapshots its current world, installs and verifies exactly one selected save, then restarts with passwords, Owner ID, ports, mods, and profile settings intact.
        </p>
      </div>

      {slots.length > 0 && <div style={{ marginBottom: "1.2rem" }}>
        <h4 className="heading" style={{ fontSize: ".9rem", margin: "0 0 .55rem" }}>World save slots</h4>
        <div style={{ display: "grid", gap: ".45rem" }}>
          {slots.map((slot) => <div key={slot.name} className="panel-inset" style={{ padding: ".55rem .7rem", display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name={slot.active ? "check" : "globe"} size={15} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <strong style={{ fontSize: ".8rem", wordBreak: "break-all" }}>{slot.name}</strong>
              <div className="subtle" style={{ fontSize: ".68rem" }}>{fmtBytes(slot.size)} · {new Date(slot.modifiedAt).toLocaleString()}</div>
            </div>
            {slot.active
              ? <span className="chip" style={{ background: "var(--accent)", color: "var(--accent-ink)" }}>ACTIVE</span>
              : <button className="btn btn-ghost" disabled={importing} onClick={() => activateSlot(slot.name)}>{running ? "Swap & Restart" : "Activate & Start"}</button>}
          </div>)}
        </div>
      </div>}

      {loc && (
        <p className="subtle" style={{ fontWeight: 600, fontSize: "0.72rem", margin: "-0.4rem 0 1rem", fontFamily: "var(--font-mono)", wordBreak: "break-all" }}>
          {loc.worldPath}
        </p>
      )}

      {backups.length === 0 ? (
        <p className="subtle" style={{ fontWeight: 700 }}>{t("backups.empty")}</p>
      ) : (
        <div style={{ display: "grid", gap: "0.5rem" }}>
          {backups.map((b) => (
            <div key={b.id} className="panel-inset" style={{ padding: "0.6rem 0.8rem", display: "flex", alignItems: "center", gap: "0.8rem", flexWrap: "wrap" }}>
              <Icon name="download" size={16} />
              <div style={{ flex: 1, minWidth: 160 }}>
                <div style={{ fontWeight: 800, fontSize: "0.84rem" }}>{fmtTime(b.created_at)}</div>
                <div className="subtle" style={{ fontSize: "0.72rem", fontWeight: 700 }}>{fmtBytes(b.size_bytes)} · {b.reason}</div>
              </div>
              <button className="btn btn-ghost" style={{ padding: "0.3rem 0.7rem" }} disabled={busy || running} onClick={() => restore(b.id)}>
                <Icon name="restart" size={14} /> {t("common.restore")}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
