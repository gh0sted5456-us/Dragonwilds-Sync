"use client";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Icon } from "@/components/ui";
import { ProgressBar, useJobsPoll } from "@/components/jobsClient";

export default function LogsPanel({ worldId }) {
  const { t } = useTranslation();
  const [lines, setLines] = useState([]);
  const [live, setLive] = useState(true);
  const [channel, setChannel] = useState("server");
  const boxRef = useRef(null);
  const esRef = useRef(null);
  const jobs = useJobsPoll();
  const maintenance = jobs.find((job) => job.worldId === worldId && ["install", "update"].includes(job.type))
    || jobs.find((job) => job.worldName === "Application Setup · Server" && ["install", "update"].includes(job.type));
  const maintenanceLines = (maintenance?.lines || []).filter((line) => channel === "all" ||
    (channel === "steamcmd" ? /^SteamCMD:/i.test(line) : /^RSDW:/i.test(line)));

  useEffect(() => {
    if (!live || channel !== "server") { esRef.current?.close(); return; }
    const es = new EventSource(`/api/worlds/${worldId}/logs/stream`);
    esRef.current = es;
    es.onmessage = (ev) => {
      try {
        const line = JSON.parse(ev.data);
        setLines((prev) => {
          const next = [...prev, line];
          return next.length > 800 ? next.slice(-800) : next;
        });
      } catch {}
    };
    es.onerror = () => { /* keep the panel; browser auto-reconnects */ };
    return () => es.close();
  }, [worldId, live, channel]);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [lines, maintenance?.lines?.length, channel]);

  return (
    <div>
      <div className="panel" style={{ padding: 4, display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 10 }}>
        {[["server", "Server"], ["steamcmd", "SteamCMD"], ["rsdw", "RSDW files"], ["all", "Full update log"]].map(([value, label]) =>
          <button key={value} className={`btn ${channel === value ? "btn-primary" : "btn-subtle"}`} onClick={() => setChannel(value)}>{label}</button>)}
      </div>
      {channel !== "server" && maintenance && <div className="panel-inset" style={{ padding: ".55rem .75rem", marginBottom: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: ".76rem" }}><span>{maintenance.message || "Preparing update…"}</span><strong>{maintenance.percent == null ? "" : `${maintenance.percent}%`}</strong></div>
        {maintenance.status === "running" && <ProgressBar percent={maintenance.percent} style={{ marginTop: 6 }} />}
        <div className="subtle" style={{ fontSize: ".68rem", marginTop: 4 }}>{maintenance.status === "error" ? maintenance.error : maintenance.status === "success" ? "Core and stopped profiles verified" : "Live file and SteamCMD progress"}</div>
      </div>}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
        <div className="subtle" style={{ fontWeight: 800, fontSize: "0.72rem" }}>{channel === "server" ? t("logs.linesBuffered", { count: lines.length }) : `${maintenanceLines.length} maintenance lines`}</div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {channel === "server" && <button className="btn btn-ghost" style={{ padding: "0.3rem 0.7rem" }} onClick={() => setLines([])}>{t("logs.clear")}</button>}
          {channel === "server" && <button className={`btn ${live ? "btn-primary" : "btn-ghost"}`} style={{ padding: "0.3rem 0.7rem" }} onClick={() => setLive((v) => !v)}>
            {live ? t("logs.live") : t("logs.paused")}
          </button>}
        </div>
      </div>
      <div ref={boxRef} className="console" style={{ height: 420 }}>
        {channel !== "server" ? (maintenanceLines.length ? maintenanceLines.map((line, index) => <div key={index} className="ln">{line}</div>) : <div className="ln subtle">No recent {channel === "steamcmd" ? "SteamCMD" : "RSDW"} update output. Start an update from Application Setup or this Server profile.</div>) : lines.length === 0
          ? <div className="ln subtle">{t("logs.waiting")}</div>
          : lines.map((l, i) => <div key={i} className="ln">{l}</div>)}
      </div>
    </div>
  );
}
