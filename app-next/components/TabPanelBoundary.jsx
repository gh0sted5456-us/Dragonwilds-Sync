"use client";

import React from "react";

export default class TabPanelBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, generation: 0 };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error(`World tab failed: ${this.props.tabId}`, error, info);
  }

  retry = () => {
    this.setState((state) => ({ error: null, generation: state.generation + 1 }));
  };

  render() {
    if (this.state.error) {
      return (
        <div className="panel-inset" role="alert" style={{ padding: "1rem", borderLeft: "3px solid var(--red)" }}>
          <div style={{ fontWeight: 850 }}>This tab could not finish loading.</div>
          <p className="subtle" style={{ margin: "5px 0 10px", overflowWrap: "anywhere" }}>
            {this.state.error?.message || "An unexpected panel error occurred."}
          </p>
          <button type="button" className="btn btn-primary" onClick={this.retry}>Retry tab</button>
        </div>
      );
    }
    return <React.Fragment key={this.state.generation}>{this.props.children}</React.Fragment>;
  }
}
