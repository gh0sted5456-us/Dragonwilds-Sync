"use client";
import { useEffect } from "react";

// Serial polling avoids overlapping requests on slow disks or servers. Browser
// visibility controls the cadence so a minimized launcher stays inexpensive.
export default function useAdaptivePolling(callback, { visibleMs, hiddenMs = 60000, enabled = true, immediate = true }) {
  useEffect(() => {
    if (!enabled) return undefined;
    let stopped = false;
    let running = false;
    let rerun = false;
    let timer = null;
    const delay = () => document.visibilityState === "hidden" ? hiddenMs : visibleMs;
    const schedule = () => {
      clearTimeout(timer);
      if (!stopped) timer = setTimeout(run, delay());
    };
    const run = async () => {
      if (stopped) return;
      if (running) { rerun = true; return; }
      running = true;
      try { await callback(); } catch { /* page callbacks own their UI error state */ }
      finally {
        running = false;
        if (rerun && !stopped && document.visibilityState === "visible") {
          rerun = false;
          void run();
        } else {
          rerun = false;
          schedule();
        }
      }
    };
    const visibilityChanged = () => {
      clearTimeout(timer);
      if (document.visibilityState === "visible") void run();
      else schedule();
    };
    document.addEventListener("visibilitychange", visibilityChanged);
    if (immediate) void run(); else schedule();
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", visibilityChanged);
    };
  }, [callback, enabled, hiddenMs, immediate, visibleMs]);
}
