"use client";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "@/components/ThemeProvider";
import { api, Icon, toast } from "@/components/ui";
const { DEFAULT_APPEARANCE } = require("@/lib/appearance-preferences");

export default function AppearancePanel() {
  const { appearance, appearanceError, previewAppearance, saveAppearance } = useTheme();
  const [draft, setDraft] = useState(appearance);
  const [gallery, setGallery] = useState({ backgrounds: [], directory: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef(null), mounted = useRef(false), controller = useRef(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; controller.current?.abort(); previewAppearance(null); }; }, [previewAppearance]);
  useEffect(() => { setDraft(appearance); }, [appearance]);
  async function refresh() {
    controller.current?.abort();
    const abort = new AbortController(); controller.current = abort;
    const timer = setTimeout(() => abort.abort(), 10000);
    setBusy(true);
    try { const result = await api("/api/appearance?catalog=1", { signal: abort.signal }); if (mounted.current && !abort.signal.aborted) { setGallery(result); setError(result.warning || ""); } }
    catch (failure) { if (mounted.current && controller.current === abort) setError(failure.name === "AbortError" ? "Reading backgrounds timed out. Try Refresh." : failure.message); }
    finally { clearTimeout(timer); if (mounted.current && controller.current === abort) setBusy(false); }
  }
  useEffect(() => { void refresh(); }, []);
  const change = (patch) => { const next = { ...draft, ...patch }; setDraft(next); previewAppearance(next); };
  const changed = JSON.stringify(draft) !== JSON.stringify(appearance);
  async function save() {
    setBusy(true); setError("");
    try { await saveAppearance(draft); if (mounted.current) toast("Workspace appearance saved in application data.", "success"); }
    catch (failure) { if (mounted.current) setError(failure.message); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function upload(file) {
    if (!file) return;
    if (file.size > 12 * 1024 * 1024) { setError("Choose a still image no larger than 12 MiB."); return; }
    setBusy(true); setError("");
    const abort = new AbortController(); controller.current = abort;
    const timer = setTimeout(() => abort.abort(), 20000);
    try {
      const response = await fetch("/api/appearance/backgrounds", { method: "POST", body: file, headers: { "content-type": "application/octet-stream", "x-rsdw-image-name": encodeURIComponent(file.name) }, signal: abort.signal });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Background import failed.");
      if (mounted.current && !abort.signal.aborted) { setGallery((old) => ({ ...old, backgrounds: result.backgrounds })); change({ background: result.asset.id }); toast("Image copied into Sync's backgrounds folder. Save to keep this selection.", "success"); }
    } catch (failure) { if (mounted.current) setError(failure.name === "AbortError" ? "Background import timed out. Refresh the gallery before retrying." : failure.message); }
    finally { clearTimeout(timer); if (mounted.current) setBusy(false); if (fileInput.current) fileInput.current.value = ""; }
  }
  return <section className="panel appearance-panel" aria-label="Backgrounds and glass surfaces">
    <header className="appearance-heading"><div><span className="eyebrow">YOUR ATMOSPHERE</span><h3 className="heading">Backgrounds &amp; black glass</h3><p className="subtle">Helpy-inspired surfaces over a quiet landscape. Preview here, then save for the whole workspace.</p></div><span className="appearance-storage-badge"><Icon name="folder" size={14} /> AppData owned</span></header>
    {(error || appearanceError) && <p role="alert" className="appearance-error">{error || appearanceError}</p>}
    <div className="appearance-gallery" role="group" aria-label="Workspace background">
      <button type="button" className="appearance-scene appearance-scene-none" aria-pressed={draft.background === "none"} disabled={busy} onClick={() => change({ background: "none" })}><span className="appearance-scene-image"><Icon name="x" size={24} /></span><span>No image</span></button>
      {gallery.backgrounds.map((asset) => <button key={asset.id} type="button" className="appearance-scene" aria-pressed={draft.background === asset.id} disabled={busy} onClick={() => change({ background: asset.id })}><img className="appearance-scene-image" src={asset.url} alt="" loading="lazy" decoding="async" /><span>{asset.name}</span>{draft.background === asset.id && <span className="appearance-selected"><Icon name="check" size={14} /></span>}</button>)}
    </div>
    <div className="appearance-controls">
      <label htmlFor="background-opacity"><span>Background visibility <strong>{Math.round(draft.backgroundOpacity * 100)}%</strong></span><input id="background-opacity" type="range" min="0" max="60" step="1" value={Math.round(draft.backgroundOpacity * 100)} disabled={busy} onChange={(event) => change({ backgroundOpacity: Number(event.target.value) / 100 })} /></label>
      <label htmlFor="surface-opacity"><span>Glass surface opacity <strong>{Math.round(draft.surfaceOpacity * 100)}%</strong></span><input id="surface-opacity" type="range" min="72" max="100" step="1" value={Math.round(draft.surfaceOpacity * 100)} disabled={busy} onChange={(event) => change({ surfaceOpacity: Number(event.target.value) / 100 })} /></label>
      <label htmlFor="background-fit"><span>Image fit</span><select id="background-fit" value={draft.fit} disabled={busy} onChange={(event) => change({ fit: event.target.value })}><option value="cover">Fill workspace</option><option value="contain">Fit entire image</option></select></label>
    </div>
    <div className="appearance-storage"><div><strong>Stored with Dragonwilds Sync</strong><code>{gallery.directory || "Loading application data folder…"}</code><p>Import a PNG, JPEG or WebP, or add still images to this folder and refresh. Originals stay where they are. No game folders are changed.</p></div><div className="appearance-storage-actions"><input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label="Import background image" onChange={(event) => void upload(event.target.files?.[0])} /><button type="button" className="btn btn-ghost" disabled={busy} onClick={() => fileInput.current?.click()}><Icon name="upload" size={15} /> Import image</button><button type="button" className="btn btn-ghost" disabled={busy} onClick={refresh}><Icon name="refresh" size={15} /> Refresh</button><button type="button" className="btn btn-ghost" disabled={!gallery.directory || typeof window === "undefined" || !window.desktop?.openPath || busy} onClick={() => window.desktop.openPath(gallery.directory).catch((failure) => setError(failure.message))}><Icon name="folder" size={15} /> Open folder</button></div></div>
    <footer className="appearance-footer"><span className="subtle">{busy ? "Working…" : changed ? "Previewing unsaved changes" : "Saved appearance"}</span><div><button className="btn btn-ghost" disabled={busy} onClick={() => change(DEFAULT_APPEARANCE)}>Restore default look</button><button className="btn btn-ghost" disabled={!changed || busy} onClick={() => { setDraft(appearance); previewAppearance(null); }}>Discard preview</button><button className="btn btn-primary" disabled={!changed || busy} onClick={save}><Icon name="check" size={15} /> Save background</button></div></footer>
    <p className="appearance-note subtle">Still images only. Solid window resizing is retained; the glass effect is inside the app. Reduced-transparency preferences use solid surfaces.</p>
  </section>;
}
