"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

export const APP_THEMES = [
  { id: "dark", name: "RSDW Midnight", description: "Deep slate, soft rune violet, and clear status colors.", swatch: "#b8a1ef" },
  { id: "gilded", name: "Dragonwilds Gold", description: "Warm gold accents with the new workspace layout.", swatch: "#d2b577" },
  { id: "amethyst", name: "Rune Amethyst", description: "Deep violet with RuneSchema accents.", swatch: "#b394eb" },
  { id: "ember", name: "Ashen Ember", description: "Warm obsidian and Dragonwilds copper.", swatch: "#e3a66f" },
  { id: "frost", name: "Frostbound", description: "Cool slate and glacial blue.", swatch: "#89bfdf" },
];
const themeIds = new Set(APP_THEMES.map((item) => item.id));
const ThemeCtx = createContext({ theme: "dark", setTheme: () => {}, toggle: () => {} });
export function useTheme() { return useContext(ThemeCtx); }

export default function ThemeProvider({ children }) {
  const [theme, setCurrentTheme] = useState("dark");
  const setTheme = useCallback((requested) => {
    const next = themeIds.has(requested) ? requested : "dark";
    document.documentElement.classList.add("dark");
    document.documentElement.dataset.rsdwTheme = next;
    setCurrentTheme(next);
    try { window.desktop?.setWindowTheme?.(next)?.catch(() => {}); } catch {}
    try { localStorage.setItem("rsdw-theme", next); } catch {}
  }, []);

  useEffect(() => {
    let saved = "dark";
    try { saved = localStorage.getItem("rsdw-theme") || "dark"; } catch {}
    setTheme(saved);
  }, [setTheme]);

  const toggle = useCallback(() => {
    const index = APP_THEMES.findIndex((item) => item.id === theme);
    setTheme(APP_THEMES[(index + 1) % APP_THEMES.length].id);
  }, [setTheme, theme]);

  return <ThemeCtx.Provider value={{ theme, setTheme, toggle }}>{children}</ThemeCtx.Provider>;
}
