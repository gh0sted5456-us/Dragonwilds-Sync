"use client";
import { useState } from "react";
import { api, Icon, toast } from "@/components/ui";
import AppOverlay from "@/components/AppOverlay";

export default function RuntimeCleanControls({ endpoint, component, platform, disabled }) {
  const [preview, setPreview] = useState(null), [busy, setBusy] = useState(false), [confirmed, setConfirmed] = useState(false);
  async function review() {
    setBusy(true); setConfirmed(false);
    try { setPreview((await api(endpoint, { method: "POST", body: { platform, component, action: "preview-clean" } })).preview); }
    catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  async function submit(action) {
    setBusy(true);
    try {
      const result = await api(endpoint, { method: "POST", body: { platform, component, action, fingerprint: preview.fingerprint, recoveryId: preview.recovery?.id } });
      window.dispatchEvent(new Event("rsdw-jobs-ping"));
      toast(result.alreadyRunning ? "A loader operation is already running." : "Runtime operation queued. Follow backup and file progress in Downloads.", "success");
      setPreview(null);
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  const canRestore = ["cleaned", "pending", "restoring", "needs-recovery"].includes(preview?.recovery?.state);
  return <>
    <button className="btn btn-ghost" style={{ marginTop: 8, width: "100%", whiteSpace: "normal" }} disabled={disabled || busy} onClick={review}><Icon name="refresh" size={14} /> Clean / restore runtime</button>
    {preview && <AppOverlay label="Review runtime cleanup" onClose={() => { if (!busy) setPreview(null); }} dismissible={!busy}>
      <section className="panel" style={{ width: "min(820px, calc(100vw - 32px))", maxHeight: "calc(100dvh - 90px)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <header style={{ padding: "1.2rem", borderBottom: "1px solid var(--line)" }}><h2 className="heading" style={{ margin: 0 }}>Review runtime cleanup</h2></header>
        <div style={{ padding: "1.2rem", overflowY: "auto", minHeight: 0 }}>
          <p>Clear <strong>{preview.files.toLocaleString()} files</strong> ({(preview.bytes / 1024 / 1024).toFixed(1)} MiB) outside this loader’s direct <code>mods</code> folder. Folder structure stays in place.</p>
          <p style={{ color: "var(--red)" }}>This also clears unknown runtime files, settings, plug-ins, and logs outside Mods. It is broader than a normal ZIP update. Reinstall the runtime ZIP afterward.</p>
          <p>The preserved Mods tree is never scanned or deleted. Cleaning UE4SS keeps RuneSchema inside UE4SS/Mods; clean RuneSchema separately if needed. Sibling bootstrap DLLs, including server <code>version.dll</code>, are untouched. No server restart is requested.</p>
          <div style={{ display: "grid", gap: 8 }}>{preview.targets.map((target) => <div key={target.id} className="panel-inset" style={{ padding: ".7rem" }}><strong>{target.id === "installation" ? "Live runtime" : "Stored package runtime"}</strong><code style={{ display: "block", fontSize: ".7rem", overflowWrap: "anywhere" }}>{target.root}</code><span className="subtle">Keep: {target.root}/Mods</span></div>)}</div>
          <details style={{ margin: "12px 0" }}><summary>Files to clear ({preview.files})</summary><div className="console" style={{ height: 190 }}>{preview.entries.slice(0, 100).map((entry) => <div className="ln" key={entry.target + entry.relative}>{entry.target}/{entry.relative}</div>)}{preview.files > 100 && <div className="ln subtle">First 100 shown; all files are inventoried in the recovery receipt.</div>}</div></details>
          <p className="subtle">A verified recovery copy is made before anything is removed. Restore is blocked if a newer ZIP or runtime edits would be overwritten.</p>
          {canRestore && <div className="panel-inset" style={{ padding: ".8rem" }}><strong>{preview.recovery.state === "cleaned" ? "Previous cleanup backup" : "Interrupted cleanup — restore required"}</strong><code style={{ display: "block", fontSize: ".7rem", overflowWrap: "anywhere" }}>{preview.recovery.backup}</code><button className="btn btn-ghost" style={{ marginTop: 8 }} disabled={busy} onClick={() => submit("restore-clean")}>Restore previous cleanup</button></div>}
          <label style={{ display: "flex", gap: 8, marginTop: 14, alignItems: "start" }}><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /> I reviewed these paths and want to clear all files outside Mods, keeping the folder structure and a recovery backup.</label>
        </div>
        <footer style={{ padding: "1rem 1.2rem", display: "flex", justifyContent: "flex-end", gap: 8, borderTop: "1px solid var(--line)" }}><button className="btn btn-ghost" disabled={busy} onClick={() => setPreview(null)}>Cancel</button><button className="btn btn-primary" disabled={!confirmed || busy || !preview.files || ["pending", "restoring", "needs-recovery"].includes(preview.recovery?.state)} onClick={() => submit("clean")}>Back up and clean</button></footer>
      </section>
    </AppOverlay>}
  </>;
}
