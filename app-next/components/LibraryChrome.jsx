"use client";
import { useEffect, useState, useCallback } from "react";
import { Icon } from "@/components/ui";

export function useLayoutPreference(scope) {
  const [value, setValue] = useState("rows");
  useEffect(() => {
    try {
      const saved = localStorage.getItem(`rsdw-${scope}-layout`);
      if (saved === "placards" || saved === "rows") setValue(saved);
    } catch {}
  }, [scope]);
  const update = useCallback((next) => {
    setValue(next);
    try { localStorage.setItem(`rsdw-${scope}-layout`, next); } catch {}
  }, [scope]);
  return [value, update];
}

export function LayoutToggle({ value, onChange, label }) {
  return <div className="layout-toggle" role="group" aria-label={label}>
    <button className={value === "placards" ? "active" : ""} onClick={() => onChange("placards")} title="Placards" aria-label="Show placards" aria-pressed={value === "placards"}><Icon name="grid" size={16} /></button>
    <button className={value === "rows" ? "active" : ""} onClick={() => onChange("rows")} title="Rows" aria-label="Show rows" aria-pressed={value === "rows"}><Icon name="list" size={16} /></button>
  </div>;
}

export function RsdwBadge({ label }) { return <span style={{ display: "inline-flex", alignItems: "center", minHeight: 19, padding: "2px 7px", border: "1px solid color-mix(in srgb,var(--yellow) 45%,var(--line))", borderRadius: 999, background: "color-mix(in srgb,var(--yellow) 9%,var(--card))", color: "var(--yellow)", fontSize: ".62rem", fontWeight: 900, letterSpacing: ".045em" }}>{label}</span>; }
