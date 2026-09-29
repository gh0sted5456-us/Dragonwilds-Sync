"use client";
import { useState } from "react";
import { Icon } from "@/components/ui";

export default function InfoPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <div style={{ height: "calc(100vh - 4.6rem)", minHeight: 620, display: "flex", flexDirection: "column", gap: "0.7rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.8rem", flexWrap: "wrap" }}>
        <div style={{ minWidth: 220, flex: 1 }}>
          <h1 className="heading" style={{ fontSize: "1.7rem", margin: 0 }}>Helpy</h1>
          <div className="subtle" style={{ fontSize: "0.75rem", fontWeight: 650, marginTop: 2 }}>
            Live guide · GitHub branch codex/super-experimental
          </div>
        </div>
        <button className="btn btn-ghost" onClick={() => setRefreshKey((key) => key + 1)}>
          <Icon name="refresh" size={15} /> Refresh
        </button>
      </div>

      <div className="panel" style={{ flex: 1, minHeight: 0, overflow: "hidden", borderColor: "var(--line-strong)" }}>
        <iframe
          key={refreshKey}
          title="Helpy"
          src={`https://gh0sted5456-us.github.io/Dragonwilds-Sync/helpy.html?embed=1&theme=dark&r=${refreshKey}`}
          style={{ width: "100%", height: "100%", border: 0, display: "block", background: "#0e0e0e" }}
          sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        />
      </div>
    </div>
  );
}
