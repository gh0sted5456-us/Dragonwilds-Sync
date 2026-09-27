"use client";
import { useEffect, useState } from "react";
import { api, toast } from "@/components/ui";

export default function PlayerProfile({ params }) {
  const [profile, setProfile] = useState(null);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);
  useEffect(() => { api(`/api/profiles/${params.id}`).then((r) => setProfile(r.profile)).catch((e) => toast(e.message, "error")); }, [params.id]);

  const connect = async () => {
    setChecking(true); setResult(null);
    try {
      const response = await api(`/api/profiles/${params.id}/verify`, { method: "POST", body: {} });
      setResult({ ...response.comparison, prerequisites: response.manifest.prerequisites });
      toast(response.comparison.current ? "Connected — your managed mods match this World." : `${response.comparison.changes.length} mod file(s) need synchronization.`, response.comparison.current ? "success" : "info");
    } catch (e) { toast(e.message, "error"); } finally { setChecking(false); }
  };
  const sync = async () => {
    setChecking(true);
    try {
      const response = await api(`/api/profiles/${params.id}/sync`, { method: "POST", body: {} });
      const { installed, removed, manifest } = response.result;
      setResult({ current: true, changes: [], prerequisites: manifest.prerequisites });
      toast(`World synchronized: ${installed.length} installed or updated, ${removed.length} removed.`, "success");
    } catch (e) { toast(e.message, "error"); } finally { setChecking(false); }
  };
  const chooseInstall = async () => {
    try {
      const selected = await window.desktop?.pickDirectory?.();
      if (!selected) return;
      const response = await api(`/api/profiles/${params.id}`, { method: "PATCH", body: { client_install: selected } });
      setProfile(response.profile);
    } catch (e) { toast(e.message, "error"); }
  };
  const setPlatform = async (platform) => {
    try {
      const response = await api(`/api/profiles/${params.id}`, { method: "PATCH", body: { connection: { ...profile.connection, platform } } });
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
  const sendToDesktop = async () => {
    try { const path = await window.desktop.createProfileShortcut({ id: params.id, role: "player", name: profile.display_name }); toast(`Shortcut created: ${path}`, "success"); }
    catch (e) { toast(e.message, "error"); }
  };
  if (!profile) return <main style={{ padding: 32 }}>Loading World profile…</main>;
  return <main style={{ maxWidth: 820, margin: "0 auto", padding: 32 }}>
    <div className="eyebrow">FRIEND WORLD</div><h1>{profile.display_name}</h1>
    <p className="subtle">Connect to compare this World&apos;s declared mods. Once synchronized, Join opens Dragonwilds through your selected platform.</p>
    <div className="panel" style={{ padding: 20, marginTop: 20 }}>
      <div><b>Dragonwilds install</b><div className="subtle">{profile.client_install || "Not configured"}</div></div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
        <b style={{ marginRight: 4 }}>Platform</b>
        <button className={`btn ${(profile.connection?.platform || "steam") === "steam" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPlatform("steam")}>Steam</button>
        <button className={`btn ${profile.connection?.platform === "gamepass" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPlatform("gamepass")}>PC Game Pass</button>
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
        <button className="btn btn-ghost" onClick={chooseInstall}>Select Game Install</button>
        <button className="btn btn-ghost" disabled={checking || !profile.client_install} onClick={connect}>{checking ? "Connecting…" : "Connect"}</button>
        {!result?.current && <button className="btn btn-primary" disabled={checking || !profile.client_install} onClick={sync}>{checking ? "Synchronizing…" : "Resync Mods"}</button>}
        <button className="btn btn-primary" disabled={checking || !result?.current} onClick={join}>Join</button>
        <button className="btn btn-ghost" disabled={typeof window === "undefined" || !window.desktop?.createProfileShortcut} onClick={sendToDesktop}>Pin World to Desktop</button>
      </div>
      {result && <div className="panel-inset" style={{ marginTop: 18, padding: 14 }}>
        <strong>{result.current ? "Managed mods are synchronized." : `${result.changes.length} file(s) need synchronization.`}</strong>
        {result.prerequisites && <div className="subtle" style={{ marginTop: 8 }}>Server prerequisites (install separately): UE4SS {result.prerequisites.ue4ss || "not declared"} · RuneSchema {result.prerequisites.runeSchema || "not declared"}</div>}
      </div>}
    </div>
  </main>;
}
