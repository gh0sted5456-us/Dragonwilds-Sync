"use client";
import { useEffect, useState } from "react";
import { api, Icon, toast } from "@/components/ui";
import { useJobsPoll, JobCard } from "@/components/jobsClient";

export default function ApplicationSetupPage() {
  const [tab, setTab] = useState("server");
  return <div>
    <header style={{ marginBottom: "1rem", display: "flex", alignItems: "center", gap: "1rem" }}>
      <img src="/rsdw/dragonwilds-logo.png" alt="RuneScape Dragonwilds" style={{ width: 112, height: 56, objectFit: "contain" }} />
      <div>
        <h1 className="heading" style={{ margin: 0, fontSize: "1.8rem" }}>Application Setup</h1>
        <p className="subtle" style={{ fontWeight: 650, margin: "4px 0 0" }}>
          Prepare machine-level Dragonwilds lanes. Profiles use these lanes; RSDW only changes an installation when you explicitly link, install, validate, or update it.
        </p>
      </div>
    </header>
    <div className="panel" style={{ padding: 6, display: "flex", gap: 6, marginBottom: "1rem" }}>
      <button className={`btn ${tab === "server" ? "btn-primary" : "btn-ghost"}`} style={{ flex: 1 }} onClick={() => setTab("server")}>
        <Icon name="terminal" /> Server
      </button>
      <button className={`btn ${tab === "play" ? "btn-primary" : "btn-ghost"}`} style={{ flex: 1 }} onClick={() => setTab("play")}>
        <Icon name="users" /> Play
      </button>
    </div>
    {tab === "server" ? <ServerSetup /> : <PlaySetup />}
  </div>;
}

function ServerSetup() {
  const [state, setState] = useState(null);
  const [dir, setDir] = useState("");
  const [platform, setPlatform] = useState("windows");
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState(null);
  const jobs = useJobsPoll();
  const setupJob = jobs.find((job) => job.id === jobId)
    || jobs.find((job) => job.worldName === "Application Setup · Server");
  const load = () => api("/api/application-setup/server").then((r) => {
    setState(r.server);
    if (r.server?.installDir) setDir(r.server.installDir);
    if (r.server?.platform) setPlatform(r.server.platform);
  }).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    if (window.desktop?.platform && !state?.platform) {
      setPlatform(window.desktop.platform === "win32" ? "windows" : "linux");
    }
    load();
  }, []);
  useEffect(() => {
    if (setupJob && setupJob.status !== "running") load();
  }, [setupJob?.status]);

  const browse = async () => {
    const selected = await window.desktop?.pickDirectory?.();
    if (selected) setDir(selected);
  };
  const adopt = async () => {
    const executablePath = await window.desktop?.pickServerExecutable?.();
    if (!executablePath) return;
    setBusy(true);
    try {
      const result = await api("/api/application-setup/server", { method: "POST", body: { mode: "adopt", executablePath } });
      setState(result.server);
      setDir(result.server.installDir || "");
      setPlatform(result.server.platform || platform);
      toast("Existing dedicated server verified and linked.", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };
  const install = async () => {
    if (!dir.trim()) return toast("Choose a dedicated-server folder.", "error");
    setBusy(true);
    try {
      const result = await api("/api/application-setup/server", { method: "POST", body: { mode: "steamcmd", installDir: dir.trim(), platform } });
      setJobId(result.jobId);
      try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {}
      toast(result.alreadyRunning ? "The existing SteamCMD setup job is still running." : "SteamCMD server setup started.", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };

  return <div style={{ display: "grid", gap: 12 }}>
  <div className="panel" style={{ padding: "1.2rem" }}>
    <h2 className="heading" style={{ marginTop: 0, fontSize: "1.1rem" }}>SteamCMD · Dedicated Server</h2>
    <p className="subtle" style={{ fontWeight: 650 }}>
      Link an existing <code>RSDragonwildsServer.exe</code>, or let RSDW install and validate the shared dedicated-server lane through SteamCMD.
    </p>
    <SetupState ready={state?.ready} text={state?.ready ? `Ready · build ${state.buildId || "unknown"}` : "Not configured"} />
    {state?.binary && <p className="subtle" style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", wordBreak: "break-all" }}>{state.binary}</p>}
    <div className="panel-inset" style={{ margin: "12px 0", padding: ".8rem", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      <div style={{ flex: 1, minWidth: 220 }}>
        <strong>Already have the server?</strong>
        <div className="subtle" style={{ fontSize: ".74rem" }}>Choose the server executable. RSDW finds its root, platform, manifest, settings, and save paths before linking it.</div>
      </div>
      <button className="btn btn-ghost" disabled={busy || typeof window === "undefined" || !window.desktop?.pickServerExecutable} onClick={adopt}><Icon name="folder" /> Select server executable</button>
    </div>
    <label className="label">Server installation folder</label>
    <div style={{ display: "flex", gap: 8 }}>
      <input className="input" style={{ flex: 1 }} value={dir} onChange={(e) => setDir(e.target.value)} placeholder="Choose a dedicated server folder" />
      <button className="btn btn-ghost" onClick={browse}><Icon name="folder" /> Browse</button>
    </div>
    <label className="label" style={{ marginTop: 12 }}>Server platform</label>
    <select className="input" value={platform} onChange={(e) => setPlatform(e.target.value)}>
      <option value="windows">Windows</option>
      <option value="linux">Linux</option>
    </select>
    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
      <button className="btn btn-primary" disabled={busy || setupJob?.status === "running"} onClick={install}><Icon name="download" /> {state?.ready ? "Validate / Update with SteamCMD" : "Install with SteamCMD"}</button>
    </div>
    <p className="subtle" style={{ marginBottom: 0, fontSize: ".72rem" }}>
      SteamCMD: {state?.steamcmdInstalled ? state.steamcmdPath : "will be downloaded automatically"}
    </p>
  </div>
  {setupJob && <div className="panel" style={{ padding: "1rem" }}>
    <div className="heading" style={{ marginBottom: 8 }}>SteamCMD output</div>
    <JobCard job={setupJob} defaultShowLog logHeight={360} />
  </div>}
  </div>;
}

function PlaySetup() {
  const [state, setState] = useState(null);
  const [dirs, setDirs] = useState({ steam: "", gamepass: "" });
  const load = () => api("/api/application-setup/play").then((r) => {
    setState(r.play);
    setDirs({
      steam: r.play?.steam?.installDir || "",
      gamepass: r.play?.gamepass?.installDir || "",
    });
  }).catch((e) => toast(e.message, "error"));
  useEffect(() => { load(); }, []);

  const browse = async (platform) => {
    const selected = await window.desktop?.pickDirectory?.();
    if (selected) setDirs((v) => ({ ...v, [platform]: selected }));
  };
  const save = async (platform) => {
    try {
      const r = await api("/api/application-setup/play", { method: "POST", body: { platform, installDir: dirs[platform] } });
      setState(r.play);
      setDirs({
        steam: r.play?.steam?.installDir || "",
        gamepass: r.play?.gamepass?.installDir || "",
      });
      toast(`${platform === "steam" ? "Steam" : "PC Game Pass"} Play lane saved.`, "success");
    } catch (e) { toast(e.message, "error"); }
  };

  return <div style={{ display: "grid", gap: 12 }}>
    <PlayLane label="Steam" platform="steam" ready={state?.steam?.ready} value={dirs.steam} onChange={(v) => setDirs((d) => ({ ...d, steam: v }))} onBrowse={() => browse("steam")} onSave={() => save("steam")} />
    <PlayLane label="PC Game Pass" platform="gamepass" ready={state?.gamepass?.ready} value={dirs.gamepass} onChange={(v) => setDirs((d) => ({ ...d, gamepass: v }))} onBrowse={() => browse("gamepass")} onSave={() => save("gamepass")} />
  </div>;
}

function PlayLane({ label, ready, value, onChange, onBrowse, onSave }) {
  return <div className="panel" style={{ padding: "1.2rem" }}>
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <h2 className="heading" style={{ margin: 0, fontSize: "1.05rem" }}>{label} lane</h2>
      <SetupState ready={ready} text={ready ? "Ready" : "Not configured"} />
    </div>
    <p className="subtle" style={{ fontWeight: 650 }}>
      This machine-level lane is shared by Player profiles that launch through {label}. Client runtime setup and repair belong to this lane, not to an individual World.
    </p>
    <div style={{ display: "flex", gap: 8 }}>
      <input className="input" style={{ flex: 1 }} value={value} onChange={(e) => onChange(e.target.value)} placeholder={`${label} Dragonwilds folder`} />
      <button className="btn btn-ghost" onClick={onBrowse}><Icon name="folder" /> Browse</button>
      <button className="btn btn-primary" onClick={onSave}>Save Lane</button>
    </div>
  </div>;
}

function SetupState({ ready, text }) {
  return <span className="chip" style={{ background: ready ? "var(--accent)" : "var(--line)", color: ready ? "var(--accent-ink)" : "var(--ink-soft)", fontWeight: 800 }}>{text}</span>;
}
