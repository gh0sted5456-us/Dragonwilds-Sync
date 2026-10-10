"use client";
// components/RemotePrefs.jsx
// Theme switch for the Remote Access guest surface. It is deliberately local to the
// guest device and never changes host settings.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Icon } from "@/components/ui";

const THEME_KEY = "pal-remote-theme";

function applyTheme(theme) {
  try {
    const root = document.documentElement;
    if (theme === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
  } catch {}
}

export default function RemotePrefs() {
  const { t } = useTranslation();
  const [theme, setTheme] = useState("dark");

  // Apply this device's saved remote preferences on mount.
  useEffect(() => {
    let savedTheme = "dark";
    try { savedTheme = localStorage.getItem(THEME_KEY) || (document.documentElement.classList.contains("dark") ? "dark" : "light"); } catch {}
    setTheme(savedTheme); applyTheme(savedTheme);

  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next); applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch {}
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <button onClick={toggleTheme} title={t("action.toggleTheme")}
        style={{ background: "transparent", border: "1px solid var(--line)", cursor: "pointer", color: "var(--ink-soft)", padding: 7, borderRadius: 8, display: "grid", placeItems: "center" }}>
        <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
      </button>
    </div>
  );
}
