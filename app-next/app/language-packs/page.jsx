"use client";
import { useState } from "react";
import Link from "next/link";
import { useTranslation, Trans } from "react-i18next";
import { api, Icon, toast } from "@/components/ui";

// Standalone guide (separate from Settings) that explains the pack format and lets a
// user bring their own translation — import a .json file or add one by https link.
// Both paths go through the same validated /api/i18n routes the catalog install uses.
export default function LanguagePacksPage() {
  const { t } = useTranslation();
  const [packBusy, setPackBusy] = useState(false);
  const [packUrl, setPackUrl] = useState("");
  const [added, setAdded] = useState(null); // last successfully added language

  const onAdded = (language) => {
    setAdded(language || null);
    toast(t("language.imported", { name: language?.nativeName || language?.code || "" }), "success");
  };

  const importPack = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setPackBusy(true);
    try {
      const content = await file.text();
      const r = await api("/api/i18n/import", { method: "POST", body: { content } });
      onAdded(r.language);
    } catch (err) { toast(err.message || t("language.readError"), "error"); }
    finally { setPackBusy(false); e.target.value = ""; }
  };

  const downloadPack = async () => {
    if (!packUrl.trim()) return;
    setPackBusy(true);
    try {
      const r = await api("/api/i18n/download", { method: "POST", body: { url: packUrl.trim() } });
      setPackUrl("");
      onAdded(r.language);
    } catch (err) { toast(err.message, "error"); }
    finally { setPackBusy(false); }
  };

  const example = `{
  "meta": {
    "code": "fr",
    "name": "French",
    "nativeName": "Français",
    "dir": "ltr"
  },
  "strings": {
    "nav.worlds": "Mondes",
    "common.save": "Sauvegarder",
    "worlds.summary_one": "{{count}} monde · {{running}} en cours · {{players}} en ligne"
  }
}`;

  return (
    <div style={{ maxWidth: 820 }}>
      <Link href="/settings" className="btn btn-ghost" style={{ padding: "0.3rem 0.6rem", fontSize: "0.78rem", marginBottom: "1rem" }}>
        <Icon name="back" size={15} /> {t("packGuide.back")}
      </Link>
      <h1 className="heading" style={{ fontSize: "1.9rem", margin: "0 0 0.3rem" }}>{t("packGuide.title")}</h1>
      <p className="subtle" style={{ fontWeight: 600, fontSize: "0.9rem", margin: "0 0 1.4rem" }}>{t("packGuide.subtitle")}</p>

      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("packGuide.whatTitle")}</h3>
        <p className="subtle" style={{ fontWeight: 600, fontSize: "0.84rem", margin: 0 }}>{t("packGuide.whatBody")}</p>
      </div>

      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("packGuide.getTitle")}</h3>
        <p className="subtle" style={{ fontWeight: 600, fontSize: "0.84rem", margin: "0 0 0.6rem" }}>{t("packGuide.getBody")}</p>
        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
          <Link href="/settings" className="btn btn-ghost" style={{ padding: "0.35rem 0.7rem" }}>
            <Icon name="settings" size={15} /> {t("packGuide.goToSettings")}
          </Link>
          <a href="https://github.com/PrakashMandal-IV/palworld-server-manager/tree/main/registry/packs" target="_blank" rel="noreferrer"
            className="btn btn-ghost" style={{ padding: "0.35rem 0.7rem" }}>
            <Icon name="globe" size={15} /> {t("language.packLibrary")}
          </a>
        </div>
      </div>

      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("packGuide.createTitle")}</h3>

        <div style={{ display: "grid", gap: "1rem" }}>
          <div>
            <div className="heading" style={{ fontSize: "0.92rem" }}>{t("packGuide.step1Title")}</div>
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.82rem", margin: "0.2rem 0 0.5rem" }}>{t("packGuide.step1Body")}</p>
            <a href="/locales/en.json" download="en.json" className="btn btn-primary" style={{ padding: "0.35rem 0.7rem" }}>
              <Icon name="download" size={15} /> {t("packGuide.downloadTemplate")}
            </a>
          </div>
          <div>
            <div className="heading" style={{ fontSize: "0.92rem" }}>{t("packGuide.step2Title")}</div>
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.82rem", margin: "0.2rem 0 0" }}>
              <Trans i18nKey="packGuide.step2Body" components={{ b: <b />, code: <code /> }} />
            </p>
          </div>
          <div>
            <div className="heading" style={{ fontSize: "0.92rem" }}>{t("packGuide.step3Title")}</div>
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.82rem", margin: "0.2rem 0 0" }}>
              <Trans i18nKey="packGuide.step3Body" components={{ code: <code /> }} />
            </p>
          </div>
        </div>

        <div className="heading" style={{ fontSize: "0.92rem", marginTop: "1.2rem" }}>{t("packGuide.exampleTitle")}</div>
        <pre style={{
          background: "var(--panel-inset, rgba(127,127,127,0.08))", border: "1px solid var(--border)", borderRadius: 8,
          padding: "0.8rem 1rem", overflowX: "auto", fontSize: "0.78rem", fontFamily: "var(--font-mono)", margin: "0.4rem 0 0",
        }}><code>{example}</code></pre>

        <div className="heading" style={{ fontSize: "0.92rem", marginTop: "1.2rem" }}>{t("packGuide.formatTitle")}</div>
        <ul className="subtle" style={{ fontWeight: 600, fontSize: "0.82rem", margin: "0.4rem 0 0", paddingLeft: "1.1rem" }}>
          <li>{t("packGuide.format1")}</li>
          <li><Trans i18nKey="packGuide.format2" components={{ code: <code />, b: <b /> }} /></li>
          <li>{t("packGuide.format3")}</li>
        </ul>
      </div>

      <div className="panel" style={{ padding: "1.3rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("packGuide.addTitle")}</h3>
        <p className="subtle" style={{ fontWeight: 600, fontSize: "0.84rem", margin: "0 0 0.8rem" }}>{t("packGuide.addBody")}</p>

        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          <label className="btn btn-ghost" style={{ cursor: packBusy ? "default" : "pointer" }}>
            <Icon name="upload" size={15} /> {packBusy ? t("language.importing") : t("language.importFile")}
            <input type="file" accept=".json,application/json" hidden disabled={packBusy} onChange={importPack} />
          </label>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.6rem", flexWrap: "wrap" }}>
          <input className="input" style={{ flex: 1, minWidth: 240 }} placeholder={t("language.downloadUrlPlaceholder")}
            value={packUrl} onChange={(e) => setPackUrl(e.target.value)} disabled={packBusy}
            onKeyDown={(e) => e.key === "Enter" && downloadPack()} />
          <button className="btn btn-primary" onClick={downloadPack} disabled={packBusy || !packUrl.trim()}>
            <Icon name="globe" size={15} /> {packBusy ? t("language.downloading") : t("language.download")}
          </button>
        </div>

        {added && (
          <div className="panel-inset" style={{ padding: "0.7rem 0.9rem", marginTop: "0.9rem", borderLeft: "3px solid var(--green-bright, var(--accent))" }}>
            <span style={{ fontWeight: 700, fontSize: "0.84rem" }}>{t("packGuide.addedHint", { name: added.nativeName || added.code })}</span>
            <Link href="/settings" className="btn btn-ghost" style={{ marginLeft: "0.6rem", padding: "0.25rem 0.55rem", fontSize: "0.76rem" }}>
              {t("packGuide.goToSettings")}
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
