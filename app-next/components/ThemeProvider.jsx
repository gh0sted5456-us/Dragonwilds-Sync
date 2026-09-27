"use client";
import { createContext, useContext, useEffect, useState, useCallback } from "react";

const ThemeCtx = createContext({ theme: "dark", setTheme: () => {}, toggle: () => {} });

export function useTheme() { return useContext(ThemeCtx); }

export default function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState("dark");

  useEffect(() => {
    let t = "dark";
    try { t = localStorage.getItem("pal-theme") || "dark"; } catch {}
    setThemeState(t);
    apply(t);
  }, []);

  const apply = (t) => {
    const root = document.documentElement;
    if (t === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
  };

  const setTheme = useCallback((t) => {
    setThemeState(t);
    apply(t);
    try { localStorage.setItem("pal-theme", t); } catch {}
    fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ theme: t }) }).catch(() => {});
  }, []);

  const toggle = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme, setTheme]);

  return <ThemeCtx.Provider value={{ theme, setTheme, toggle }}>{children}</ThemeCtx.Provider>;
}
