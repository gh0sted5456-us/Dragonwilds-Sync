"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { api, Icon, toast } from "@/components/ui";

// Warns (Windows only) when the server's required runtimes are missing, with a one-click
// elevated install surfaced in the Downloads tray. Renders nothing when everything's present.
export default function PrereqsNotice({ worldId }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setData(await api(`/api/worlds/${worldId}/prereqs`)); } catch { /* best effort */ }
  }, [worldId]);
  useEffect(() => { load(); }, [load]);

  if (!data || !data.supported || data.ok) return null;

  const missing = [!data.vcredist && t("prereqs.vcredist"), !data.directx && t("prereqs.directx")].filter(Boolean);

  const install = async () => {
    setBusy(true);
    try {
      await api(`/api/worlds/${worldId}/prereqs`, { method: "POST" });
      toast(t("prereqs.started"), "success");
      try { window.__palJobsPing?.(); } catch {}
      setTimeout(load, 30000); // re-check once the install has had a chance to finish
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };

  return (
    <div className="panel-inset" style={{ padding: "0.9rem 1.1rem", borderLeft: "3px solid var(--red)", marginBottom: "1rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Icon name="alert" size={16} />
        <span style={{ fontWeight: 800, fontSize: "0.9rem" }}>{t("prereqs.title")}</span>
      </div>
      <p className="subtle" style={{ fontWeight: 600, fontSize: "0.8rem", margin: "0 0 8px" }}>
        {t("prereqs.desc", { missing: missing.join(" + ") })}
      </p>
      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
        <button className="btn btn-primary" style={{ padding: "0.4rem 0.8rem" }} disabled={busy} onClick={install}>
          <Icon name="download" size={15} /> {busy ? t("prereqs.starting") : t("prereqs.install")}
        </button>
        <a href={data.vcRedistUrl} target="_blank" rel="noreferrer" style={{ color: "var(--accent)", fontWeight: 700, fontSize: "0.76rem" }}>
          {t("prereqs.manualVc")}
        </a>
      </div>
    </div>
  );
}
