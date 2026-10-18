"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
const { DEFAULT_APPEARANCE, normalizeAppearance } = require("@/lib/appearance-preferences");

export const APP_THEMES = [
  { id: "dark", name: "Obsidian Gold", description: "Helpy-inspired black glass, warm gold edges, and quiet highlights.", swatch: "#c7a45b" },
  { id: "gilded", name: "Dragonwilds Gold", description: "Burnished gold with warmer obsidian surfaces.", swatch: "#d2b577" },
  { id: "amethyst", name: "Rune Amethyst", description: "Deep violet with RuneSchema accents.", swatch: "#b394eb" },
  { id: "ember", name: "Ashen Ember", description: "Warm obsidian and Dragonwilds copper.", swatch: "#e3a66f" },
  { id: "frost", name: "Frostbound", description: "Cool slate and glacial blue.", swatch: "#89bfdf" },
];
const themeIds = new Set(APP_THEMES.map((item) => item.id));
const ThemeCtx = createContext({ theme: "dark", setTheme: () => {}, toggle: () => {} });
export function useTheme() { return useContext(ThemeCtx); }

export default function ThemeProvider({ children }) {
  const [theme, setCurrentTheme] = useState("dark");
  const [appearance, setAppearance] = useState(DEFAULT_APPEARANCE);
  const [preview, setPreview] = useState(null);
  const [appearanceError, setAppearanceError] = useState("");
  const [appearanceReady, setAppearanceReady] = useState(false);
  const path = usePathname();
  const guest = path === "/remote" || path.startsWith("/remote/");
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

  useEffect(() => {
    if (guest) return;
    try { const cached = JSON.parse(localStorage.getItem("rsdw-appearance") || "null"); if (cached) setAppearance(normalizeAppearance(cached)); } catch {}
    setAppearanceReady(true);
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 10000);
    fetch("/api/appearance", { cache: "no-store", signal: abort.signal }).then(async (response) => {
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Appearance could not be loaded.");
      if (!abort.signal.aborted) { setAppearance(normalizeAppearance(result.preferences)); setAppearanceError(result.warning || ""); }
    }).catch((error) => { if (!abort.signal.aborted) setAppearanceError(error.message); }).finally(() => clearTimeout(timeout));
    return () => { abort.abort(); clearTimeout(timeout); };
  }, [guest]);

  const effective = preview || appearance;
  useEffect(() => {
    if (!appearanceReady) return;
    const root = document.documentElement;
    root.style.setProperty("--workspace-background-opacity", String(effective.backgroundOpacity));
    root.style.setProperty("--surface-opacity", String(effective.surfaceOpacity));
    if (!preview) { try { localStorage.setItem("rsdw-appearance", JSON.stringify(appearance)); } catch {} }
  }, [appearance, appearanceReady, effective, preview]);

  const saveAppearance = useCallback(async (patch) => {
    const response = await fetch("/api/appearance", { method: "POST", cache: "no-store", headers: { "content-type": "application/json" }, body: JSON.stringify(patch), signal: AbortSignal.timeout(10000) });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Appearance could not be saved.");
    const next = normalizeAppearance(result.preferences);
    setAppearance(next); setPreview(null); setAppearanceError("");
    return next;
  }, []);
  const previewAppearance = useCallback((next) => setPreview(next ? normalizeAppearance(next) : null), []);

  const toggle = useCallback(() => {
    const index = APP_THEMES.findIndex((item) => item.id === theme);
    setTheme(APP_THEMES[(index + 1) % APP_THEMES.length].id);
  }, [setTheme, theme]);

  return <ThemeCtx.Provider value={{ theme, setTheme, toggle, appearance, effectiveAppearance: effective, appearanceError, appearanceReady, previewAppearance, saveAppearance }}>{children}</ThemeCtx.Provider>;
}

export function WorkspaceBackdrop() {
  const { effectiveAppearance = DEFAULT_APPEARANCE, appearanceReady } = useTheme();
  const { background, fit } = effectiveAppearance;
  return <div className="workspace-backdrop" aria-hidden="true">
    {appearanceReady && background !== "none" && <img key={background} src={`/api/appearance/background/${encodeURIComponent(background)}`} alt="" decoding="async" fetchPriority="low" style={{ objectFit: fit }} onError={(event) => { event.currentTarget.style.visibility = "hidden"; }} />}
    <div className="workspace-backdrop-shade" />
  </div>;
}
