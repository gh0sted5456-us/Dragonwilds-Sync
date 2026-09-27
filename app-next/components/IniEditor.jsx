"use client";
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useTranslation, Trans } from "react-i18next";
import { api, Icon, fmtTime, fmtBytes, StatusChip, toast } from "@/components/ui";

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Full-screen modal editor for DedicatedServer.ini with version history.
// Every save/restore snapshots the file, so any change can be rolled back.
// Guards unsaved edits when closing or restoring a version.
export default function IniEditor({ world, running, onClose }) {
  const { t } = useTranslation();
  const worldId = world.world_id;
  const [content, setContent] = useState("");
  const [original, setOriginal] = useState("");
  const [path, setPath] = useState("");
  const [exists, setExists] = useState(false);
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(null);   // { id, content } being viewed
  const [confirm, setConfirm] = useState(null);    // { message, onYes }
  const downOnBackdrop = useRef(false);
  const taRef = useRef(null);
  const findRef = useRef(null);
  const isElectron = typeof window !== "undefined" && window.desktop?.isElectron;

  // ---- Find / replace (Notepad-style, no dependency) ----
  const [findOpen, setFindOpen] = useState(false);
  const [showReplace, setShowReplace] = useState(false);
  const [query, setQuery] = useState("");
  const [replaceWith, setReplaceWith] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [activeMatch, setActiveMatch] = useState(0);

  const dirty = !loading && content !== original;

  // All match start-offsets for the current query, in document order.
  const matches = useMemo(() => {
    if (!query) return [];
    const hay = matchCase ? content : content.toLowerCase();
    const needle = matchCase ? query : query.toLowerCase();
    const out = [];
    for (let i = hay.indexOf(needle); i !== -1; i = hay.indexOf(needle, i + needle.length)) out.push(i);
    return out;
  }, [content, query, matchCase]);

  useEffect(() => { setActiveMatch((a) => (matches.length ? Math.min(a, matches.length - 1) : 0)); }, [matches.length]);

  // Select a match and scroll it into view. The value-truncation trick gives an
  // accurate scrollTop even with soft-wrapping, where line math alone can't.
  const revealMatch = useCallback((idx) => {
    const ta = taRef.current;
    if (!ta || !matches.length) return;
    const start = matches[idx];
    const end = start + query.length;
    const full = ta.value;
    ta.value = full.slice(0, start);
    const upto = ta.scrollHeight;
    ta.value = full;
    ta.scrollTop = Math.max(0, upto - ta.clientHeight / 2);
    ta.focus();
    ta.setSelectionRange(start, end);
  }, [matches, query]);

  const gotoMatch = useCallback((dir) => {
    if (!matches.length) return;
    setActiveMatch((a) => {
      const next = (a + dir + matches.length) % matches.length;
      requestAnimationFrame(() => revealMatch(next));
      return next;
    });
  }, [matches, revealMatch]);

  const openFind = useCallback((withReplace) => {
    setFindOpen(true);
    if (withReplace) setShowReplace(true);
    // Seed the query from the current selection, if any.
    const ta = taRef.current;
    if (ta && ta.selectionStart != null && ta.selectionEnd > ta.selectionStart) {
      setQuery(ta.value.slice(ta.selectionStart, ta.selectionEnd));
    }
    requestAnimationFrame(() => { findRef.current?.focus(); findRef.current?.select(); });
  }, []);

  const closeFind = useCallback(() => { setFindOpen(false); taRef.current?.focus(); }, []);

  const replaceOne = () => {
    if (!matches.length) return;
    const start = matches[activeMatch];
    setContent(content.slice(0, start) + replaceWith + content.slice(start + query.length));
  };
  const replaceAll = () => {
    if (!query) return;
    const re = new RegExp(escapeRe(query), matchCase ? "g" : "gi");
    const next = content.replace(re, () => replaceWith);
    if (next !== content) { setContent(next); toast(t("ini.replacedAll", { count: matches.length }), "success"); }
  };

  const openExternal = () => {
    if (!path) return;
    if (isElectron) window.desktop.openPath(path);
    else toast(t("ini.openExternalDesktop"));
  };

  const loadVersions = useCallback(async () => {
    try { const r = await api(`/api/worlds/${worldId}/ini/versions`); setVersions(r.versions || []); }
    catch { /* history is best-effort */ }
  }, [worldId]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api(`/api/worlds/${worldId}/ini`);
      setContent(r.content || "");
      setOriginal(r.content || "");
      setPath(r.path || "");
      setExists(r.exists);
    } catch (e) { toast(e.message, "error"); }
    finally { setLoading(false); }
  }, [worldId]);

  useEffect(() => { load(); loadVersions(); }, [load, loadVersions]);

  // Run `action` immediately, or ask to discard first when there are unsaved edits.
  const guard = useCallback((action) => {
    if (dirty) setConfirm({ message: t("ini.discardConfirm"), onYes: () => { setConfirm(null); action(); } });
    else action();
  }, [dirty]);

  const requestClose = useCallback(() => guard(onClose), [guard, onClose]);

  // Keyboard: Ctrl/Cmd+F find, Ctrl/Cmd+H replace, Esc closes find → preview → confirm → editor.
  useEffect(() => {
    const h = (e) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && (e.key === "f" || e.key === "F")) { e.preventDefault(); openFind(false); return; }
      if (mod && (e.key === "h" || e.key === "H")) { e.preventDefault(); openFind(true); return; }
      if (e.key === "Escape") {
        if (findOpen) closeFind();
        else if (preview) setPreview(null);
        else if (confirm) setConfirm(null);
        else requestClose();
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [requestClose, preview, confirm, findOpen, openFind, closeFind]);

  const save = async () => {
    setSaving(true);
    try {
      await api(`/api/worlds/${worldId}/ini`, { method: "POST", body: { content } });
      setOriginal(content);
      toast(running ? t("ini.savedRestart") : t("ini.saved"), "success");
      loadVersions();
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  };

  const viewVersion = async (vid) => {
    try { const r = await api(`/api/worlds/${worldId}/ini/versions/${vid}`); setPreview({ id: vid, content: r.version.content }); }
    catch (e) { toast(e.message, "error"); }
  };

  const doRestore = async (vid) => {
    try {
      const r = await api(`/api/worlds/${worldId}/ini/versions/${vid}/restore`, { method: "POST" });
      setContent(r.content); setOriginal(r.content); setPreview(null);
      toast(running ? t("ini.restoredRestart") : t("ini.restored"), "success");
      loadVersions();
    } catch (e) { toast(e.message, "error"); }
  };
  // Restoring replaces the editor content, so guard unsaved edits first.
  const requestRestore = (vid) => guard(() => doRestore(vid));

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.62)", display: "grid", placeItems: "center", zIndex: 60, padding: 0 }}
      onMouseDown={(e) => { downOnBackdrop.current = e.target === e.currentTarget; }}
      onClick={(e) => { if (e.target === e.currentTarget && downOnBackdrop.current) requestClose(); }}
    >
      <div className="panel" style={{ width: "100vw", height: "100vh", maxWidth: "none", borderRadius: 0, display: "flex", flexDirection: "column", padding: "1.1rem", gap: "0.9rem" }}>
        {/* Header: world name / status / path */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.7rem", flexWrap: "wrap" }}>
          <Icon name="settings" size={18} />
          <div style={{ fontWeight: 800, fontSize: "1.05rem" }}>{world.display_name}</div>
          <StatusChip status={world.status} running={running} />
          <div className="subtle" style={{ fontWeight: 700, fontSize: "0.72rem", flex: 1, minWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {path}
          </div>
          <button className="btn btn-ghost" onClick={() => openFind(false)} title={t("ini.findTip")}><Icon name="grid" size={14} /> {t("ini.find")}</button>
          {exists && <button className="btn btn-ghost" onClick={openExternal} title={t("ini.openExternalTip")}><Icon name="upload" size={14} /> {t("ini.openExternal")}</button>}
          {dirty && <span className="chip" style={{ background: "var(--yellow)", color: "#1e1f22" }}>{t("ini.unsaved")}</span>}
          <button className="btn btn-ghost" onClick={requestClose}><Icon name="x" size={14} /> {t("ini.close")}</button>
        </div>

        {running && (
          <div className="panel-inset" style={{ padding: "0.5rem 0.9rem", borderLeft: "3px solid var(--yellow)", fontSize: "0.76rem", fontWeight: 700 }}>
            <Trans i18nKey="ini.runningNotice" components={{ b: <b /> }} />
          </div>
        )}
        {!exists && !loading && (
          <div className="subtle" style={{ fontWeight: 700, fontSize: "0.78rem" }}>{t("ini.noFileNotice")}</div>
        )}

        {/* Body: editor + version history */}
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 280px", gap: "1rem", flex: 1, minHeight: 0 }}>
          <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
            {/* Find / replace bar */}
            {findOpen && (
              <div className="panel-inset" style={{ padding: "0.5rem 0.6rem", marginBottom: "0.6rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", flexWrap: "wrap" }}>
                  <input
                    ref={findRef} className="input" value={query} onChange={(e) => setQuery(e.target.value)}
                    placeholder={t("ini.findPlaceholder")} style={{ flex: 1, minWidth: 140, padding: "0.35rem 0.6rem" }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") { e.preventDefault(); gotoMatch(e.shiftKey ? -1 : 1); }
                      else if (e.key === "Escape") { e.preventDefault(); closeFind(); }
                    }} />
                  <span className="subtle" style={{ fontWeight: 700, fontSize: "0.72rem", minWidth: 54, textAlign: "center" }}>
                    {query ? `${matches.length ? activeMatch + 1 : 0}/${matches.length}` : "—"}
                  </span>
                  <button className="btn btn-ghost" style={{ padding: "0.3rem 0.5rem" }} disabled={!matches.length} onClick={() => gotoMatch(-1)} title={t("ini.findPrev")}><Icon name="back" size={14} /></button>
                  <button className="btn btn-ghost" style={{ padding: "0.3rem 0.5rem" }} disabled={!matches.length} onClick={() => gotoMatch(1)} title={t("ini.findNext")}>▼</button>
                  <button className={`btn ${matchCase ? "btn-primary" : "btn-ghost"}`} style={{ padding: "0.3rem 0.5rem", fontSize: "0.72rem" }} onClick={() => setMatchCase((v) => !v)} title={t("ini.matchCase")}>Aa</button>
                  <button className="btn btn-ghost" style={{ padding: "0.3rem 0.5rem", fontSize: "0.72rem" }} onClick={() => setShowReplace((v) => !v)}>{showReplace ? t("ini.hideReplace") : t("ini.replace")}</button>
                  <button className="btn btn-ghost" style={{ padding: "0.3rem 0.5rem" }} onClick={closeFind} title={t("ini.close")}><Icon name="x" size={14} /></button>
                </div>
                {showReplace && (
                  <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", flexWrap: "wrap" }}>
                    <input className="input" value={replaceWith} onChange={(e) => setReplaceWith(e.target.value)}
                      placeholder={t("ini.replacePlaceholder")} style={{ flex: 1, minWidth: 140, padding: "0.35rem 0.6rem" }} />
                    <button className="btn btn-ghost" style={{ padding: "0.3rem 0.6rem", fontSize: "0.74rem" }} disabled={!matches.length} onClick={replaceOne}>{t("ini.replaceOne")}</button>
                    <button className="btn btn-ghost" style={{ padding: "0.3rem 0.6rem", fontSize: "0.74rem" }} disabled={!matches.length} onClick={replaceAll}>{t("ini.replaceAll")}</button>
                  </div>
                )}
              </div>
            )}
            <textarea
              ref={taRef}
              className="input"
              spellCheck={false}
              value={loading ? t("ini.loading") : content}
              onChange={(e) => setContent(e.target.value)}
              disabled={loading}
              wrap="soft"
              style={{ flex: 1, width: "100%", fontFamily: "var(--mono, ui-monospace, monospace)", fontSize: "0.8rem", lineHeight: 1.5, whiteSpace: "pre-wrap", overflowWrap: "anywhere", wordBreak: "break-word", overflowX: "hidden", overflowY: "auto", resize: "none" }}
            />
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "0.7rem" }}>
              <button className="btn btn-ghost" onClick={() => setContent(original)} disabled={!dirty || saving}>
                <Icon name="restart" size={14} /> {t("ini.revert")}
              </button>
              <button className="btn btn-primary" onClick={save} disabled={!dirty || saving || loading}>
                <Icon name="download" /> {saving ? t("ini.saving") : t("ini.save")}
              </button>
            </div>
          </div>

          <div className="panel-inset" style={{ padding: "0.8rem", display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div className="heading" style={{ fontSize: "0.9rem", marginBottom: "0.6rem" }}>{t("ini.versionHistory")}</div>
            {versions.length === 0 ? (
              <p className="subtle" style={{ fontWeight: 700, fontSize: "0.74rem" }}>{t("ini.noVersions")}</p>
            ) : (
              <div style={{ display: "grid", gap: "0.4rem", overflowY: "auto" }}>
                {versions.map((v) => (
                  <div key={v.id} style={{ padding: "0.45rem 0.55rem", border: "1px solid var(--line)", borderRadius: 8 }}>
                    <div style={{ fontWeight: 800, fontSize: "0.74rem" }}>{v.note || t("ini.snapshot")}</div>
                    <div className="subtle" style={{ fontSize: "0.68rem", fontWeight: 700 }}>{fmtTime(v.created_at)} · {fmtBytes(v.size)}</div>
                    <div style={{ display: "flex", gap: "0.35rem", marginTop: "0.35rem" }}>
                      <button className="btn btn-ghost" style={{ padding: "0.2rem 0.45rem", fontSize: "0.7rem" }} onClick={() => viewVersion(v.id)}>{t("ini.view")}</button>
                      <button className="btn btn-amber" style={{ padding: "0.2rem 0.45rem", fontSize: "0.7rem" }} onClick={() => requestRestore(v.id)}>{t("ini.restore")}</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* View a historical version */}
      {preview && (
        <div onMouseDown={(e) => { if (e.target === e.currentTarget) setPreview(null); }}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "grid", placeItems: "center", zIndex: 70, padding: "2rem" }}>
          <div className="panel" style={{ width: "min(820px, 96vw)", maxHeight: "86vh", display: "flex", flexDirection: "column", padding: "1.1rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.7rem" }}>
              <div className="heading" style={{ fontSize: "1rem" }}>{t("ini.versionNum", { id: preview.id })}</div>
              <button className="btn btn-ghost" onClick={() => setPreview(null)}><Icon name="x" size={14} /> {t("ini.close")}</button>
            </div>
            <textarea className="input" readOnly value={preview.content} wrap="soft"
              style={{ flex: 1, minHeight: 360, fontFamily: "var(--mono, ui-monospace, monospace)", fontSize: "0.78rem", whiteSpace: "pre-wrap", overflowWrap: "anywhere", wordBreak: "break-word", overflowX: "hidden" }} />
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "0.7rem" }}>
              <button className="btn btn-ghost" onClick={() => guard(() => { setContent(preview.content); setPreview(null); toast(t("ini.loadedIntoEditor"), "success"); })}>{t("ini.loadIntoEditor")}</button>
              <button className="btn btn-amber" onClick={() => requestRestore(preview.id)}>{t("ini.restoreThis")}</button>
            </div>
          </div>
        </div>
      )}

      {/* Discard-changes confirmation */}
      {confirm && (
        <div onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirm(null); }}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "grid", placeItems: "center", zIndex: 80, padding: "2rem" }}>
          <div className="panel" style={{ width: "min(420px, 94vw)", padding: "1.2rem" }}>
            <div className="heading" style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>{t("ini.unsavedTitle")}</div>
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.84rem", marginTop: 0 }}>{confirm.message}</p>
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button className="btn btn-ghost" onClick={() => setConfirm(null)}>{t("ini.keepEditing")}</button>
              <button className="btn btn-danger" onClick={confirm.onYes}>{t("ini.discardChanges")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
