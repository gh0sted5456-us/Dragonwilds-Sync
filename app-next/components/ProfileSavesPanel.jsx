"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, fmtBytes, fmtTime, Icon, toast } from "@/components/ui";

export default function ProfileSavesPanel({ profileId }) {
  const [data, setData] = useState({ discoveries: [], managed: [], roots: [] });
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setData(await api(`/api/profile-saves?profileId=${encodeURIComponent(profileId)}`)); }
    catch (error) { toast(error.message, "error"); }
  }, [profileId]);
  useEffect(() => { load(); }, [load]);
  const managedIds = useMemo(() => new Set((data.managed || []).map((item) => item.id)), [data.managed]);

  async function scanFolder() {
    const root = await window.desktop?.pickDirectory?.();
    if (!root) return;
    setBusy(true);
    try { setData(await api("/api/profile-saves", { method: "POST", body: { action: "scan", profileId, roots: [root] } })); }
    catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function adopt(item, scope) {
    setBusy(true);
    try {
      await api("/api/profile-saves", { method: "POST", body: { action: "adopt", sourcePath: item.sourcePath, kind: item.kind, scope, profileId } });
      await load();
      toast(`${item.name} copied into the managed save vault.`, "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function assign(item, scope) {
    setBusy(true);
    try {
      await api("/api/profile-saves", { method: "POST", body: { action: "assign", id: item.id, scope, profileId } });
      await load();
      toast(scope === "agnostic" ? "Player save will follow every World profile." : "Save assigned to this World profile.", "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function extractWgs(item) {
    setBusy(true);
    try {
      const result = await api("/api/profile-saves", { method: "POST", body: { action: "extract-wgs", sourcePath: item.sourcePath } });
      await load();
      toast(`Extracted ${result.worlds} world save(s) and ${result.players} player save(s) into the managed vault.`, "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function launchConverter() {
    if (!window.desktop?.openPath) return window.open("https://github.com/RSDWArchive/RSDWSaveConverter/releases/latest", "_blank", "noopener,noreferrer");
    setBusy(true);
    try {
      const result = await api("/api/profile-saves", { method: "POST", body: { action: "converter" } });
      const launchError = await window.desktop.openPath(result.converter.path);
      if (launchError) throw new Error(launchError);
      toast(`Opened verified RSDW Save Converter ${result.converter.version}.`, "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function remove(item) {
    if (!confirm(`Remove ${item.name} from RSDW's managed save vault? The original and recovery backups are not deleted.`)) return;
    setBusy(true);
    try { await api(`/api/profile-saves?id=${encodeURIComponent(item.id)}`, { method: "DELETE" }); await load(); toast("Managed save removed.", "success"); }
    catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  return <div className="panel-inset" style={{ marginTop: 12, padding: 12 }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      <div><strong>World and player saves</strong><div className="subtle" style={{ marginTop: 4, fontSize: ".73rem" }}>Pair this World&apos;s mod list with a world save and character bundle. Game Pass saves can be extracted here; verified Steam → Game Pass imports use the separate RSDW Save Converter. Close Dragonwilds before switching or converting.</div></div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><button className="btn btn-ghost" disabled={busy} onClick={launchConverter}><Icon name="refresh" size={14} /> Steam → Game Pass converter</button><button className="btn btn-ghost" disabled={busy} onClick={scanFolder}><Icon name="folder" size={14} /> Scan another folder</button><button className="btn btn-subtle" disabled={busy} onClick={load}><Icon name="refresh" size={14} /> Rescan</button></div>
    </div>

    {!!data.managed?.length && <div style={{ display: "grid", gap: 6, marginTop: 12 }}>
      <div className="eyebrow">MANAGED SAVE VAULT</div>
      {data.managed.map((item) => <SaveRow key={item.id} item={item} busy={busy} profileId={profileId} managed onWorld={() => assign(item, "world")} onAgnostic={item.kind === "player" ? () => assign(item, "agnostic") : null} onRemove={() => remove(item)} />)}
    </div>}

    <div style={{ display: "grid", gap: 6, marginTop: 12 }}>
      <div className="eyebrow">DISCOVERED ON THIS COMPUTER</div>
      {(data.discoveries || []).map((item) => { const alreadyManaged = managedIds.has(item.id); return <SaveRow key={item.id} item={item} busy={busy} profileId={profileId} alreadyManaged={alreadyManaged} onExtract={item.extractable ? () => extractWgs(item) : null} onWorld={item.manageable && !alreadyManaged ? () => adopt(item, "world") : null} onAgnostic={item.manageable && item.kind === "player" && !alreadyManaged ? () => adopt(item, "agnostic") : null} />; })}
      {!data.discoveries?.length && <div className="subtle" style={{ fontSize: ".74rem" }}>No saves found in the configured path. Scan another folder or launch Dragonwilds once to create its save directories.</div>}
    </div>
  </div>;
}

function SaveRow({ item, busy, profileId, managed = false, alreadyManaged = false, onWorld, onAgnostic, onExtract, onRemove }) {
  const assignment = item.assignment;
  const activeHere = assignment?.scope === "world" && assignment.profileId === profileId;
  const activeElsewhere = assignment?.scope === "world" && assignment.profileId && !activeHere;
  return <div className="panel" style={{ padding: ".7rem .8rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
    <div style={{ minWidth: 0, flex: 1 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}><strong style={{ fontSize: ".8rem" }}>{item.name}</strong><span className="chip">{item.kind === "world" ? "WORLD .SAV" : item.kind === "player" ? "PLAYER BUNDLE" : "GAME PASS WGS"}</span>{assignment?.scope === "agnostic" && <span className="chip" style={{ background: "var(--green)" }}>ALL WORLDS</span>}{activeHere && <span className="chip" style={{ background: "var(--accent)" }}>THIS WORLD</span>}{activeElsewhere && <span className="chip">ANOTHER WORLD</span>}</div>
      <div className="subtle" style={{ fontSize: ".67rem", marginTop: 4, overflowWrap: "anywhere" }}>{item.originalPath || item.sourcePath}</div>
      <div className="subtle" style={{ fontSize: ".65rem", marginTop: 2 }}>{item.files || 1} file(s) · {fmtBytes(item.size || 0)} · {fmtTime(item.modifiedAt)}{item.note ? ` · ${item.note}` : ""}</div>
    </div>
    <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
      {alreadyManaged && <span className="chip">IN VAULT</span>}
      {onExtract && <button className="btn btn-primary" disabled={busy} onClick={onExtract}>Extract Game Pass saves</button>}
      {onAgnostic && <button className="btn btn-subtle" disabled={busy || assignment?.scope === "agnostic"} onClick={onAgnostic}>Use for all Worlds</button>}
      {onWorld && <button className="btn btn-primary" disabled={busy || (managed && activeHere)} onClick={onWorld}>Use for this World</button>}
      {onRemove && <button className="btn btn-ghost" disabled={busy} onClick={onRemove}><Icon name="trash" size={14} /></button>}
    </div>
  </div>;
}
