"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "@/components/ui";

export default function useLogExport() {
  const [exporting, setExporting] = useState(false);
  const controller = useRef(null);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; controller.current?.abort(); };
  }, []);
  const exportLogs = useCallback(async (kind, id) => {
    if (controller.current) return;
    const abort = new AbortController();
    controller.current = abort;
    setExporting(true);
    const timeout = setTimeout(() => abort.abort(), 60000);
    try {
      const scope = kind === "server" ? "worlds" : "profiles";
      const response = await fetch(`/api/${scope}/${encodeURIComponent(id)}/logs/export`, { cache: "no-store", credentials: "same-origin", signal: abort.signal });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `Log export failed (${response.status}).`);
      }
      if (!response.headers.get("Content-Type")?.includes("application/zip")) throw new Error("The log export did not return a ZIP file.");
      const blob = await response.blob();
      if (!mounted.current) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || "RSDW-logs.zip";
      document.body.appendChild(anchor);
      try { anchor.click(); } finally { anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000); }
      const warnings = Number(response.headers.get("X-RSDW-Log-Warnings") || 0);
      toast(warnings ? "Log ZIP download started. Some logs were unavailable or size-limited; see export-info.json." : "Log ZIP download started. Review logs before sharing.", warnings ? "info" : "success");
    } catch (error) {
      if (mounted.current) toast(error.name === "AbortError" ? "Log export timed out. Please try again." : error.message, "error");
    } finally {
      clearTimeout(timeout);
      controller.current = null;
      if (mounted.current) setExporting(false);
    }
  }, []);
  return { exportLogs, exporting };
}
