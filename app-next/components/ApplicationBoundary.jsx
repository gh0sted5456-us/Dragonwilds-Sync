"use client";

import React from "react";

// Last-resort renderer containment. Individual World tabs have their own boundary;
// this one ensures a failure on any other page cannot replace the Electron window
// with Next's generic application-error screen.
export default class ApplicationBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) { return { error }; }

  componentDidCatch(error, info) {
    console.error("Application view failed", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "2rem", background: "var(--bg)" }}>
        <div className="panel" role="alert" style={{ width: "min(560px, 100%)", padding: "1.4rem", borderLeft: "3px solid var(--red)" }}>
          <h1 className="heading" style={{ fontSize: "1.25rem", marginTop: 0 }}>This view stopped unexpectedly</h1>
          <p className="subtle" style={{ overflowWrap: "anywhere" }}>{this.state.error?.message || "An unexpected interface error occurred."}</p>
          <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={() => this.setState({ error: null })}>Retry view</button>
            <button className="btn btn-ghost" onClick={() => window.location.assign("/")}>Return to Worlds</button>
          </div>
        </div>
      </main>
    );
  }
}
