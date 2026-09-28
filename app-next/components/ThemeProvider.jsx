"use client";
import { createContext, useContext, useEffect, useCallback } from "react";

const ThemeCtx = createContext({ theme: "dark", setTheme: () => {}, toggle: () => {} });
export function useTheme() { return useContext(ThemeCtx); }

export default function ThemeProvider({ children }) {
  useEffect(() => {
    document.documentElement.classList.add("dark");
    try { localStorage.setItem("pal-theme", "dark"); } catch {}
  }, []);

  // RSDW Sync now has one deliberate application theme. Keep this compatibility
  // API so older components do not crash, but all theme requests resolve to dark.
  const setTheme = useCallback(() => {
    document.documentElement.classList.add("dark");
    try { localStorage.setItem("pal-theme", "dark"); } catch {}
  }, []);
  const toggle = setTheme;

  return <ThemeCtx.Provider value={{ theme: "dark", setTheme, toggle }}>{children}</ThemeCtx.Provider>;
}
