"use client";
// Frame for the Remote Access guest surface. The admin sidebar is bypassed for /remote
// (see components/Shell.jsx); this gives guests their own minimal top bar with the
// per-device language + theme switch, and a centered content column.
import RemotePrefs from "@/components/RemotePrefs";

export default function RemoteLayout({ children }) {
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <header style={{
        height: 56, display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 1.2rem", borderBottom: "1px solid var(--line-strong)", background: "var(--sidebar)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, overflow: "hidden", display: "grid", placeItems: "center" }}>
            <img src="/icon.png" alt="PSM" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          </div>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "0.92rem" }}>PSM Remote</span>
        </div>
        <RemotePrefs />
      </header>
      <main style={{ padding: "1.6rem 1.4rem 3rem", maxWidth: 1120, margin: "0 auto" }}>
        {children}
      </main>
    </div>
  );
}
