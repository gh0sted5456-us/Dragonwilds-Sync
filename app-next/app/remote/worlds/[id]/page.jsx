"use client";
// Guest world view. Mirrors app/worlds/[id]/page.jsx but renders ONLY the tabs this code
// was granted, and reuses the exact same panels — their API calls are scope/tab-checked
// server-side by the Remote Access guard, so nothing extra is needed here to keep a guest
// in bounds. A revoked/disabled/rescoped code ends the session on the next heartbeat.
import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { api, Icon, StatusChip, fmtUptime, fmtTime, toast } from "@/components/ui";
// Players remote view disabled for Dragonwilds (no remote player API)
// import PlayersPanel from "@/components/PlayersPanel";
import LogsPanel from "@/components/LogsPanel";
import SettingsEditor from "@/components/SettingsEditor";
import BackupsPanel from "@/components/BackupsPanel";
import SchedulePanel from "@/components/SchedulePanel";
import MapPanel from "@/components/MapPanel";
import ModsPanel from "@/components/ModsPanel";
import Ue4ssPanel from "@/components/Ue4ssPanel";
// PalSchemaPanel removed: reference deleted
import AdminPanel from "@/components/AdminPanel";
// Chat remote view disabled for Dragonwilds
// import ChatPanel from "@/components/ChatPanel";
// DeathsPanel removed for Dragonwilds
import BroadcastPanel from "@/components/BroadcastPanel";
// Discord remote view disabled for Dragonwilds
// import DiscordPanel from "@/components/DiscordPanel";
// import DiscordBotPanel from "@/components/DiscordBotPanel";

const ALL_TABS = [
  { id: "overview", labelKey: "world.tab.overview", icon: "grid" },
  // Players and Deaths tabs removed for Dragonwilds (unsupported by the game)
  { id: "map", labelKey: "world.tab.map", icon: "map" },
  { id: "broadcast", labelKey: "world.tab.broadcast", icon: "bell" },
  { id: "chat", labelKey: "world.tab.chat", icon: "chat" },
  { id: "console", labelKey: "world.tab.console", icon: "terminal" },
  { id: "settings", labelKey: "world.tab.settings", icon: "settings" },
  { id: "backups", labelKey: "world.tab.backups", icon: "download" },
  { id: "schedule", labelKey: "world.tab.schedule", icon: "clock" },
  { id: "mods", labelKey: "world.tab.mods", icon: "shield" },
  // Discord tabs removed for Dragonwilds
  // { id: "discord", labelKey: "world.tab.discord", icon: "bell" },
  // { id: "discordbot", labelKey: "world.tab.discordBot", icon: "chat" },
  { id: "admin", labelKey: "world.tab.admin", icon: "settings" },
];
const ACTION_TOAST = { start: "toast.worldStarted", stop: "toast.worldStopped", restart: "toast.worldRestarted" };

export default function RemoteWorldDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const router = useRouter();
  const [session, setSession] = useState(null); // { scope, worldId, tabs }
  const [data, setData] = useState(null);
  const [tab, setTab] = useState(null);
  const [busy, setBusy] = useState(null);

  // Heartbeat: keep the session alive and react to revoke / rescope live.
  useEffect(() => {
    let alive = true;
    const beat = () => fetch("/api/remote/session").then((r) => r.json()).then((r) => {
      if (!alive) return;
      if (!r || !r.ok || r.revoked) { toast(t("remote.accessEnded"), "error"); router.replace("/remote"); return; }
      if (r.scope === "world" && r.worldId && r.worldId !== id) { router.replace(`/remote/worlds/${r.worldId}`); return; }
      setSession(r);
    }).catch(() => {});
    beat();
    const hb = setInterval(beat, 6000);
    return () => { alive = false; clearInterval(hb); };
  }, [id, router, t]);

  const load = useCallback(async () => {
    try { setData(await api(`/api/worlds/${id}`)); }
    catch (e) { /* a 403 here means the code lost this world — heartbeat will redirect */ }
  }, [id]);

  useEffect(() => {
    load();
    const it = setInterval(load, 5000);
    return () => clearInterval(it);
  }, [load]);

  // Tabs this code may see, in the canonical order.
  const allowed = session ? ALL_TABS.filter((tb) => session.tabs.includes(tb.id)) : [];
  useEffect(() => {
    if (allowed.length && (!tab || !allowed.some((a) => a.id === tab))) setTab(allowed[0].id);
  }, [allowed, tab]);

  const canOverview = !!session && session.tabs.includes("overview");

  const act = async (action) => {
    setBusy(action);
    try {
      await api(`/api/worlds/${id}/action`, { method: "POST", body: { action } });
      toast(t(ACTION_TOAST[action] || "toast.worldStarted"), "success");
      setTimeout(load, 700);
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(null); }
  };

  if (!session) return <div className="subtle" style={{ fontWeight: 700 }}>{t("common.loading")}</div>;
  if (allowed.length === 0) return <div className="subtle" style={{ fontWeight: 700 }}>{t("remote.noTabs")}</div>;
  if (!data) return <div className="subtle" style={{ fontWeight: 700 }}>{t("common.loading")}</div>;

  const { world, live, events, sessions, schedules, backups } = data;
  const running = world.running;
  const goTo = (tid) => { if (allowed.some((a) => a.id === tid)) setTab(tid); };

  return (
    <div>
      {session.scope === "full" && (
        <a href="/remote/worlds" className="btn btn-ghost" style={{ marginBottom: "1rem" }}><Icon name="back" /> {t("remote.allWorlds")}</a>
      )}

      {/* Header */}
      <div className="panel" style={{ padding: "1.3rem 1.4rem", marginBottom: "1.2rem", borderTop: `3px solid ${world.accent_color || "var(--accent)"}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
          <div style={{ width: 50, height: 50, borderRadius: 12, background: world.icon_data ? "transparent" : (world.accent_color || "var(--yellow)"), display: "grid", placeItems: "center", overflow: "hidden", flexShrink: 0 }}>
            {world.icon_data ? <img src={world.icon_data} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : <Icon name="globe" size={26} />}
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
              <h1 className="heading" style={{ fontSize: "1.5rem", margin: 0 }}>{world.display_name}</h1>
              <StatusChip status={world.status} running={running} />
            </div>
          </div>
          {canOverview && (
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {running ? (
                <>
                  <button className="btn btn-ghost" disabled={busy} onClick={() => act("restart")}><Icon name="restart" /> {t("common.restart")}</button>
                  <button className="btn btn-danger" disabled={busy} onClick={() => act("stop")}><Icon name="stop" /> {t("common.stop")}</button>
                </>
              ) : (
                <button className="btn btn-primary" disabled={busy} onClick={() => act("start")}><Icon name="play" /> {busy === "start" ? t("common.starting") : t("common.start")}</button>
              )}
            </div>
          )}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px,1fr))", gap: "0.8rem", marginTop: "1.1rem" }}>
          <QuickStat label={t("common.players")} value={live?.metrics ? `${live.metrics.currentplayernum ?? live.players?.players?.length ?? 0}${live.metrics.maxplayernum ? "/" + live.metrics.maxplayernum : ""}` : "—"} />
          <QuickStat label={t("common.uptime")} value={live?.metrics ? fmtUptime(live.metrics.uptime) : "—"} />
          <QuickStat label={t("world.inGameDay")} value={live?.metrics?.days ?? "—"} />
          <QuickStat label={t("world.serverFps")} value={live?.metrics?.serverfps ?? "—"} />
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "0.4rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        {allowed.map((tb) => (
          <button key={tb.id} className={`btn ${tab === tb.id ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab(tb.id)}>
            <Icon name={tb.icon} size={16} /> {t(tb.labelKey)}
          </button>
        ))}
      </div>

      <div className="panel" style={{ padding: "1.3rem" }}>
        {tab === "overview" && <Overview t={t} events={events} sessions={sessions} />}
        {tab === "players" && <PlayersPanel worldId={id} players={live?.players} onChange={load} />}
        {tab === "deaths" && <DeathsPanel worldId={id} running={running} onGoToUe4ss={() => goTo("mods")} onGoToDiscord={() => goTo("discord")} />}
        {tab === "map" && <MapPanel players={live?.players} running={running} />}
        {tab === "broadcast" && (
          <div className="panel-inset">
            <div style={{ fontWeight: 800, fontSize: "0.9rem" }}>Broadcasts unavailable</div>
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.78rem" }}>
              The on-screen broadcast feature is Dragonwilds-specific and requires a community UE4SS mod which
              is not bundled. This panel has been disabled to avoid offering unsupported functionality.
            </p>
          </div>
        )}
        {tab === "chat" && <ChatPanel worldId={id} running={running} onGoToUe4ss={() => goTo("mods")} />}
        {tab === "console" && <LogsPanel worldId={id} />}
        {tab === "settings" && <SettingsEditor worldId={id} world={world} running={running} onGoToAdmin={() => goTo("admin")} />}
        {tab === "backups" && <BackupsPanel worldId={id} backups={backups} running={running} onChange={load} />}
        {tab === "schedule" && <SchedulePanel worldId={id} world={world} schedules={schedules} onChange={load} onGoToBroadcast={() => goTo("broadcast")} />}
        {tab === "mods" && (
          <div style={{ display: "grid", gap: "1.8rem" }}>
            <div>
              <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("world.modsWorkshop")}</h3>
              <ModsPanel worldId={id} running={running} />
            </div>
            <div style={{ borderTop: "1px solid var(--line)", paddingTop: "1.4rem" }}>
            <Ue4ssPanel worldId={id} running={running} />
            </div>
          </div>
        )}
        {tab === "discord" && <DiscordPanel world={world} onChange={load} />}
        {tab === "discordbot" && <DiscordBotPanel world={world} />}
        {tab === "admin" && <AdminPanel world={world} running={running} onChange={load} />}
      </div>
    </div>
  );
}

function QuickStat({ label, value }) {
  return (
    <div className="panel-inset" style={{ padding: "0.7rem 0.9rem" }}>
      <div className="heading" style={{ fontSize: "1.25rem" }}>{value}</div>
      <div className="subtle" style={{ fontSize: "0.66rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
    </div>
  );
}

function Overview({ t, events, sessions }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.4rem" }}>
      <div>
        <h3 className="heading" style={{ fontSize: "1rem", marginTop: 0 }}>{t("world.recentActivity")}</h3>
        <div style={{ display: "grid", gap: "0.35rem", maxHeight: 320, overflow: "auto" }}>
          {(!events || events.length === 0) ? <p className="subtle" style={{ fontWeight: 700 }}>{t("world.noEvents")}</p> :
            events.map((e) => (
              <div key={e.id} className="panel-inset" style={{ padding: "0.45rem 0.7rem", fontSize: "0.8rem" }}>
                <span className="chip" style={{ background: "var(--card-2)", border: "1px solid var(--line)", marginRight: 8 }}>{e.kind}</span>
                <span style={{ fontWeight: 700 }}>{e.message}</span>
                <div className="subtle" style={{ fontSize: "0.68rem", fontWeight: 700 }}>{fmtTime(e.created_at)}</div>
              </div>
            ))}
        </div>
      </div>
      <div>
        <h3 className="heading" style={{ fontSize: "1rem", marginTop: 0 }}>{t("world.joinLeaveHistory")}</h3>
        <div style={{ display: "grid", gap: "0.35rem", maxHeight: 320, overflow: "auto" }}>
          {(!sessions || sessions.length === 0) ? <p className="subtle" style={{ fontWeight: 700 }}>{t("world.noSessions")}</p> :
            sessions.map((s) => (
              <div key={s.id} className="panel-inset" style={{ padding: "0.45rem 0.7rem", fontSize: "0.8rem", display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontWeight: 800 }}>
                  <span className={s.event === "join" ? "s-running" : "s-crashed"}>{s.event === "join" ? "→ " : "← "}</span>
                  {s.player_name || s.user_id}
                </span>
                <span className="subtle" style={{ fontWeight: 700, fontSize: "0.72rem" }}>{fmtTime(s.created_at)}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
