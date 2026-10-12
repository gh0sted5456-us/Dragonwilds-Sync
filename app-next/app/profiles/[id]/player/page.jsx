"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, Icon, toast } from "@/components/ui";
import ProfileSavesPanel from "@/components/ProfileSavesPanel";
import ClientSyncJourney from "@/components/ClientSyncJourney";
import { useJobsPoll } from "@/components/jobsClient";

export default function PlayerProfile({ params }) {
  const searchParams = useSearchParams();
  const autoplay = searchParams.get("autoplay") === "1";
  const autoStarted = useRef(false);
  const [profile, setProfile] = useState(null);
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
  const jobs = useJobsPoll();
  useEffect(() => {
    Promise.all([api(`/api/profiles/${params.id}`), api("/api/application-setup/play")]).then(([profileResponse, installsResponse]) => {
      setProfile(profileResponse.profile);
      setLocations({ installDir: profileResponse.profile.client_install || "", executablePath: profileResponse.profile.connection?.executablePath || "", savePath: profileResponse.profile.connection?.savePath || "" });
      setPlayLanes({
        steam: installsResponse.play?.steam?.installDir || null,
        epic: installsResponse.play?.epic?.installDir || null,
        gamepass: installsResponse.play?.gamepass?.installDir || null,
      });
    }).catch((e) => toast(e.message, "error"));
  }, [params.id]);

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
    setLaunchReady(true);
    setFlowStage("ready");
    setFlowStep("Server approved this manifest. Ready to enter.");
    return response.admission;
  };

  const connect = async () => {
    setChecking(true); setResult(null); setLaunchReady(false); setFlowError(null); setSkipDownload(false);
    setFlowStage("auth"); setFlowStep("Authenticating and downloading the World manifest…");
    try {
      const response = await api(`/api/profiles/${params.id}/verify`, { method: "POST", body: {} });
      setFlowStage("compare"); setFlowStep("Comparing the World manifest with your managed files…");
      setResult({ ...response.comparison, prerequisites: response.manifest.prerequisites });
      await refreshProfile();
      if (response.comparison.current) {
        setSkipDownload(true); setFlowStage("verify");
        await requestAdmission();
      } else {
        setFlowStage("download"); setFlowStep(`${response.comparison.changes.length} file(s) need syncing. Choose Resync Mods to continue.`);
      }
      toast(response.comparison.current ? "Connected — your managed mods match this World." : `${response.comparison.changes.length} mod file(s) need synchronization.`, response.comparison.current ? "success" : "info");
    } catch (e) { setFlowStage(null); setFlowError(e.message); toast(e.message, "error"); } finally { setChecking(false); }
  };
  const sync = async () => {
    setChecking(true); setLaunchReady(false); setFlowError(null); setSkipDownload(false);
    setFlowStage("auth"); setFlowStep("Connecting to the World and preparing managed downloads…");
    try {
      const request = api(`/api/profiles/${params.id}/sync`, { method: "POST", body: {} });
      setTimeout(() => { try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {} }, 250);
      const response = await request;
      const { installed, removed, manifest } = response.result;
      if (installed.length === 0) setSkipDownload(true);
      setResult({ current: true, changes: [], units: summarizeUnits(manifest), transport: manifest.transport, prerequisites: manifest.prerequisites });
      setFlowStage("verify"); setFlowStep("Downloaded files and the World profile have been verified.");
      await refreshProfile();
      await requestAdmission();
      toast(`World synchronized: ${installed.length} installed or updated, ${removed.length} removed.`, "success");
    } catch (e) { setFlowStage(null); setFlowError(e.message); toast(e.message, "error"); } finally { setChecking(false); }
  };
  const setService = async (service) => {
    try {
      const installDir = playLanes[service] || locations.installDir;
      const response = await api("/api/client-service", { method: "POST", body: { profileId: params.id, service, installDir, executablePath: installDir === locations.installDir ? locations.executablePath : "", savePath: locations.savePath, persist: true } });
      await refreshProfile();
      setLocations({ installDir: response.installation.installDir || "", executablePath: response.installation.executablePath || "", savePath: response.installation.savePath || "" });
      setResult(null);
      setLaunchReady(false); setFlowStage(null); setFlowError(null);
      toast(`${response.installation.label} identified for this World.`, "success");
    } catch (e) { toast(e.message, "error"); }
  };
  const detectService = async () => {
    try {
      const response = await api("/api/client-service", { method: "POST", body: { profileId: params.id, installDir: locations.installDir, executablePath: locations.executablePath, savePath: locations.savePath, persist: true } });
      await refreshProfile();
      setLocations({ installDir: response.installation.installDir || "", executablePath: response.installation.executablePath || "", savePath: response.installation.savePath || "" });
      setResult(null); setLaunchReady(false); setFlowStage(null); setFlowError(null);
      toast(`Detected ${response.installation.label} from the selected paths.`, "success");
    } catch (e) { toast(e.message, "error"); }
  };
  const join = async () => {
    if (!result?.current) return toast("Connect and synchronize this World before joining.", "error");
    try {
      setFlowError(null);
      await requestAdmission();
      const activated = await api(`/api/profiles/${params.id}/activate`, { method: "POST", body: {} });
      const linked = Number(activated.activation?.deployment?.hardlink || 0) + Number(activated.activation?.deployment?.symlink || 0);
      setPreparedLinks(linked);
      setCredentialOpen(true);
    } catch (e) { setFlowError(e.message); toast(e.message, "error"); }
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
      setLaunchReady(false);
      setFlowError(null); setFlowStage("auth"); setSkipDownload(false);
      try {
        setFlowStep("Authenticating with World…");
        const verified = await api(`/api/profiles/${params.id}/verify`, { method: "POST", body: {} });
        setResult({ ...verified.comparison, prerequisites: verified.manifest.prerequisites });
        setFlowStage("compare");
        await refreshProfile();
        if (!verified.comparison.current) {
          setFlowStage("download");
          setFlowStep(`Synchronizing ${verified.comparison.changes.length} managed file(s)…`);
          const request = api(`/api/profiles/${params.id}/sync`, { method: "POST", body: {} });
          setTimeout(() => { try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {} }, 250);
          const synced = await request;
          if (synced.result.installed.length === 0) setSkipDownload(true);
          setResult({ current: true, changes: [], units: summarizeUnits(synced.result.manifest), transport: synced.result.manifest.transport, prerequisites: synced.result.manifest.prerequisites });
          setFlowStage("verify");
          await refreshProfile();
        } else { setSkipDownload(true); setFlowStage("verify"); }
        await requestAdmission();
      } catch (e) {
        setFlowStep("Connection could not be completed.");
        setFlowStage(null);
        setFlowError(e.message);
        toast(e.message, "error");
      } finally {
        setChecking(false);
      }
    })();
  }, [autoplay, profile, params.id]);

  if (!profile) return <main style={{ padding: 32 }}>Loading World profile…</main>;
  const selectedService = profile.connection?.service || (profile.connection?.platform === "gamepass" ? "gamepass" : "steam");
  const selectedInstall = profile.client_install || playLanes[selectedService];
  const syncJob = checking ? jobs.find((job) => job.type === "sync" && job.worldId === params.id && job.status === "running") : null;
  const identity = profile.connection?.worldIdentity || {};
  return <main style={{ maxWidth: 820, margin: "0 auto", padding: 32 }}>
    <Link href="/?mode=player" className="page-back"><Icon name="back" /> Back to World Management</Link>
    <div style={{ position: "relative", minHeight: 112, marginBottom: 18, borderRadius: 14, overflow: "hidden", border: "1px solid var(--line-strong)", background: "var(--card)" }}>
      {identity.bannerData && <img src={identity.bannerData} alt="" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: .5 }} />}
      <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg,var(--card) 18%,transparent 80%)" }} />
      <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 14, padding: 18 }}>
        <img src={identity.iconData || "/icon.png"} alt="" style={{ width: 64, height: 64, borderRadius: 14, objectFit: identity.iconData ? "cover" : "contain", border: "1px solid var(--line-strong)" }} />
        <div><div className="eyebrow">ASSOCIATED WORLD</div><h1 style={{ margin: 0 }}>{profile.display_name}</h1><div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 6 }}><span className="chip">{profile.connection?.rules?.access || profile.connection?.worldType || "Private"}</span>{profile.connection?.shareEnabled && <span className="chip" style={{ background: "var(--green)" }}>SHARING FILES</span>}{profile.connection?.rules?.passwordRequired && <span className="chip">PASSWORD</span>}{(profile.connection?.modBadges || []).map((badge) => <span className="chip" key={badge}>{badge}</span>)}{profile.connection?.modCount > 0 && <span className="chip">{profile.connection.modCount} REQUIRED</span>}</div></div>
      </div>
    </div>
    <p className="subtle">{profile.connection?.localWorld ? "This local World profile activates its assigned save and profile-owned files before opening Dragonwilds." : "Connect to authenticate and compare this World's declared files. Once synchronized, Join opens Dragonwilds through your selected platform."}</p>
    {!profile.connection?.localWorld && <div className="panel" style={{ padding: 16, marginTop: 18, borderColor: launchReady ? "var(--accent)" : "var(--line-strong)" }}>
      <strong>World connection</strong>
      <div style={{ marginTop: 12 }}><ClientSyncJourney stage={flowStage} job={syncJob} message={flowStep} error={flowError} skipDownload={skipDownload} /></div>
      <div className="subtle" style={{ marginTop: 5 }}>
        Dragonwilds opens only after the server acknowledges your verified mod manifest.
      </div>
      {launchReady && <>
        <div className="panel-inset" style={{ marginTop: 14, padding: 12, display: "grid", gap: 8 }}>
          <CopyField label="World Name" value={profile.display_name} onCopy={copyValue} />
          <CopyField label="Game Address" value={gameAddress(profile)} onCopy={copyValue} />
          <CopyField label="World Password" value={profile.connection?.password || ""} onCopy={copyValue} />
          <CopyField label="World Type" value={profile.connection?.worldType || "Private"} onCopy={copyValue} />
        </div>
        <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={join}>Review credentials &amp; enter World</button>
      </>}
    </div>}
    <div className="panel" style={{ padding: 20, marginTop: 20 }}>
      <div style={{ display: "grid", gap: 8 }}>
        <div><b>Steam lane</b><div className="subtle">{playLanes.steam || "Not configured in Application Setup"}</div></div>
        <div><b>Epic Games lane</b><div className="subtle">{playLanes.epic || "Not configured in Application Setup"}</div></div>
        <div><b>PC Game Pass lane</b><div className="subtle">{playLanes.gamepass || "Not configured in Application Setup"}</div></div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
        <b style={{ marginRight: 4 }}>Service</b>
        <button className={`btn ${selectedService === "steam" ? "btn-primary" : "btn-ghost"}`} onClick={() => setService("steam")}>Steam</button>
        <button className={`btn ${selectedService === "epic" ? "btn-primary" : "btn-ghost"}`} onClick={() => setService("epic")}>Epic Games</button>
        <button className={`btn ${selectedService === "gamepass" ? "btn-primary" : "btn-ghost"}`} onClick={() => setService("gamepass")}>PC Game Pass</button>
      </div>
      <div className="panel-inset" style={{ marginTop: 14, padding: 12, display: "grid", gap: 8 }}>
        <strong>World launch locations</strong>
        <div className="subtle" style={{ fontSize: ".74rem" }}>Auto-detection checks the executable location and save folder. This World keeps its own paths, so another World can use a different storefront install.</div>
        <PathPicker label="Game folder" value={locations.installDir} onChange={(value) => setLocations({ ...locations, installDir: value })} onBrowse={async () => { const value = await window.desktop?.pickDirectory?.(); if (value) setLocations({ ...locations, installDir: value }); }} />
        <PathPicker label="Game executable" value={locations.executablePath} onChange={(value) => setLocations({ ...locations, executablePath: value })} onBrowse={async () => { const value = await window.desktop?.pickClientExecutable?.(); if (value) setLocations({ ...locations, executablePath: value }); }} />
        <PathPicker label="World save folder" value={locations.savePath} onChange={(value) => setLocations({ ...locations, savePath: value })} onBrowse={async () => { const value = await window.desktop?.pickDirectory?.(); if (value) setLocations({ ...locations, savePath: value }); }} />
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}><button className="btn btn-ghost" onClick={detectService}><span aria-hidden>◎</span> Detect &amp; Save</button><span className="subtle">{serviceName(selectedService)} · {profile.connection?.serviceDetection?.confidence || "legacy"} confidence</span></div>
      </div>
      <div className="panel-inset" style={{ marginTop: 12, padding: 12 }}>
        <strong>Profile-owned mods</strong>
        <div className="subtle" style={{ marginTop: 5 }}>Verified mods stay in this World profile and are projected into the selected game install only when this World is synchronized or launched. Hard links are preferred; protected or cross-drive installs use a reported fallback.</div>
        {profile.connection?.modDeployment && <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}><span className="chip">{profile.connection.modDeployment.mode}</span><span className="chip">{Number(profile.connection.modDeployment.hardlink || 0) + Number(profile.connection.modDeployment.symlink || 0)} linked</span>{profile.connection.modDeployment.copy > 0 && <span className="chip">{profile.connection.modDeployment.copy} copied fallback</span>}</div>}
      </div>
      <ProfileSavesPanel profileId={params.id} />
      <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
        <a className="btn btn-ghost" href="/setup">Application Setup</a>
        {profile.connection?.localWorld ? <button className="btn btn-primary" disabled={launching || !selectedInstall} onClick={launchLocal}>{launching ? "Opening…" : "Activate Save & Launch"}</button> : <><button className="btn btn-ghost" disabled={checking || !selectedInstall} onClick={connect}>{checking ? "Connecting…" : "Connect"}</button><button className={result?.current ? "btn btn-ghost" : "btn btn-primary"} disabled={checking || !selectedInstall} onClick={sync}>{checking ? "Synchronizing…" : result?.current ? "Refresh Profile Mods" : "Resync Mods"}</button><button className="btn btn-primary" disabled={checking || !result?.current} onClick={join}>Join</button></>}
        <button className="btn btn-ghost" disabled={typeof window === "undefined" || !window.desktop?.createProfileShortcut} onClick={sendToDesktop}>Pin World to Desktop</button>
        {!profile.connection?.localWorld && <button className={profile.connection?.shareEnabled ? "btn btn-danger" : "btn btn-ghost"} disabled={sharing} onClick={toggleShare}>{sharing ? "Updating…" : profile.connection?.shareEnabled ? "Stop Sharing" : "Share World Files"}</button>}
      </div>
      {profile.connection?.shareEnabled && <div className="panel-inset" style={{ marginTop: 14, padding: 12 }}>
        <strong>Player profile share is active</strong>
        <div className="subtle" style={{ marginTop: 5 }}>Friends search this computer&apos;s IP in Profiles, choose this player-owned World, and use the code below as the World password. Only the verified cached manifest files are shared; saves are never included.</div>
        <CopyField label="Share code" value={profile.connection.shareCode || ""} onCopy={copyValue} secret />
      </div>}
      {result && <div className="panel-inset" style={{ marginTop: 18, padding: 14 }}>
        <strong>{result.current ? "Managed mods are synchronized." : `${result.changes.length} file(s) need synchronization.`}</strong>
        {result.transport && <div className="subtle" style={{ marginTop: 6, fontSize: ".72rem" }}>Delivery: authenticated TCP connection with expiring direct-download links and SHA-256 verification.</div>}
        {!!result.units?.length && <div style={{ display: "grid", gap: 6, marginTop: 12 }}>
          {result.units.map((unit) => <div key={unit.key} className="panel" style={{ padding: ".65rem .75rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <div><strong style={{ fontSize: ".78rem" }}>{unit.name || unit.key}</strong><div className="subtle" style={{ fontSize: ".67rem" }}>{unit.fileCount} file(s) · {formatBytes(unit.bytes)} · {unit.clientRequired === false ? "optional" : "required"}</div></div>
            <span className="chip" style={{ background: unit.current ? "var(--green)" : "var(--line)" }}>{unit.current ? "CURRENT" : `${unit.changedFiles} TO SYNC`}</span>
          </div>)}
        </div>}
        {result.prerequisites && <div className="subtle" style={{ marginTop: 8 }}>Server prerequisites (install separately): UE4SS {result.prerequisites.ue4ss || "not declared"} · RuneSchema {result.prerequisites.runeSchema || "not declared"}</div>}
      </div>}
    </div>
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
  return <div className="credential-overlay" role="dialog" aria-modal="true" aria-labelledby="world-credentials-title" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="panel credential-window">
      <header><div><span className="eyebrow">READY TO ENTER</span><h2 id="world-credentials-title">{profile.display_name}</h2></div><button className="btn btn-ghost" onClick={onClose} aria-label="Close credentials">×</button></header>
      <p className="subtle">Keep this window beside Dragonwilds. The values are shown in plain text so you can paste them directly into the game.</p>
      <div className="panel-inset credential-fields">
        <CopyField label="World Name" value={profile.display_name} onCopy={onCopy} />
        <CopyField label="Game Address" value={gameAddress(profile)} onCopy={onCopy} />
        <CopyField label="World Password" value={profile.connection?.password || ""} onCopy={onCopy} />
        <CopyField label="World Type" value={profile.connection?.worldType || "Private"} onCopy={onCopy} />
      </div>
      <footer><button className="btn btn-ghost" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={launching} onClick={onLaunch}>{launching ? "Opening…" : "Launch Dragonwilds"}</button></footer>
    </section>
  </div>;
}

function PathPicker({ label, value, onChange, onBrowse }) {
  return <div style={{ display: "grid", gridTemplateColumns: "120px minmax(0,1fr) auto", gap: 8, alignItems: "center" }}>
    <strong style={{ fontSize: ".76rem" }}>{label}</strong>
    <input className="input" aria-label={label} value={value || ""} onChange={(event) => onChange(event.target.value)} placeholder={`Select ${label.toLowerCase()}`} />
    <button type="button" className="btn btn-ghost" onClick={onBrowse}>Browse</button>
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
