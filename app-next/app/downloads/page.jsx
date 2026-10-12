"use client";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useJobsPoll, JobCard } from "@/components/jobsClient";
import { PageHeader } from "@/components/PageChrome";

export default function DownloadsPage() {
  const { t } = useTranslation();
  const jobs = useJobsPoll();
  const [dismissed, setDismissed] = useState(() => new Set());

  const visible = jobs.filter((j) => !dismissed.has(j.id));
  const active = visible.filter((j) => j.status === "running");
  const history = visible.filter((j) => j.status !== "running");

  const dismiss = (id) => setDismissed((s) => new Set(s).add(id));
  const clearHistory = () => setDismissed((s) => {
    const n = new Set(s);
    history.forEach((j) => n.add(j.id));
    return n;
  });

  return (
    <div>
      <PageHeader eyebrow="TRANSFER CENTER" title={t("downloads.title")} description="Follow mod synchronization, cloud transfers, component installs, and SteamCMD activity in one place." icon="download" actions={history.length > 0 && (
          <button className="btn btn-ghost" onClick={clearHistory}>{t("downloads.clearHistory")}</button>
        )} />

      <Section title={`${t("downloads.inProgress")}${active.length ? ` (${active.length})` : ""}`}>
        {active.length === 0
          ? <Empty text={t("downloads.noActive")} />
          : <div style={{ display: "grid", gap: "0.7rem" }}>{active.map((j) => <JobCard key={j.id} job={j} defaultShowLog logHeight={320} />)}</div>}
      </Section>

      <Section title={t("downloads.history")}>
        {history.length === 0
          ? <Empty text={t("downloads.historyEmpty")} />
          : <div style={{ display: "grid", gap: "0.7rem" }}>{history.map((j) => <JobCard key={j.id} job={j} onDismiss={() => dismiss(j.id)} />)}</div>}
      </Section>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: "1.8rem" }}>
      <div className="subtle" style={{ fontSize: "0.7rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.7rem" }}>{title}</div>
      {children}
    </div>
  );
}

function Empty({ text }) {
  return <div className="panel-inset" style={{ padding: "1.1rem", textAlign: "center" }} ><span className="subtle" style={{ fontWeight: 600, fontSize: "0.86rem" }}>{text}</span></div>;
}
