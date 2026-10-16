"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, Icon, toast } from "@/components/ui";
import ProfileSavesPanel from "@/components/ProfileSavesPanel";
import ClientSyncJourney from "@/components/ClientSyncJourney";
import ClientSafeStoragePanel from "@/components/ClientSafeStoragePanel";
import AppOverlay from "@/components/AppOverlay";
import { useJobsPoll } from "@/components/jobsClient";
const { deliveryInfo } = require("@/lib/sync-progress");

export default function PlayerProfile({ params }) {
  return <PlayerProfileWorkspace key={params.id} params={params} />;
}

function PlayerProfileWorkspace({ params }) {
  const searchParams = useSearchParams();
  const autoplay = searchParams.get("autoplay") === "1";
  const autoStarted = useRef(false);
  const [profile, setProfile] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [loadAttempts, setLoadAttempts] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(null);
  const [playLanes, setPlayLanes] = useState({ steam: null, epic: null, gamepass: null });
  const [locations, setLocations] = useState({ installDir: "", executablePath: "", savePath: "" });
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);
  const [flowStep, setFlowStep] = useState(null);
  const [flowStage, setFlowStage] = useState(null);
  const [flowError, setFlowError] = useState(null);
  const [skipDownload, setSkipDownload] = useState(false);
  const [launchReady, setLaunchReady] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [credentialOpen, setCredentialOpen] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [preparedLinks, setPreparedLinks] = useState(0);
  const [syncStartedAt, setSyncStartedAt] = useState(0);
  const jobs = useJobsPoll();
  const activeSyncJob = jobs.find((job) => job.type === "sync" && job.worldId === params.id && job.status === "running");
  const busy = checking || launching || !!activeSyncJob;
  useEffect(() => { if (activeSyncJob) setSyncStartedAt(activeSyncJob.startedAt); }, [activeSyncJob?.id]);
  useEffect(() => {
    let active = true;
    setLoadError("");
    Promise.all([api(`/api/profiles/${params.id}`), api("/api/application-setup/play")]).then(([profileResponse, installsResponse]) => {
      if (!active) return;
      setProfile(profileResponse.profile);
      setLocations({ installDir: profileResponse.profile.client_install || "", executablePath: profileResponse.profile.connection?.executablePath || "", savePath: profileResponse.profile.connection?.savePath || "" });
      setPlayLanes({
        steam: installsResponse.play?.steam?.installDir || null,
        epic: installsResponse.play?.epic?.installDir || null,
        gamepass: installsResponse.play?.gamepass?.installDir || null,
      });
    }).catch((e) => { if (active) { setLoadError(e.message); toast(e.message, "error"); } });
    return () => { active = false; };
  }, [params.id, loadAttempts]);

  const refreshProfile = async () => {
    const latest = await api(`/api/profiles/${params.id}`);
    setProfile(latest.profile);
    setLocations({ installDir: latest.profile.client_install || "", executablePath: latest.profile.connection?.executablePath || "", savePath: latest.profile.connection?.savePath || "" });
    return latest.profile;
  };

  const requestAdmission = async () => {
    setFlowStage("ack");
    setFlowStep("Submitting verified client manifest to World…");
    const response = await api(`/api/profiles/${params.id}/admit`, { method: "POST", body: {} });
    await refreshProfile();
    setLaunchReady(!!response.admission?.approved);
    setFlowStage("ready");
    setFlowStep(response.admission?.approved ? "Server approved this manifest. Ready to enter." : "Shared files are ready. Player shares do not issue server login approval.");
    return response.admission;
  };

  const connect = async () => {
    if (busy) return;
    setSyncStartedAt(0);
    setChecking(true); setResult(null); setLaunchReady(false); setFlowError(null); setSkipDownload(false);
    setFlowStage("auth"); setFlowStep("Authenticating and downloading the World manifest…");
    try {
      const response = await api(`/api/profiles/${params.id}/verify`, { method: "POST", body: {} });
      setFlowStage("compare"); setFlowStep("Comparing the World manifest with your managed files…");
      setResult({ ...response.comparison, prerequisites: response.manifest.prerequisites });
      await refreshProfile();
      if (response.comparison.current) {
        setSkipDownload(true); setFlowStage("verify");
        if (profile.connection?.cachedModProfile?.revision === response.manifest.revision) await requestAdmission();
        else setFlowStep("The installed files match. Choose Sync files to save this World's private profile and request host approval.");
      } else {
        setFlowStage("download"); setFlowStep(`${response.comparison.changes.length} file(s) need syncing. Choose Sync files to continue.`);
      }
      toast(response.comparison.current ? "Connected — your managed mods match this World." : `${response.comparison.changes.length} mod file(s) need synchronization.`, response.comparison.current ? "success" : "info");
    } catch (e) { setFlowError(e.message); toast(e.message, "error"); } finally { setChecking(false); }
  };
  const acceptSyncResponse = async (response) => {
    const { installed, manifest } = response.result;
    setSkipDownload(installed.length === 0);
    setResult({ current: true, changes: [], units: summarizeUnits(manifest), transport: manifest.transport, prerequisites: manifest.prerequisites });
    await refreshProfile();
    setLaunchReady(!!response.admission?.approved);
    setFlowStage("ready");
    setFlowStep(response.admission?.approved ? "Files verified and approved by the host. You can review credentials and enter." : "Shared files verified and saved. No server login approval is issued by player shares.");
    try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {}
  };
  const sync = async () => {
    if (busy) return;
    setSyncStartedAt(Date.now());
    setResult(null);
    setChecking(true); setLaunchReady(false); setFlowError(null); setSkipDownload(false);
    setFlowStage("auth"); setFlowStep("Connecting to the World and preparing managed downloads…");
    try {
      const request = api(`/api/profiles/${params.id}/sync`, { method: "POST", body: {} });
      setTimeout(() => { try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {} }, 250);
      const response = await request;
      const { installed, removed } = response.result;
      await acceptSyncResponse(response);
      toast(`World synchronized: ${installed.length} installed or updated, ${removed.length} removed.`, "success");
    } catch (e) { setFlowError(e.message); toast(e.message, "error"); try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {} } finally { setChecking(false); }
  };
  const setService = async (service) => {
    if (busy) return;
    try {
      const installDir = playLanes[service] || locations.installDir;
      const response = await api("/api/client-service", { method: "POST", body: { profileId: params.id, service, installDir, executablePath: installDir === locations.installDir ? locations.executablePath : "", savePath: locations.savePath, persist: true } });
      await refreshProfile();
      setLocations({ installDir: response.installation.installDir || "", executablePath: response.installation.executablePath || "", savePath: response.installation.savePath || "" });
      setResult(null);
      setSyncStartedAt(0); setLaunchReady(false); setFlowStage(null); setFlowError(null);
      toast(`${response.installation.label} identified for this World.`, "success");
    } catch (e) { toast(e.message, "error"); }
  };
  const detectService = async () => {
    if (busy) return;
    try {
      const response = await api("/api/client-service", { method: "POST", body: { profileId: params.id, installDir: locations.installDir, executablePath: locations.executablePath, savePath: locations.savePath, persist: true } });
      await refreshProfile();
      setLocations({ installDir: response.installation.installDir || "", executablePath: response.installation.executablePath || "", savePath: response.installation.savePath || "" });
      setResult(null); setLaunchReady(false); setFlowStage(null); setFlowError(null);
      toast(`Detected ${response.installation.label} from the selected paths.`, "success");
    } catch (e) { toast(e.message, "error"); }
  };
  const join = async () => {
    if (busy || !launchReady || !result?.current) return toast("Sync and obtain host approval before joining.", "error");
    setChecking(true);
    try {
      setFlowError(null);
      const approved = await requestAdmission();
      if (!approved?.approved) throw new Error("This is a file share, not a server login approval.");
      const activated = await api(`/api/profiles/${params.id}/activate`, { method: "POST", body: {} });
      const linked = Number(activated.activation?.deployment?.hardlink || 0) + Number(activated.activation?.deployment?.symlink || 0);
      setPreparedLinks(linked);
      setCredentialOpen(true);
    } catch (e) { setLaunchReady(false); setCredentialOpen(false); setFlowError(e.message); toast(e.message, "error"); }
    finally { setChecking(false); }
  };
  const launchGame = async () => {
    const service = profile.connection?.service || (profile.connection?.platform === "gamepass" ? "gamepass" : "steam");
    setLaunching(true);
    try {
      if (!window.desktop?.launchWorld) throw new Error("Joining is available in the Windows desktop app.");
      await window.desktop.launchWorld({ service, installDir: profile.client_install, executablePath: profile.connection?.executablePath });
      setCredentialOpen(false);
      toast(`Opening Dragonwilds with ${serviceName(service)} · ${preparedLinks} profile link(s) active.`, "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setLaunching(false); }
  };
  const launchLocal = async () => {
    const service = profile.connection?.service || "steam";
    if (service === "gamepass") return toast("Use the verified RSDW Save Converter to place this save into an existing Game Pass slot first.", "error");
    setLaunching(true);
    try {
      const activated = await api(`/api/profiles/${params.id}/activate`, { method: "POST", body: {} });
      if (!window.desktop?.launchWorld) throw new Error("Launching is available in the Windows desktop app.");
      await window.desktop.launchWorld({ service, installDir: profile.client_install || playLanes[service], executablePath: profile.connection?.executablePath });
      toast(`Activated ${activated.activation?.saves?.world?.name || profile.display_name} and opened Dragonwilds.`, "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setLaunching(false); }
  };
  const copyValue = async (label, value) => {
    const text = String(value || "");
    if (!text) return toast(`${label} is not available.`, "error");
    try {
      await navigator.clipboard.writeText(text);
      toast(`${label} copied.`, "success");
    } catch {
      toast(`Could not copy ${label}.`, "error");
    }
  };

  const sendToDesktop = async () => {
    try {
      const identity = profile.connection?.worldIdentity || {};
      const path = await window.desktop.createProfileShortcut({ id: params.id, role: "player", name: profile.display_name, iconData: identity.iconData || null, service: profile.connection?.service || profile.connection?.platform || "steam" });
      toast(`Shortcut created: ${path}`, "success");
    } catch (e) { toast(e.message, "error"); }
  };

  const toggleShare = async () => {
    setSharing(true);
    try {
      const response = await api(`/api/profiles/${params.id}/share`, { method: "POST", body: { enabled: !profile.connection?.shareEnabled } });
      setProfile(response.profile);
      toast(response.profile.connection?.shareEnabled
        ? "Player profile sharing is on. Friends can discover this profile and sync its verified cached files with the share code."
        : "Player profile sharing is off.", "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setSharing(false); }
  };

  useEffect(() => {
    if (!autoplay || !profile || autoStarted.current) return;
    autoStarted.current = true;
    if (profile.connection?.localWorld) { void launchLocal(); return; }
    (async () => {
      setChecking(true);
      setSyncStartedAt(0);
      setLaunchReady(false);
      setFlowError(null); setFlowStage("auth"); setSkipDownload(false);
      try {
        setFlowStep("Authenticating with World…");
        const verified = await api(`/api/profiles/${params.id}/verify`, { method: "POST", body: {} });
        setResult({ ...verified.comparison, prerequisites: verified.manifest.prerequisites });
        setFlowStage("compare");
        await refreshProfile();
        if (!verified.comparison.current || profile.connection?.cachedModProfile?.revision !== verified.manifest.revision) {
          setFlowStage("download");
          setFlowStep(`Synchronizing ${verified.comparison.changes.length} managed file(s)…`);
          const request = api(`/api/profiles/${params.id}/sync`, { method: "POST", body: {} });
          setSyncStartedAt(Date.now());
          setTimeout(() => { try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {} }, 250);
          const synced = await request;
          await acceptSyncResponse(synced);
        } else { setSkipDownload(true); setFlowStage("verify"); await requestAdmission(); }
      } catch (e) {
        setFlowStep("Connection could not be completed.");
        setFlowError(e.message);
        toast(e.message, "error");
      } finally {
        setChecking(false);
      }
    })();
  }, [autoplay, profile, params.id]);

  if (!profile) return <main className="player-world-workspace"><Link href="/" className="page-back"><Icon name="back" /> Back to World Management</Link>{loadError ? <div className="panel" role="alert" style={{ padding: 20 }}>World profile could not be loaded: {loadError} <button className="btn btn-ghost" onClick={() => setLoadAttempts((value) => value + 1)}>Retry</button></div> : <p role="status">Loading World profile…</p>}</main>;
  const selectedService = profile.connection?.service || (profile.connection?.platform === "gamepass" ? "gamepass" : "steam");
  const selectedInstall = profile.client_install || playLanes[selectedService];
  const syncJob = activeSyncJob || (syncStartedAt ? jobs.find((job) => job.type === "sync" && job.worldId === params.id && job.startedAt >= syncStartedAt - 100) : null);
  const identity = profile.connection?.worldIdentity || {};
  const transport = result?.transport || profile.connection;
  const playerShare = String(profile.connection?.worldId || profile.server_world_id || "").startsWith("profile-");
  const showSettings = settingsOpen ?? (!selectedInstall || !!profile.connection?.localWorld);
  return <main className="player-world-workspace">
    <Link href="/" className="page-back"><Icon name="back" /> Back to World Management</Link>
    <div style={{ position: "relative", minHeight: 112, marginBottom: 18, borderRadius: 14, overflow: "hidden", border: "1px solid var(--line-strong)", background: "var(--card)" }}>
      {identity.bannerData && <img src={identity.bannerData} alt="" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: .5 }} />}
      <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg,var(--card) 18%,transparent 80%)" }} />
      <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 14, padding: 18 }}>
        <img src={identity.iconData || "/icon.png"} alt="" style={{ width: 64, height: 64, borderRadius: 14, objectFit: identity.iconData ? "cover" : "contain", border: "1px solid var(--line-strong)" }} />
        <div><div className="eyebrow">ASSOCIATED WORLD</div><h1 style={{ margin: 0 }}>{profile.display_name}</h1><div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 6 }}><span className="chip">{profile.connection?.rules?.access || profile.connection?.worldType || "Private"}</span>{profile.connection?.shareEnabled && <span className="chip" style={{ background: "var(--green)" }}>SHARING FILES</span>}{profile.connection?.rules?.passwordRequired && <span className="chip">PASSWORD</span>}{(profile.connection?.modBadges || []).map((badge) => <span className="chip" key={badge}>{badge}</span>)}{profile.connection?.modCount > 0 && <span className="chip">{profile.connection.modCount} REQUIRED</span>}</div></div>
      </div>
    </div>
    <p className="subtle">{profile.connection?.localWorld ? "This local World profile activates its assigned save and profile-owned files before opening Dragonwilds." : "Connect to authenticate and compare this World's declared files. Once synchronized, Join opens Dragonwilds through your selected platform."}</p>
    {!profile.connection?.localWorld && <div className="panel sync-connection-panel" style={{ borderColor: launchReady ? "var(--accent)" : "var(--line-strong)" }}>
      <div className="sync-section-heading"><div><span className="eyebrow">VERIFIED FILE SYNC</span><h2>This World's files, ready to play.</h2></div><span className="subtle">Check → sync → enter</span></div>
      <ClientSyncJourney stage={flowStage} job={syncJob} message={flowStep} error={flowError} skipDownload={skipDownload} transport={transport} share={playerShare} />
      <div className="world-sync-actions">
        <button className="btn btn-ghost" disabled={busy || !selectedInstall} onClick={connect}><Icon name="search" /> Check files</button>
        <button className="btn btn-primary" disabled={busy || !selectedInstall} onClick={sync}><Icon name="refresh" /> {busy ? "Working…" : flowError ? "Retry sync" : "Sync files"}</button>
        <button className="btn btn-ghost" disabled={busy || !launchReady || !result?.current} onClick={join}><Icon name="play" /> Review credentials &amp; enter World</button>
      </div>
      {!selectedInstall && <p className="subtle">Select a game installation in Launch &amp; profile settings below before syncing.</p>}
      <div className="subtle" style={{ marginTop: 5 }}>
        {playerShare ? "A player share provides files, not server login approval." : "Dragonwilds opens only after the server acknowledges your verified mod manifest."}
      </div>
      {launchReady && <>
        <div className="panel-inset" style={{ marginTop: 14, padding: 12, display: "grid", gap: 8 }}>
          <CopyField label="World Name" value={profile.display_name} onCopy={copyValue} />
          <CopyField label="Game Address" value={gameAddress(profile)} onCopy={copyValue} />
          <CopyField label="World Password" value={profile.connection?.password || ""} onCopy={copyValue} />
          <CopyField label="World Type" value={profile.connection?.worldType || "Private"} onCopy={copyValue} />
        </div>
      </>}
    </div>}
      {result && <div className="panel-inset" style={{ marginTop: 18, padding: 14 }}>
        <strong>{result.current ? "Managed mods are synchronized." : `${result.changes.length} file(s) need synchronization.`}</strong>
        {result.transport && <div className="subtle" style={{ marginTop: 6, fontSize: ".72rem" }}>{deliveryInfo(result.transport).label} delivery · {deliveryInfo(result.transport).detail}. All files are checked against the manifest.</div>}
        {!!result.units?.length && <div style={{ display: "grid", gap: 6, marginTop: 12 }}>
          {result.units.map((unit) => <div key={unit.key} className="panel" style={{ padding: ".65rem .75rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <div><strong style={{ fontSize: ".78rem" }}>{unit.name || unit.key}</strong><div className="subtle" style={{ fontSize: ".67rem" }}>{unit.fileCount} file(s) · {formatBytes(unit.bytes)} · {unit.clientRequired === false ? "optional" : "required"}</div></div>
            <span className="chip" style={{ background: unit.current ? "var(--green)" : "var(--line)" }}>{unit.current ? "CURRENT" : `${unit.changedFiles} TO SYNC`}</span>
          </div>)}
        </div>}
        {result.prerequisites && <div className="subtle" style={{ marginTop: 8 }}>Server prerequisites (install separately): UE4SS {result.prerequisites.ue4ss || "not declared"} · RuneSchema {result.prerequisites.runeSchema || "not declared"}</div>}
      </div>}
    <details className="panel world-launch-details" open={showSettings} onToggle={(event) => setSettingsOpen(event.currentTarget.open)}>
      <summary>Launch &amp; profile settings</summary>
    {showSettings && <div style={{ paddingTop: 20 }}>
      <div style={{ display: "grid", gap: 8 }}>
        <div><b>Steam lane</b><div className="subtle">{playLanes.steam || "Not configured in Application Setup"}</div></div>
        <div><b>Epic Games lane</b><div className="subtle">{playLanes.epic || "Not configured in Application Setup"}</div></div>
        <div><b>PC Game Pass lane</b><div className="subtle">{playLanes.gamepass || "Not configured in Application Setup"}</div></div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
        <b style={{ marginRight: 4 }}>Service</b>
        <button className={`btn ${selectedService === "steam" ? "btn-primary" : "btn-ghost"}`} disabled={busy} onClick={() => setService("steam")}>Steam</button>
        <button className={`btn ${selectedService === "epic" ? "btn-primary" : "btn-ghost"}`} disabled={busy} onClick={() => setService("epic")}>Epic Games</button>
        <button className={`btn ${selectedService === "gamepass" ? "btn-primary" : "btn-ghost"}`} disabled={busy} onClick={() => setService("gamepass")}>PC Game Pass</button>
      </div>
      <div className="panel-inset" style={{ marginTop: 14, padding: 12, display: "grid", gap: 8 }}>
        <strong>World launch locations</strong>
        <div className="subtle" style={{ fontSize: ".74rem" }}>Auto-detection checks the executable location and save folder. This World keeps its own paths, so another World can use a different storefront install.</div>
        <PathPicker disabled={busy} label="Game folder" value={locations.installDir} onChange={(value) => setLocations({ ...locations, installDir: value })} onBrowse={async () => { const value = await window.desktop?.pickDirectory?.(); if (value) setLocations({ ...locations, installDir: value }); }} />
        <PathPicker disabled={busy} label="Game executable" value={locations.executablePath} onChange={(value) => setLocations({ ...locations, executablePath: value })} onBrowse={async () => { const value = await window.desktop?.pickClientExecutable?.(); if (value) setLocations({ ...locations, executablePath: value }); }} />
        <PathPicker disabled={busy} label="World save folder" value={locations.savePath} onChange={(value) => setLocations({ ...locations, savePath: value })} onBrowse={async () => { const value = await window.desktop?.pickDirectory?.(); if (value) setLocations({ ...locations, savePath: value }); }} />
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}><button className="btn btn-ghost" disabled={busy} onClick={detectService}><span aria-hidden>◎</span> Detect &amp; Save</button><span className="subtle">{serviceName(selectedService)} · {profile.connection?.serviceDetection?.confidence || "legacy"} confidence</span></div>
      </div>
      <div className="panel-inset" style={{ marginTop: 12, padding: 12 }}>
        <strong>Profile-owned mods</strong>
        <div className="subtle" style={{ marginTop: 5 }}>Verified mods stay in this World profile and are projected into the selected game install only when this World is synchronized or launched. Hard links are preferred; protected or cross-drive installs use a reported fallback.</div>
        {profile.connection?.modDeployment && <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}><span className="chip">{profile.connection.modDeployment.mode}</span><span className="chip">{Number(profile.connection.modDeployment.hardlink || 0) + Number(profile.connection.modDeployment.symlink || 0)} linked</span>{profile.connection.modDeployment.copy > 0 && <span className="chip">{profile.connection.modDeployment.copy} copied fallback</span>}</div>}
      </div>
      <ClientSafeStoragePanel key={`${params.id}:${selectedInstall || ""}`} profileId={params.id} install={selectedInstall} localWorld={!!profile.connection?.localWorld} />
      <ProfileSavesPanel profileId={params.id} />
      <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
        <a className="btn btn-ghost" href="/setup">Application Setup</a>
        {profile.connection?.localWorld && <button className="btn btn-primary" disabled={busy || !selectedInstall} onClick={launchLocal}>{launching ? "Opening…" : "Activate Save & Launch"}</button>}
        <button className="btn btn-ghost" disabled={typeof window === "undefined" || !window.desktop?.createProfileShortcut} onClick={sendToDesktop}>Pin World to Desktop</button>
        {!profile.connection?.localWorld && <button className={profile.connection?.shareEnabled ? "btn btn-danger" : "btn btn-ghost"} disabled={sharing || busy} onClick={toggleShare}>{sharing ? "Updating…" : profile.connection?.shareEnabled ? "Stop Sharing" : "Share World Files"}</button>}
      </div>
      {profile.connection?.shareEnabled && <div className="panel-inset" style={{ marginTop: 14, padding: 12 }}>
        <strong>Player profile share is active</strong>
        <div className="subtle" style={{ marginTop: 5 }}>Friends search this computer&apos;s IP in Worlds → Connect to World, choose this player-owned World, and use the code below as the World password. Only the verified cached manifest files are shared; saves are never included.</div>
        <CopyField label="Share code" value={profile.connection.shareCode || ""} onCopy={copyValue} secret />
      </div>}

    </div>}
    </details>
    {credentialOpen && <CredentialWindow profile={profile} launching={launching} onCopy={copyValue} onClose={() => setCredentialOpen(false)} onLaunch={launchGame} />}
  </main>;
}

function summarizeUnits(manifest) {
  return (manifest?.units || []).map((unit) => ({ key: unit.key, name: unit.name, fileCount: unit.fileCount ?? unit.files?.length ?? 0, bytes: Number(unit.bytes || 0), clientRequired: unit.clientRequired !== false, current: true, changedFiles: 0 }));
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function serviceName(service) {
  if (service === "gamepass") return "PC Game Pass";
  if (service === "epic") return "Epic Games";
  return "Steam";
}

function gameAddress(profile) {
  const host = profile.connection?.address || profile.connection?.internalIp || profile.connection?.externalIp || "";
  const port = Number(profile.connection?.rules?.gamePort || profile.connection?.gamePort || 0);
  return host && port ? `${host}:${port}` : host;
}

function CredentialWindow({ profile, launching, onCopy, onClose, onLaunch }) {
  return <AppOverlay label="World credentials" labelledBy="world-credentials-title" onClose={onClose} dismissible={!launching}>
    <section className="panel credential-window">
      <header><div><span className="eyebrow">READY TO ENTER</span><h2 id="world-credentials-title">{profile.display_name}</h2></div><button className="btn btn-ghost" onClick={onClose} disabled={launching} aria-label="Close credentials">×</button></header>
      <p className="subtle">Keep this window beside Dragonwilds. The values are shown in plain text so you can paste them directly into the game.</p>
      <div className="panel-inset credential-fields">
        <CopyField label="World Name" value={profile.display_name} onCopy={onCopy} />
        <CopyField label="Game Address" value={gameAddress(profile)} onCopy={onCopy} />
        <CopyField label="World Password" value={profile.connection?.password || ""} onCopy={onCopy} />
        <CopyField label="World Type" value={profile.connection?.worldType || "Private"} onCopy={onCopy} />
      </div>
      <footer><button className="btn btn-ghost" onClick={onClose} disabled={launching}>Cancel</button><button className="btn btn-primary" disabled={launching} onClick={onLaunch}>{launching ? "Opening…" : "Launch Dragonwilds"}</button></footer>
    </section>
  </AppOverlay>;
}

function PathPicker({ label, value, onChange, onBrowse, disabled }) {
  return <div style={{ display: "grid", gridTemplateColumns: "120px minmax(0,1fr) auto", gap: 8, alignItems: "center" }}>
    <strong style={{ fontSize: ".76rem" }}>{label}</strong>
    <input className="input" disabled={disabled} aria-label={label} value={value || ""} onChange={(event) => onChange(event.target.value)} placeholder={`Select ${label.toLowerCase()}`} />
    <button type="button" className="btn btn-ghost" disabled={disabled} onClick={onBrowse}>Browse</button>
  </div>;
}


function CopyField({ label, value, onCopy }) {
  const shown = value || "Not available";
  return <div style={{ display: "grid", gridTemplateColumns: "120px minmax(0,1fr) auto", gap: 8, alignItems: "center" }}>
    <strong style={{ fontSize: ".78rem" }}>{label}</strong>
    <div className="panel" style={{ padding: ".55rem .7rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace" }}>
      {shown}
    </div>
    <button className="btn btn-ghost" disabled={!value} onClick={() => onCopy(label, value)}>Copy</button>
  </div>;
}
