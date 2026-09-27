"use client";
// components/RemotePrefs.jsx
// Language + theme switch for the Remote Access guest surface (/remote). Deliberately
// SELF-CONTAINED and NON-PERSISTING to the server: it writes only remote-scoped
// localStorage keys and never calls /api/settings, so a guest changing their own language
// or theme can't touch the admin's app-wide preferences. Applied on mount so each device
// keeps its own choice.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import i18n from "@/lib/i18n/instance";
import { Icon } from "@/components/ui";

const THEME_KEY = "pal-remote-theme";
const LANG_KEY = "pal-remote-lang";

function applyTheme(theme) {
  try {
    const root = document.documentElement;
    if (theme === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
  } catch {}
}

// Lazy-load a language pack and switch to it WITHOUT persisting server-side.
async function switchLocal(code, dir = "ltr") {
  if (code !== "en" && !i18n.hasResourceBundle(code, "translation")) {
    const res = await fetch(`/api/i18n/pack/${encodeURIComponent(code)}`).then((r) => r.json()).catch(() => null);
    if (res && res.ok) {
      for (const l of Object.keys(res.resources)) {
        i18n.addResourceBundle(l, "translation", res.resources[l].translation, true, true);
      }
    }
  }
  await i18n.changeLanguage(code);
  try { document.documentElement.lang = code; document.documentElement.dir = dir || "ltr"; } catch {}
}

export default function RemotePrefs() {
  const { t } = useTranslation();
  const [theme, setTheme] = useState("dark");
  const [langs, setLangs] = useState([]);
  const [lang, setLang] = useState(i18n.language || "en");

  // Apply this device's saved remote preferences on mount.
  useEffect(() => {
    let savedTheme = "dark";
    try { savedTheme = localStorage.getItem(THEME_KEY) || (document.documentElement.classList.contains("dark") ? "dark" : "light"); } catch {}
    setTheme(savedTheme); applyTheme(savedTheme);

    fetch("/api/i18n/languages").then((r) => r.json()).then((r) => setLangs(r.languages || [])).catch(() => {});
    let savedLang = null;
    try { savedLang = localStorage.getItem(LANG_KEY); } catch {}
    if (savedLang && savedLang !== i18n.language) {
      switchLocal(savedLang).then(() => setLang(savedLang)).catch(() => {});
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next); applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch {}
  };

  const chooseLang = async (code) => {
    if (!code || code === lang) return;
    const meta = langs.find((l) => l.code === code);
    try { await switchLocal(code, meta?.dir || "ltr"); setLang(code); localStorage.setItem(LANG_KEY, code); } catch {}
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      {langs.length > 0 && (
        <select className="input" value={lang} onChange={(e) => chooseLang(e.target.value)}
          style={{ height: 34, padding: "0 0.5rem", fontSize: "0.82rem", width: "auto", minWidth: 120 }}
          title={t("remote.language")}>
          {langs.map((l) => <option key={l.code} value={l.code}>{l.nativeName || l.name || l.code}</option>)}
        </select>
      )}
      <button onClick={toggleTheme} title={t("action.toggleTheme")}
        style={{ background: "transparent", border: "1px solid var(--line)", cursor: "pointer", color: "var(--ink-soft)", padding: 7, borderRadius: 8, display: "grid", placeItems: "center" }}>
        <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
      </button>
    </div>
  );
}
