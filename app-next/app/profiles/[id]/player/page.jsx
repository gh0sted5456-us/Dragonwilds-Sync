"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, toast } from "@/components/ui";

export default function PlayerProfile({ params }) {
  const searchParams = useSearchParams();
  const autoplay = searchParams.get("autoplay") === "1";
  const autoStarted = useRef(false);
  const [profile, setProfile] = useState(null);
  const [playLanes, setPlayLanes] = useState({ steam: null, gamepass: null });
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);
  const [flowStep, setFlowStep] = useState(null);
  const [launchReady, setLaunchReady] = useState(false);
  useEffect(() => {
    Promise.all([api(`/api/profiles/${params.id}`), api("/api/application-setup/play")]).then(([profileResponse, installsResponse]) => {
      setProfile(profileResponse.profile);
      setPlayLanes({
        steam: installsResponse.play?.steam?.installDir || null,
        gamepass: installsResponse.play?.gamepass?.installDir || null,
      });
    }).catch((e) => toast(e.message, "error"));
  }, [params.id]);

  const refreshProfile = async () => {
    const latest = await api(`/api/profiles/${params.id}`);
    setProfile(latest.profile);
    return latest.profile;
  };

  const connect = async () => {
    setChecking(true); setResult(null);
    try {
      const response = await api(`/api/profiles/${params.id}/verify`, { method: "POST", body: {} });
      setResult({ ...response.comparison, prerequisites: response.manifest.prerequisites });
      await refreshProfile();
      toast(response.comparison.current ? "Connected — your managed mods match this World." : `${response.comparison.changes.length} mod file(s) need synchronization.`, response.comparison.current ? "success" : "info");
    } catch (e) { toast(e.message, "error"); } finally { setChecking(false); }
  };
  const sync = async () => {
    setChecking(true);
    try {
      const response = await api(`/api/profiles/${params.id}/sync`, { method: "POST", body: {} });
      const { installed, removed, manifest } = response.result;
      setResult({ current: true, changes: [], units: summarizeUnits(manifest), transport: manifest.transport, prerequisites: manifest.prerequisites });
      await refreshProfile();
      toast(`World synchronized: ${installed.length} installed or updated, ${removed.length} removed.`, "success");
    } catch (e) { toast(e.message, "error"); } finally { setChecking(false); }
  };
  const setPlatform = async (platform) => {
    try {
      const connection = { ...profile.connection, platform };
      delete connection.steamInstall;
      delete connection.gamepassInstall;
      const response = await api(`/api/profiles/${params.id}`, { method: "PATCH", body: { connection, client_install: null } });
      setProfile(response.profile);
      setResult(null);
    } catch (e) { toast(e.message, "error"); }
  };
  const join = async () => {
    if (!result?.current) return toast("Connect and synchronize this World before joining.", "error");
    const platform = profile.connection?.platform || "steam";
    const target = platform === "gamepass"
      ? "ms-windows-store://launch?productId=9P402RWR63H4"
      : "steam://run/1374490";
    try {
      if (!window.desktop?.openExternal) throw new Error("Joining is available in the Windows desktop app.");
      await window.desktop.openExternal(target);
      toast(`Opening Dragonwilds with ${platform === "gamepass" ? "PC Game Pass" : "Steam"}.`, "success");
    } catch (e) { toast(e.message, "error"); }
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
      const path = await window.desktop.createProfileShortcut({ id: params.id, role: "player", name: profile.display_name, iconData: identity.iconData || null });
      toast(`Shortcut created: ${path}`, "success");
    } catch (e) { toast(e.message, "error"); }
  };

  useEffect(() => {
    if (!autoplay || !profile || autoStarted.current) return;
    autoStarted.current = true;
    (async () => {
      setChecking(true);
      setLaunchReady(false);
      try {
        setFlowStep("Authenticating with World…");
        const verified = await api(`/api/profiles/${params.id}/verify`, { method: "POST", body: {} });
        setResult({ ...verified.comparison, prerequisites: verified.manifest.prerequisites });
        await refreshProfile();
        if (!verified.comparison.current) {
          setFlowStep(`Synchronizing ${verified.comparison.changes.length} managed file(s)…`);
          const synced = await api(`/api/profiles/${params.id}/sync`, { method: "POST", body: {} });
          setResult({ current: true, changes: [], units: summarizeUnits(synced.result.manifest), transport: synced.result.manifest.transport, prerequisites: synced.result.manifest.prerequisites });
          await refreshProfile();
        }
        setFlowStep("Authenticated and synchronized.");
        setLaunchReady(true);
      } catch (e) {
        setFlowStep("Connection could not be completed.");
        toast(e.message, "error");
      } finally {
        setChecking(false);
      }
    })();
  }, [autoplay, profile, params.id]);

  if (!profile) return <main style={{ padding: 32 }}>Loading World profile…</main>;
  const selectedInstall = (profile.connection?.platform || "steam") === "gamepass" ? playLanes.gamepass : playLanes.steam;
  const identity = profile.connection?.worldIdentity || {};
  return <main style={{ maxWidth: 820, margin: "0 auto", padding: 32 }}>
    <div style={{ position: "relative", minHeight: 112, marginBottom: 18, borderRadius: 14, overflow: "hidden", border: "1px solid var(--line-strong)", background: "var(--card)" }}>
      {identity.bannerData && <img src={identity.bannerData} alt="" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: .5 }} />}
      <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg,var(--card) 18%,transparent 80%)" }} />
      <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 14, padding: 18 }}>
        <img src={identity.iconData || "/rsdw/rsdwl-icon.webp"} alt="" style={{ width: 64, height: 64, borderRadius: 14, objectFit: "cover", border: "1px solid var(--line-strong)" }} />
        <div><div className="eyebrow">FRIEND WORLD</div><h1 style={{ margin: 0 }}>{profile.display_name}</h1></div>
      </div>
    </div>
    <p className="subtle">Connect to authenticate and compare this World&apos;s declared files. Once synchronized, Join opens Dragonwilds through your selected platform.</p>
    {autoplay && <div className="panel" style={{ padding: 16, marginTop: 18, borderColor: launchReady ? "var(--accent)" : "var(--line-strong)" }}>
      <strong>{flowStep || "Preparing World connection…"}</strong>
      <div className="subtle" style={{ marginTop: 5 }}>
        Desktop launch checks authentication and managed files first. Dragonwilds only opens after this confirmation.
      </div>
      {launchReady && <>
        <div className="panel-inset" style={{ marginTop: 14, padding: 12, display: "grid", gap: 8 }}>
          <CopyField label="World Name" value={profile.display_name} onCopy={copyValue} />
          <CopyField label="IP Address" value={profile.connection?.address || profile.connection?.internalIp || profile.connection?.externalIp || ""} onCopy={copyValue} />
          <CopyField label="World Password" value={profile.connection?.password || ""} onCopy={copyValue} secret />
          <CopyField label="World Type" value={profile.connection?.worldType || "Private"} onCopy={copyValue} />
        </div>
        <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={join}>Confirm &amp; Launch Dragonwilds</button>
      </>}
    </div>}
    <div className="panel" style={{ padding: 20, marginTop: 20 }}>
      <div style={{ display: "grid", gap: 8 }}>
        <div><b>Steam lane</b><div className="subtle">{playLanes.steam || "Not configured in Application Setup"}</div></div>
        <div><b>PC Game Pass lane</b><div className="subtle">{playLanes.gamepass || "Not configured in Application Setup"}</div></div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
        <b style={{ marginRight: 4 }}>Platform</b>
        <button className={`btn ${(profile.connection?.platform || "steam") === "steam" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPlatform("steam")}>Steam</button>
        <button className={`btn ${profile.connection?.platform === "gamepass" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPlatform("gamepass")}>PC Game Pass</button>
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
        <a className="btn btn-ghost" href="/setup">Application Setup</a>
        <button className="btn btn-ghost" disabled={checking || !selectedInstall} onClick={connect}>{checking ? "Connecting…" : "Connect"}</button>
        {!result?.current && <button className="btn btn-primary" disabled={checking || !selectedInstall} onClick={sync}>{checking ? "Synchronizing…" : "Resync Mods"}</button>}
        <button className="btn btn-primary" disabled={checking || !result?.current} onClick={join}>Join</button>
        <button className="btn btn-ghost" disabled={typeof window === "undefined" || !window.desktop?.createProfileShortcut} onClick={sendToDesktop}>Pin World to Desktop</button>
      </div>
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


function CopyField({ label, value, onCopy, secret = false }) {
  const shown = value || "Not available";
  return <div style={{ display: "grid", gridTemplateColumns: "120px minmax(0,1fr) auto", gap: 8, alignItems: "center" }}>
    <strong style={{ fontSize: ".78rem" }}>{label}</strong>
    <div className="panel" style={{ padding: ".55rem .7rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace" }}>
      {secret && value ? "••••••••" : shown}
    </div>
    <button className="btn btn-ghost" disabled={!value} onClick={() => onCopy(label, value)}>Copy</button>
  </div>;
}
