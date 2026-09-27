"use client";
import { useEffect, useState } from "react";
import { api, toast } from "@/components/ui";

export default function PlayerProfile({ params }) {
  const [profile, setProfile] = useState(null);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);
  useEffect(() => { api(`/api/profiles/${params.id}`).then((r) => setProfile(r.profile)).catch((e) => toast(e.message, "error")); }, [params.id]);

  const verifyAndLaunch = async () => {
    setChecking(true); setResult(null);
    try {
      const response = await api(`/api/profiles/${params.id}/verify`, { method: "POST", body: {} });
      setResult(response.comparison);
      if (!response.comparison.current) return toast(`${response.comparison.changes.length} mod file(s) need synchronization before launch.`, "error");
      if (window.desktop?.openExternal) await window.desktop.openExternal("steam://run/1374490");
      else window.location.href = "steam://run/1374490";
      toast("Mods verified — launching Dragonwilds", "success");
    } catch (e) { toast(e.message, "error"); } finally { setChecking(false); }
  };
  const sendToDesktop = async () => {
    try { const path = await window.desktop.createProfileShortcut({ id: params.id, role: "player", name: profile.display_name }); toast(`Shortcut created: ${path}`, "success"); }
    catch (e) { toast(e.message, "error"); }
  };
  if (!profile) return <main style={{ padding: 32 }}>Loading World profile…</main>;
  return <main style={{ maxWidth: 820, margin: "0 auto", padding: 32 }}>
    <div className="eyebrow">PLAYER PROFILE</div><h1>{profile.display_name}</h1>
    <p className="subtle">Verify this World&apos;s retained mod manifest against your Dragonwilds installation, then launch the game.</p>
    <div className="panel" style={{ padding: 20, marginTop: 20 }}>
      <div><b>Game install</b><div className="subtle">{profile.client_install || "Not configured"}</div></div>
      <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
        <button className="btn btn-primary" disabled={checking || !profile.client_install} onClick={verifyAndLaunch}>{checking ? "Verifying…" : "Verify Mods & Launch"}</button>
        <button className="btn btn-ghost" disabled={typeof window === "undefined" || !window.desktop?.createProfileShortcut} onClick={sendToDesktop}>Send Player Launch to Desktop</button>
      </div>
      {result && !result.current && <div className="panel-inset" style={{ marginTop: 18, padding: 14 }}>{result.changes.length} file(s) require synchronization. Transfer/apply is the next migration slice; launch was safely stopped.</div>}
    </div>
  </main>;
}
