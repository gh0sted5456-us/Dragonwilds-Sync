"use client";

import { useEffect, useState } from "react";
import Editor, { loader } from "@monaco-editor/react";

let localMonacoReady = false;
let localMonacoPromise = null;

function prepareLocalMonaco() {
  if (localMonacoReady) return Promise.resolve();
  if (!localMonacoPromise) {
    localMonacoPromise = import("monaco-editor").then((monaco) => {
      // @monaco-editor/react otherwise defaults to a CDN. Supplying the bundled
      // package keeps the editor available on dedicated/offline machines.
      loader.config({ monaco });
      localMonacoReady = true;
    });
  }
  return localMonacoPromise;
}

export default function ModCodeEditor({ file, running, saving, onSave, onClose }) {
  const [ready, setReady] = useState(localMonacoReady);
  const [value, setValue] = useState(file.content);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    let active = true;
    prepareLocalMonaco().then(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, []);

  useEffect(() => { setValue(file.content); setDirty(false); }, [file.content, file.relative]);

  const save = async (nextValue = value) => {
    const saved = await onSave(nextValue);
    if (saved) setDirty(false);
  };

  const beforeMount = (monaco) => {
    monaco.editor.defineTheme("rsdw-matte", {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "comment", foreground: "8f9a84", fontStyle: "italic" },
        { token: "string", foreground: "d4ba83" },
        { token: "keyword", foreground: "b99bd2" },
        { token: "number", foreground: "d99872" },
      ],
      colors: {
        "editor.background": "#181b1e",
        "editor.foreground": "#f3efe7",
        "editorLineNumber.foreground": "#766f64",
        "editorLineNumber.activeForeground": "#c1a56d",
        "editor.selectionBackground": "#6f5a355c",
        "editorCursor.foreground": "#d0b47a",
        "editorIndentGuide.background1": "#353a3e",
      },
    });
  };

  const mount = (editor, monaco) => {
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => save(editor.getValue()));
    editor.focus();
  };

  return <div className="code-editor-overlay" role="dialog" aria-modal="true" aria-label={`Edit ${file.name}`}>
    <section className="code-editor-window panel">
      <header className="code-editor-header">
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", gap: 7, alignItems: "center", flexWrap: "wrap" }}>
            <strong>{file.name}</strong>
            <span className="chip">{file.language.toUpperCase()}</span>
            <span className="chip" style={{ background: file.hotload ? "var(--green)" : "var(--line)" }}>HOTLOAD {file.hotload ? "YES" : "NO"}</span>
            {dirty && <span className="chip" style={{ color: "var(--yellow)" }}>UNSAVED</span>}
          </div>
          <div className="subtle" style={{ fontSize: ".68rem", overflowWrap: "anywhere", marginTop: 4 }}>{file.modName} · {file.relative}</div>
        </div>
        <button className="btn btn-ghost" onClick={onClose}>Close</button>
      </header>
      {running && !file.hotload && <div className="code-editor-warning">This mod is not hotload-capable. You may inspect it now, but the server must be stopped before saving.</div>}
      <div className="code-editor-surface">
        {ready ? <Editor
          path={`rsdw-mod://${file.relative}`}
          value={value}
          language={file.language}
          theme="rsdw-matte"
          beforeMount={beforeMount}
          onMount={mount}
          onChange={(next) => { setValue(next ?? ""); setDirty((next ?? "") !== file.content); }}
          options={{
            automaticLayout: true,
            minimap: { enabled: false },
            fontSize: 14,
            lineHeight: 22,
            padding: { top: 12, bottom: 12 },
            scrollBeyondLastLine: false,
            wordWrap: "on",
            tabSize: 2,
            renderWhitespace: "selection",
          }}
        /> : <div className="subtle" style={{ display: "grid", placeItems: "center", height: "100%" }}>Loading the bundled Monaco editor…</div>}
      </div>
      <footer className="code-editor-footer">
        <span className="subtle">Ctrl+S saves · rollback copy protects each write</span>
        <button className="btn btn-primary" disabled={saving || !dirty || (running && !file.hotload)} onClick={() => save()}>
          {saving ? "Saving…" : running && file.hotload ? "Apply hotload" : "Save file"}
        </button>
      </footer>
    </section>
  </div>;
}
