"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, Icon } from "@/components/ui";
import useAdaptivePolling from "@/components/useAdaptivePolling";
import useLogExport from "@/components/useLogExport";

export default function NativeLogPanel({ kind, id, channel: fixedChannel }) {
  const [selected, setSelected] = useState("eos");
  const channel = fixedChannel || selected;
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState(true);
  const controller = useRef(null);
  const mounted = useRef(false);
  const box = useRef(null);
  const { exportLogs, exporting } = useLogExport();
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; controller.current?.abort(); }; }, []);
  const load = useCallback(async () => {
    if (document.visibilityState === "hidden") return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; abort.abort(); }, 15000);
    setLoading(true);
    try {
      const scope = kind === "server" ? "worlds" : "profiles";
      const result = await api(`/api/${scope}/${encodeURIComponent(id)}/logs/files?channel=${channel}`, { signal: abort.signal });
      if (mounted.current && controller.current === abort) { setData(result); setError(""); }
    } catch (failure) {
      if (mounted.current && controller.current === abort && (failure.name !== "AbortError" || timedOut)) setError(timedOut ? "Reading logs timed out. Try Refresh." : failure.message);
    } finally {
      clearTimeout(timer);
      if (mounted.current && controller.current === abort) setLoading(false);
    }
  }, [kind, id, channel]);
  useEffect(() => { setData(null); setError(""); void load(); return () => controller.current?.abort(); }, [load]);
  useAdaptivePolling(load, { visibleMs: 5000, hiddenMs: 60000, enabled: live, immediate: false });
  useEffect(() => { if (live && box.current) box.current.scrollTop = box.current.scrollHeight; }, [data, live]);
  return <section aria-label="Native game diagnostics">
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10, alignItems: "center" }}>
      {!fixedChannel && <div role="group" aria-label="Native log channel" style={{ display: "flex", gap: 4 }}>{[["eos", "EOS"], ["native", "Game"], ["ue4ss", "UE4SS"]].map(([value, label]) => <button key={value} className={`btn ${channel === value ? "btn-primary" : "btn-ghost"}`} aria-pressed={channel === value} onClick={() => setSelected(value)}>{label}</button>)}</div>}
      <button className="btn btn-ghost" onClick={load} disabled={loading}><Icon name="refresh" /> {loading ? "Reading…" : "Refresh"}</button>
      <button className={`btn ${live ? "btn-primary" : "btn-ghost"}`} onClick={() => setLive((value) => !value)}>{live ? "Live · 5s" : "Paused"}</button>
      <button className="btn btn-ghost" disabled={exporting} onClick={() => exportLogs(kind, id)}><Icon name="download" /> {exporting ? "Preparing…" : "Export Logs"}</button>
    </div>
    <p className="subtle" role="status" style={{ margin: "0 0 8px", fontSize: ".76rem" }}>{data?.note || (channel === "eos" ? "EOS messages are read from the game's native log—not from a separate SDK session." : "Logs from this computer's mapped installation.")}{data?.truncated && " Showing only the recent log tail."}{data?.backup && " Current log unavailable; showing the latest backup."}</p>
    {data?.logName && <div className="subtle" style={{ marginBottom: 8, fontSize: ".7rem" }}>{data.logName} · {data.modifiedAt ? new Date(data.modifiedAt).toLocaleString() : ""} · {(data.lines || []).length} displayed lines</div>}
    {error && <p role="alert">{error}</p>}
    <div ref={box} className="console" style={{ height: 320, maxHeight: "50dvh" }} aria-label={`${channel.toUpperCase()} log output`}>
      {data?.lines?.length ? data.lines.map((line, index) => <div className="ln" key={index}>{line}</div>) : <div className="ln subtle">{loading ? "Reading log snapshot…" : data?.missing ? "No log is available yet." : channel === "eos" ? "No EOS messages in the recent native log tail." : "The log is empty."}</div>}
    </div>
    <p className="subtle" style={{ marginBottom: 0, fontSize: ".7rem" }}>Logs may contain names, IP addresses or credentials. Review exports before sharing.</p>
  </section>;
}
