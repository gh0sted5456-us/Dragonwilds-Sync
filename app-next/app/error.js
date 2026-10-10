"use client";

import { useEffect } from "react";

// Next route-level containment. This catches failures during navigation/data rendering
// before they can escalate to the desktop window or require an application restart.
export default function RouteError({ error, reset }) {
  useEffect(() => { console.error("Route failed", error); }, [error]);
  return (
    <div className="panel" role="alert" style={{ padding: "1.3rem", borderLeft: "3px solid var(--red)" }}>
      <h2 className="heading" style={{ marginTop: 0 }}>This page could not finish loading</h2>
      <p className="subtle" style={{ overflowWrap: "anywhere" }}>{error?.message || "An unexpected page error occurred."}</p>
      <button type="button" className="btn btn-primary" onClick={reset}>Retry page</button>
    </div>
  );
}
