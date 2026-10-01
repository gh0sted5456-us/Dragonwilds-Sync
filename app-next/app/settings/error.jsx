"use client";

export default function SettingsError({ error, reset }) {
  return (
    <div className="panel" style={{ padding: "1.3rem", maxWidth: 680, borderLeft: "3px solid var(--yellow)" }}>
      <h1 className="heading" style={{ fontSize: "1.4rem", marginTop: 0 }}>Settings could not be displayed</h1>
      <p className="subtle" style={{ fontWeight: 650 }}>
        The rest of RSDW Sync is still running. Retry this page, and check launcher.log if the problem continues.
      </p>
      {error?.message && (
        <p className="panel-inset" style={{ padding: "0.7rem", fontFamily: "var(--font-mono)", fontSize: "0.75rem", wordBreak: "break-word" }}>
          {error.message}
        </p>
      )}
      <button className="btn btn-primary" onClick={reset}>Retry Settings</button>
    </div>
  );
}
