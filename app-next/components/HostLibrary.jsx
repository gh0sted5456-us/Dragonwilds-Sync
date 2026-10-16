"use client";
import { useState, useCallback, useRef } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";
import { api, Icon, StatusChip, fmtUptime, toast } from "@/components/ui";
import CreateWorldModal from "@/components/CreateWorldModal";
import useAdaptivePolling from "@/components/useAdaptivePolling";
import LanDiscoveryPanel from "@/components/LanDiscoveryPanel";
import { LayoutToggle, useLayoutPreference, RsdwBadge } from "@/components/LibraryChrome";
const ACTION_TOAST = { start: "toast.worldStarted", stop: "toast.worldStopped", restart: "toast.worldRestarted" };

export default function HostLibrary() {
  const { t } = useTranslation();
  const [serverModeEnabled, setServerModeEnabled] = useState(false);
  const [worlds, setWorlds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [busy, setBusy] = useState({});
  const [checking, setChecking] = useState(false);
  const [activeServerId, setActiveServerId] = useState(null);
  const [serverLayout, setServerLayout] = useLayoutPreference("server");
  const serverModeRef = useRef(null);

  const load = useCallback(async () => {
    setLoadError("");
    try {
      let enabled = serverModeRef.current;
      if (enabled == null) {
        const settings = await api("/api/settings");
        enabled = settings.settings?.serverModeEnabled === true;
        serverModeRef.current = enabled;
        setServerModeEnabled(enabled);
      }
      if (!enabled) {
        setWorlds([]);
        setActiveServerId(null);
        return;
      }
      const [{ worlds }, active] = await Promise.all([api("/api/worlds"), api("/api/server-profile")]);
      setWorlds(worlds);
      setActiveServerId(active.activeId || null);
    } catch (e) { setLoadError(e.message); }
    finally { setLoading(false); }
  }, []);

  useAdaptivePolling(load, { visibleMs: 15000, hiddenMs: 60000, enabled: true });

  const doAction = async (id, action) => {
    setBusy((b) => ({ ...b, [id]: action }));
    try {
      if (action === "update") {
        await api(`/api/worlds/${id}/update`, { method: "POST" });
        try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {}
      }
      else await api(`/api/worlds/${id}/action`, { method: "POST", body: { action } });
      toast(action === "update" ? "Server update queued." : t(ACTION_TOAST[action] || "toast.worldStarted"), "success");
      setTimeout(load, 600);
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy((b) => ({ ...b, [id]: null })); }
  };

  const activateServer = async (id) => {
    setBusy((b) => ({ ...b, [id]: "activate" }));
    try {
      await api("/api/server-profile", { method: "POST", body: { worldId: id } });
      setActiveServerId(id);
      toast("Server profile activated. Its settings will be used for Start and Restart.", "success");
      load();
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy((b) => ({ ...b, [id]: null })); }
  };

  const checkUpdates = async () => {
    setChecking(true);
    try {
      const r = await api("/api/updates/check");
      toast(r.latest ? t("worlds.latestBuild", { build: r.latest, count: r.worlds.length }) : t("worlds.steamUnreachable"), r.latest ? "success" : "error");
      load();
    } catch (e) { toast(e.message, "error"); }
    finally { setChecking(false); }
  };

  const running = worlds.filter((w) => w.running).length;
  const players = worlds.reduce((a, w) => a + (w.live?.currentPlayers || 0), 0);

  return (
    <div>
      {loadError && <div className="panel" role="alert" style={{ padding: "1rem", marginBottom: "1rem" }}>Hosting could not be loaded: {loadError} <button className="btn btn-ghost" onClick={load}>Retry</button></div>}
      {serverModeEnabled ? <>
      <header className="worlds-overview-header">
        <div className="worlds-overview-copy">
          <div>
          <div className="eyebrow">MANAGED HOSTING</div>
          <h1 className="heading">Host</h1>
          <p className="subtle">
            Keep each server's world save, settings, mods, and delivery policy together.
          </p>
          </div>
          <img className="dragonwilds-header-logo" src="/rsdw/dragonwilds-wordmark.png" alt="RuneScape Dragonwilds" />
        </div>
        <div className="worlds-overview-actions">
          <div className="library-view-controls">
          <LayoutToggle value={serverLayout} onChange={setServerLayout} label="Server profile view" />
          <span className="library-count">{worlds.length} profile{worlds.length === 1 ? "" : "s"} · {running} running{worlds.some((w) => w.live?.currentPlayers != null) ? ` · ${players} players` : ""}</span>
          </div>
          <div className="library-action-group">
          <button className="btn btn-ghost" onClick={checkUpdates} disabled={checking}>
            <Icon name="refresh" /> {checking ? t("common.checking") : t("worlds.checkUpdates")}
          </button>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <Icon name="plus" /> New server
          </button>
          </div>
        </div>
      </header>
      <LanDiscoveryPanel />

      {loading ? (
        <div className="panel subtle" style={{ padding: "2rem", textAlign: "center" }}>{t("common.loading")}</div>
      ) : worlds.length === 0 ? (
        <EmptyState onCreate={() => setShowCreate(true)} />
      ) : (
        <div className={serverLayout === "placards" ? "rsdw-placard-grid" : "rsdw-row-list"}>
          {worlds.map((w) => (
            serverLayout === "placards"
              ? <WorldPlacard key={w.world_id} w={w} active={activeServerId === w.world_id} busy={busy[w.world_id]} onAction={doAction} onActivate={activateServer} />
              : <WorldRow key={w.world_id} w={w} active={activeServerId === w.world_id} busy={busy[w.world_id]} onAction={doAction} onActivate={activateServer} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateWorldModal onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); load(); }} />
      )}
      </> : loading ? <div className="panel" role="status" style={{ padding: "2rem" }}>Loading hosting preferences…</div> : !loadError && <>
        <section className="library-empty">
          <span className="library-empty-symbol"><Icon name="terminal" size={34} /></span>
          <div className="eyebrow">HOSTING IS OPTIONAL</div>
          <h1 className="heading">Host your own world.</h1>
          <p className="subtle">Enable server management to configure a dedicated server and its file delivery. Your player worlds stay separate.</p>
          <Link href="/settings?section=server" className="btn btn-primary"><Icon name="settings" /> Configure hosting</Link>
        </section>
        <LanDiscoveryPanel />
      </>}
    </div>
  );
}

function WorldPlacard({ w, active, busy, onAction, onActivate }) {
  const { t } = useTranslation();
  const isBusy = !!busy;
  const accent = w.accent_color || "var(--yellow)";
  const banner = w.banner_data || `/rsdw/placards/${Math.abs(String(w.world_id).length % 9) + 1}.webp`;
  return <article className="rsdw-placard" style={{ "--placard-accent": accent }}>
    <div className="rsdw-placard-mode">SERVER PROFILE · HOSTED WORLD</div>
    <div className="rsdw-placard-media"><img src={banner} alt="" /><div /></div>
    <div className="rsdw-placard-body">
      <div className="rsdw-placard-identity">
        <div className="rsdw-placard-icon"><img src={w.icon_data || "/icon.png"} alt="" /></div>
        <div><h2><Link href={`/worlds/${w.world_id}`}>{w.display_name}</Link></h2><span>Build {w.build_id || "unknown"} · Game port {w.game_port}</span></div>
      </div>
      <div className="placard-badges"><StatusChip status={w.status} running={w.running} />{active && <RsdwBadge label="ACTIVE PROFILE" />}{w.updateAvailable && <RsdwBadge label="UPDATE AVAILABLE" />}<RsdwBadge label={w.profileBadges?.host || (w.platform === "windows" ? "WINDOWS SERVER" : "LINUX SERVER")} />{w.profileBadges?.hosting && <RsdwBadge label={w.profileBadges.hosting} />}{w.profileBadges?.delivery && <RsdwBadge label={w.profileBadges.delivery} />}{(w.profileBadges?.platforms || []).map((label) => <RsdwBadge key={label} label={label} />)}{(w.profileBadges?.loaders || []).map((label) => <RsdwBadge key={label} label={label} />)}</div>
      <div className="rsdw-placard-stats"><Stat label={t("common.players")} value={w.live ? `${w.live.currentPlayers}${w.live.maxPlayers ? "/" + w.live.maxPlayers : ""}` : "—"} /><Stat label={t("common.uptime")} value={w.live ? fmtUptime(w.live.uptime) : "—"} /><Stat label={t("common.day")} value={w.live?.days ?? "—"} /></div>
    </div>
    <div className="rsdw-placard-actions">
      {!active && <button className="btn btn-ghost" disabled={isBusy || w.running} onClick={() => onActivate(w.world_id)}><Icon name="check" /> Activate</button>}
      <button className="btn btn-ghost" disabled={isBusy || w.running} onClick={() => onAction(w.world_id, "update")}><Icon name="download" /> Update</button>
      {w.running ? <><button className="btn btn-ghost" disabled={isBusy} onClick={() => onAction(w.world_id, "restart")}><Icon name="restart" /></button><button className="btn btn-danger" disabled={isBusy} onClick={() => onAction(w.world_id, "stop")}><Icon name="stop" /></button></> : <button className="btn btn-primary" disabled={isBusy} onClick={() => onAction(w.world_id, "start")}><Icon name="play" /> {busy === "start" ? t("common.starting") : t("common.start")}</button>}
      <Link href={`/worlds/${w.world_id}`} className="btn btn-ghost">{t("common.manage")}</Link>
    </div>
  </article>;
}

function WorldRow({ w, active, busy, onAction, onActivate }) {
  const { t } = useTranslation();
  const isBusy = !!busy;
  const accent = w.accent_color || "var(--accent)";
  return (
    <div className="panel world-card animate-floatUp" style={{ position: "relative", padding: "1rem 1.1rem", display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap", overflow: "hidden", borderLeft: `3px solid ${accent}` }}>
      {!w.banner_data && <div aria-hidden style={{ position: "absolute", inset: 0, background: `linear-gradient(90deg,var(--card) 20%,transparent),url('/rsdw/placards/${Math.abs(String(w.world_id).length % 9) + 1}.webp') center/cover`, opacity: .28 }} />}
      {/* banner: sits on the right, fades toward the center (|||| |  |) */}
      {w.banner_data && (
        <>
          <div aria-hidden style={{
            position: "absolute", inset: 0, zIndex: 0,
            backgroundImage: `url(${w.banner_data})`,
            backgroundSize: "cover", backgroundPosition: "left center",
            // fade from visible (left edge) to transparent (center) — |  | ||||
            WebkitMaskImage: "linear-gradient(to left, transparent 30%, rgba(0,0,0,0.35) 62%, rgba(0,0,0,0.75) 100%)",
            maskImage: "linear-gradient(to left, transparent 30%, rgba(0,0,0,0.35) 62%, rgba(0,0,0,0.75) 100%)",
            opacity: 0.85, pointerEvents: "none",
          }} />
          {/* left scrim keeps the icon + name readable over the banner */}
          <div aria-hidden style={{
            position: "absolute", inset: 0, zIndex: 0, pointerEvents: "none",
            background: "linear-gradient(to right, var(--card) 8%, color-mix(in srgb, var(--card) 55%, transparent) 34%, transparent 52%)",
          }} />
        </>
      )}

      <div style={{ position: "relative", zIndex: 1, width: 46, height: 46, borderRadius: 10, background: w.icon_data ? "transparent" : accent, border: `1px solid ${w.icon_data ? "transparent" : "var(--line)"}`, display: "grid", placeItems: "center", flexShrink: 0, overflow: "hidden", boxShadow: w.icon_data ? "0 2px 8px rgba(0,0,0,0.3)" : "none" }}>
        <img src={w.icon_data || "/icon.png"} alt="" style={{ width: w.icon_data ? "100%" : "82%", height: w.icon_data ? "100%" : "82%", objectFit: w.icon_data ? "cover" : "contain" }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, flex: 1, minWidth: 200 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
          <Link href={`/worlds/${w.world_id}`} className="heading" style={{ fontSize: "1.15rem", textDecoration: "none" }}>
            {w.display_name}
          </Link>
          <StatusChip status={w.status} running={w.running} />
          {active && <RsdwBadge label="ACTIVE SERVER PROFILE" />}
          {w.updateAvailable && (
            <span className="chip" style={{ background: "var(--yellow)", color: "#1e1f22" }}>{t("worlds.updateAvailable")}</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 6 }}>
          <RsdwBadge label={w.profileBadges?.host || (w.platform === "windows" ? "WINDOWS SERVER" : "LINUX SERVER")} />
          {w.profileBadges?.hosting && <RsdwBadge label={w.profileBadges.hosting} />}
          {w.profileBadges?.delivery && <RsdwBadge label={w.profileBadges.delivery} />}
          {(w.profileBadges?.platforms || []).map((label) => <RsdwBadge key={label} label={label} />)}
          {(w.profileBadges?.loaders || []).map((label) => <RsdwBadge key={label} label={label} />)}
        </div>
        <div className="subtle" style={{ fontSize: "0.78rem", fontWeight: 700, marginTop: 3 }}>
          {t("worlds.portsLine", { game: w.game_port, rest: w.rest_api_port, build: w.build_id || "—" })}
        </div>
      </div>

      <div style={{ position: "relative", zIndex: 1, display: "flex", gap: "1.4rem", textAlign: "center" }}>
        <Stat label={t("common.players")} value={w.live ? `${w.live.currentPlayers}${w.live.maxPlayers ? "/" + w.live.maxPlayers : ""}` : "—"} />
        <Stat label={t("common.uptime")} value={w.live ? fmtUptime(w.live.uptime) : "—"} />
        <Stat label={t("common.day")} value={w.live?.days ?? "—"} />
      </div>

      <div style={{ position: "relative", zIndex: 1, display: "flex", gap: "0.5rem", flexShrink: 0 }}>
        {!active && <button className="btn btn-ghost" disabled={isBusy || w.running} onClick={() => onActivate(w.world_id)} title="Load this profile's dedicated server settings"><Icon name="check" /> Activate</button>}
        <button className="btn btn-ghost" disabled={isBusy || w.running} onClick={() => onAction(w.world_id, "update")} title="Update server build">
          <Icon name="download" /> Update
        </button>
        {w.running ? (
          <>
            <button className="btn btn-ghost" disabled={isBusy} onClick={() => onAction(w.world_id, "restart")} title={t("common.restart")}>
              <Icon name="restart" />
            </button>
            <button className="btn btn-danger" disabled={isBusy} onClick={() => onAction(w.world_id, "stop")} title={t("common.stop")}>
              <Icon name="stop" />
            </button>
          </>
        ) : (
          <button className="btn btn-primary" disabled={isBusy} onClick={() => onAction(w.world_id, "start")} title={t("common.start")}>
            <Icon name="play" /> {busy === "start" ? t("common.starting") : t("common.start")}
          </button>
        )}
        <Link href={`/worlds/${w.world_id}`} className="btn btn-ghost">{t("common.manage")}</Link>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="heading" style={{ fontSize: "1.05rem" }}>{value}</div>
      <div className="subtle" style={{ fontSize: "0.66rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
    </div>
  );
}

function EmptyState({ onCreate }) {
  return (
    <section className="library-empty">
      <span className="library-empty-symbol"><Icon name="terminal" size={34} /></span>
      <div className="eyebrow">YOUR HOSTING WORKSPACE</div>
      <h2 className="heading">Host a world. Keep it yours.</h2>
      <p className="subtle">Create a dedicated profile for its save, settings, mods and file sharing. Server Core setup stays separate from your private profile.</p>
      <div className="library-empty-actions"><Link href="/setup" className="btn btn-ghost"><Icon name="settings" /> Configure Server Core</Link><button className="btn btn-primary" onClick={onCreate}><Icon name="plus" /> Create server profile</button></div>
    </section>
  );
}
