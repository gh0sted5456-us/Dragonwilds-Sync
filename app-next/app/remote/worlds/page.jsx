"use client";
// Full-scope guest: pick a world. (A per-world code is sent straight to its world instead
// and never lands here.) Reuses the world list API, which the guard filters by scope.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import Link from "next/link";
import { Icon, StatusChip } from "@/components/ui";

export default function RemoteWorlds() {
  const { t } = useTranslation();
  const router = useRouter();
  const [worlds, setWorlds] = useState(null);
  const [session, setSession] = useState(null);

  // Heartbeat: confirm the session is still valid; a per-world code skips to its world.
  useEffect(() => {
    let alive = true;
    const beat = () => fetch("/api/remote/session").then((r) => r.json()).then((r) => {
      if (!alive) return;
      if (!r || !r.ok || r.revoked) { router.replace("/remote"); return; }
      setSession(r);
      if (r.scope === "world" && r.worldId) router.replace(`/remote/worlds/${r.worldId}`);
    }).catch(() => {});
    beat();
    const id = setInterval(beat, 7000);
    return () => { alive = false; clearInterval(id); };
  }, [router]);

  useEffect(() => {
    const load = () => fetch("/api/worlds").then((r) => r.json()).then((r) => setWorlds(r.worlds || [])).catch(() => setWorlds([]));
    load();
    const id = setInterval(load, 6000);
    return () => clearInterval(id);
  }, []);

  const signOut = async () => {
    try { await fetch("/api/remote/session", { method: "DELETE" }); } catch {}
    router.replace("/remote");
  };

  if (!worlds) return <div className="subtle" style={{ fontWeight: 700 }}>{t("common.loading")}</div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
        <h1 className="heading" style={{ fontSize: "1.6rem", margin: 0 }}>{t("remote.worldsTitle")}</h1>
        <button className="btn btn-ghost" onClick={signOut}><Icon name="power" size={16} /> {t("remote.signOut")}</button>
      </div>

      {worlds.length === 0 ? (
        <p className="subtle" style={{ fontWeight: 700 }}>{t("remote.noWorldsGuest")}</p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px,1fr))", gap: "1rem" }}>
          {worlds.map((w) => (
            <Link key={w.world_id} href={`/remote/worlds/${w.world_id}`} className="panel" style={{
              padding: "1rem 1.1rem", textDecoration: "none", color: "inherit", display: "block",
              borderTop: `3px solid ${w.accent_color || "var(--accent)"}`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
                <div style={{ width: 42, height: 42, borderRadius: 10, background: w.icon_data ? "transparent" : (w.accent_color || "var(--yellow)"), display: "grid", placeItems: "center", overflow: "hidden", flexShrink: 0 }}>
                  {w.icon_data ? <img src={w.icon_data} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : <Icon name="globe" size={22} />}
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="heading" style={{ fontSize: "1rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{w.display_name}</div>
                  <div style={{ marginTop: 3 }}><StatusChip status={w.status} running={w.running} /></div>
                </div>
              </div>
              {w.live && (
                <div className="subtle" style={{ fontWeight: 700, fontSize: "0.74rem", marginTop: "0.7rem" }}>
                  {t("common.players")}: {w.live.currentPlayers ?? 0}{w.live.maxPlayers ? `/${w.live.maxPlayers}` : ""}
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
