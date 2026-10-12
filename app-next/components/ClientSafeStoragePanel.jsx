"use client";
import { useEffect, useState } from "react";
import { api, toast } from "@/components/ui";

export default function ClientSafeStoragePanel({ profileId, install, localWorld }) {
  const [storage, setStorage] = useState(null);
  const [error, setError] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    const response = await api(`/api/profiles/${profileId}/safe-storage`);
    setStorage(response.storage);
    setReviewed(false);
    setError("");
  };
  useEffect(() => {
    if (!install) { setStorage(null); return; }
    reload().catch((failure) => setError(failure.message));
  }, [profileId, install]);

  const action = async (kind) => {
    setBusy(true);
    try {
      if (kind === "restore" && !window.confirm("Restore the archived native mods into this game install? The currently active managed profile will be deactivated. Close Dragonwilds first.")) return;
      const response = await api(`/api/profiles/${profileId}/safe-storage`, { method: "POST", body: { action: kind, fingerprint: storage?.fingerprint } });
      setStorage(response.storage);
      setReviewed(false);
      setError("");
      toast(kind === "archive" ? "Original mods archived and verified. Profile activation is ready." : kind === "restore" ? "Original game files restored." : "Safe Storage recovered.", "success");
    } catch (failure) { setError(failure.message); toast(failure.message, "error"); }
    finally { setBusy(false); }
  };

  return <div className="panel-inset" style={{ marginTop: 12, padding: 12, display: "grid", gap: 8 }}>
    <strong>Safe Storage · native mods</strong>
    <div className="subtle" style={{ fontSize: ".74rem" }}>Before the launcher manages this installation, review its existing mod files. Confirming copies and verifies them into Safe Storage, then removes only the listed originals. Shared UE4SS loader binaries stay in place so the game can still start. Nothing is archived automatically. You can restore the mods while the game is closed.</div>
    {!install && <div className="subtle">Choose a game folder first.</div>}
    {error && <div role="alert" style={{ color: "var(--yellow)", fontSize: ".76rem" }}>{error}</div>}
    {storage && <>
      <div className="subtle" style={{ fontSize: ".72rem", overflowWrap: "anywhere" }}>{storage.install}</div>
      {storage.pending?.length > 0 && <><div style={{ color: "var(--yellow)", fontSize: ".76rem" }}>Interrupted operation: {storage.pending.join(", ")}. Recover before continuing.</div><button className="btn btn-ghost" disabled={busy} onClick={() => action("recover")}>Recover interrupted operation</button></>}
      {storage.unsupported?.length > 0 && <div style={{ color: "var(--yellow)", fontSize: ".76rem" }}>Linked or special files need manual review: {storage.unsupported.join(", ")}</div>}
      {storage.entries?.length > 0 && <>
        <div><b>{storage.entries.length} unmanaged file(s) found</b><div className="subtle" style={{ fontSize: ".72rem" }}>Review this exact inventory before archiving. Files added or changed afterward require a fresh review.</div></div>
        <div style={{ maxHeight: 180, overflow: "auto", border: "1px solid var(--line)", borderRadius: 8, padding: 8 }}>
          {storage.entries.map((entry) => <div key={entry.relative} style={{ fontSize: ".72rem", overflowWrap: "anywhere", padding: "2px 0" }}>{entry.relative} · {formatBytes(entry.size)}</div>)}
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: ".76rem" }}><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />I reviewed these files and want a verified, restorable archive.</label>
        <button className="btn btn-primary" disabled={busy || !reviewed || !!storage.pending?.length || !!storage.unsupported?.length} onClick={() => action("archive")}>{busy ? "Working…" : "Archive originals & prepare profile"}</button>
      </>}
      {storage.ready && <div style={{ color: "var(--green)", fontSize: ".76rem" }}>Ready for managed profile activation.{localWorld ? " This World gets its own mod snapshot." : " Connected World downloads stay in this profile."}</div>}
      {storage.archives?.filter((item) => !item.restoredAt).map((item) => <div key={item.id} className="subtle" style={{ fontSize: ".72rem" }}>Restorable archive {item.id} · {item.files?.length || 0} files</div>)}
      {storage.archives?.some((item) => !item.restoredAt) && <button className="btn btn-ghost" disabled={busy || !!storage.pending?.length} onClick={() => action("restore")}>Restore original native mods</button>}
      <button className="btn btn-ghost" disabled={busy} onClick={() => reload().catch((failure) => setError(failure.message))}>Refresh inventory</button>
    </>}
  </div>;
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  return bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
