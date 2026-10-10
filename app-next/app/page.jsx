"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";
import { api, Icon, StatusChip, fmtUptime, toast } from "@/components/ui";
import CreateWorldModal from "@/components/CreateWorldModal";

const ACTION_TOAST = { start: "toast.worldStarted", stop: "toast.worldStopped", restart: "toast.worldRestarted" };

export default function WorldsPage() {
  const { t } = useTranslation();
  const [mode, setMode] = useState("player");
  const [worlds, setWorlds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [busy, setBusy] = useState({});
  const [checking, setChecking] = useState(false);
  const [activeServerId, setActiveServerId] = useState(null);

  const load = useCallback(async () => {
    try {
      const [{ worlds }, active] = await Promise.all([api("/api/worlds"), api("/api/server-profile")]);
      setWorlds(worlds);
      setActiveServerId(active.activeId || null);
    } catch (e) { toast(e.message, "error"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load]);

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
      <div className="panel" style={{ display: "flex", gap: 8, padding: 6, marginBottom: "1.2rem" }}>
        <ModeTab active={mode === "player"} onClick={() => setMode("player")} icon="users" label="My Worlds" detail="Find, connect & resync" />
        <ModeTab active={mode === "server"} onClick={() => setMode("server")} icon="terminal" label="Declarations" detail="Publish hosted Worlds" />
      </div>

      {mode === "player" ? <PlayerHub /> : <>
      <header style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: "1.2rem", flexWrap: "wrap", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <img src="/rsdw/dragonwilds-wordmark.png" alt="RuneScape Dragonwilds" style={{ width: 185, maxHeight: 58, objectFit: "contain" }} />
          <div>
          <h1 className="heading" style={{ fontSize: "1.9rem", margin: 0 }}>{t("worlds.title")}</h1>
          <p className="subtle" style={{ margin: "0.2rem 0 0", fontWeight: 700 }}>
            {t("worlds.summary", { count: worlds.length, running, players })}
          </p>
          </div>
        </div>
        <div style={{ display: "flex", gap: "0.6rem" }}>
          <button className="btn btn-ghost" onClick={checkUpdates} disabled={checking}>
            <Icon name="refresh" /> {checking ? t("common.checking") : t("worlds.checkUpdates")}
          </button>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <Icon name="plus" /> {t("worlds.newWorld")}
          </button>
        </div>
      </header>

      {loading ? (
        <div className="panel subtle" style={{ padding: "2rem", textAlign: "center" }}>{t("common.loading")}</div>
      ) : worlds.length === 0 ? (
        <EmptyState onCreate={() => setShowCreate(true)} />
      ) : (
        <div style={{ display: "grid", gap: "0.9rem" }}>
          {worlds.map((w) => (
            <WorldRow key={w.world_id} w={w} active={activeServerId === w.world_id} busy={busy[w.world_id]} onAction={doAction} onActivate={activateServer} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateWorldModal onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); load(); }} />
      )}
      </>}
    </div>
  );
}

function ModeTab({ active, onClick, icon, label, detail }) {
  return <button onClick={onClick} style={{ flex: 1, border: 0, borderRadius: 8, padding: "0.8rem 1rem", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 10, background: active ? "var(--accent)" : "transparent", color: active ? "var(--accent-ink)" : "var(--ink)" }}>
    <Icon name={icon} size={22} />
    <span style={{ textAlign: "left" }}><strong style={{ display: "block", fontSize: "1rem" }}>{label}</strong><small style={{ opacity: .78 }}>{detail}</small></span>
  </button>;
}

function PlayerHub() {
  const [profiles, setProfiles] = useState([]);
  const [results, setResults] = useState([]);
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [installs, setInstalls] = useState({ steam: "", gamepass: "" });
  const [platform, setPlatform] = useState("steam");
  const [finding, setFinding] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState(null);

  const loadProfiles = useCallback(() => api("/api/profiles").then((r) => setProfiles(r.profiles)).catch((e) => toast(e.message, "error")), []);
  useEffect(() => {
    loadProfiles();
    api("/api/application-setup/play").then((r) => setInstalls({
      steam: r.play?.steam?.installDir || "",
      gamepass: r.play?.gamepass?.installDir || "",
    })).catch((e) => toast(e.message, "error"));
  }, [loadProfiles]);

  useEffect(() => {
    const close = () => setContextMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("blur", close);
    return () => { window.removeEventListener("click", close); window.removeEventListener("blur", close); };
  }, []);

  const sendProfileToDesktop = async (profile) => {
    try {
      if (!window.desktop?.createProfileShortcut) throw new Error("Desktop shortcuts are available in the desktop app.");
      const identity = profile.connection?.worldIdentity || {};
      const shortcut = await window.desktop.createProfileShortcut({
        id: profile.profile_id,
        role: "player",
        name: profile.display_name,
        iconData: identity.iconData || null,
      });
      toast(`Desktop launcher created: ${shortcut}`, "success");
    } catch (e) { toast(e.message, "error"); }
  };

  const find = async () => {
    setFinding(true); setResults([]);
    try {
      const r = await api("/api/sync/discover", { method: "POST", body: { address: address.trim() } });
      setResults(r.worlds || []);
      if (!r.worlds?.length) toast("No RSDW Sync Worlds were published at that address.", "error");
    } catch (e) { toast(e.message, "error"); } finally { setFinding(false); }
  };
  const downloadManifest = async (world) => {
    try {
      await api("/api/sync/import", { method: "POST", body: { address: world.queriedIp || address.trim(), syncPort: world.syncPort, worldId: world.worldId, password, platform } });
      toast(`${world.name || "World"} manifest downloaded.`, "success");
      await loadProfiles();
    } catch (e) { toast(e.message, "error"); }
  };
  const remove = async (profile) => {
    try { await api(`/api/profiles/${profile.profile_id}`, { method: "DELETE" }); loadProfiles(); }
    catch (e) { toast(e.message, "error"); }
  };

  return <div>
    <header style={{ marginBottom: "1rem", display: "flex", gap: "1rem", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
      <div style={{ minWidth: 240, flex: 1 }}>
        <h1 className="heading" style={{ fontSize: "1.9rem", margin: 0 }}>Friends&apos; Worlds</h1>
        <p className="subtle" style={{ fontWeight: 700, marginBottom: 0 }}>Keep as many Worlds as you like. Connect, compare and resync only when you need to.</p>
      </div>
      <button className="btn btn-primary" onClick={() => setConnectOpen((open) => !open)}>
        {connectOpen ? <span aria-hidden style={{ fontSize: "1.25rem", lineHeight: 1 }}>×</span> : <Icon name="globe" />} {connectOpen ? "Close" : "Connect to World"}
      </button>
    </header>
    {connectOpen && <>
    {!installs.steam && !installs.gamepass && <div className="panel" style={{ padding: "1rem", marginBottom: "1rem", border: "1px solid var(--yellow)" }}>
      <h2 className="heading" style={{ margin: "0 0 .35rem" }}>Play lanes are not configured</h2>
      <p className="subtle">Prepare Steam, PC Game Pass, or both once under Application Setup. Player profiles only choose which prepared lane to use.</p>
      <Link className="btn btn-primary" href="/setup"><Icon name="settings" /> Open Application Setup</Link>
    </div>}
    <div className="panel" style={{ padding: "1rem", marginBottom: "1rem" }}>
      <h2 className="heading" style={{ margin: "0 0 .35rem", fontSize: "1.1rem" }}>Find a server</h2>
      <p className="subtle" style={{ margin: "0 0 .7rem" }}>Enter the host IP. Add <code>:port</code> only when the host changed the default Sync port. Search reads the server directory; Download Manifest verifies the password and saves its identity, rules, and required mods.</p>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(210px,1fr) auto", gap: 8, marginBottom: 8 }}>
        <input value={address} onChange={(e) => setAddress(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && address.trim()) find(); }} placeholder="Server IP — for example 203.0.113.25" style={fieldStyle} />
        <button className="btn btn-primary" disabled={finding || !address.trim()} onClick={find}><Icon name="refresh" /> {finding ? "Searching…" : "Search"}</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(210px,1fr) auto", gap: 8, marginBottom: 8 }}>
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" placeholder="World password (same password used in game)" style={fieldStyle} />
        <span />
      </div>
      <div className="panel-inset" style={{ padding: 10, display: "grid", gap: 6, marginBottom: 8 }}>
        <div><strong>Steam lane</strong> <span className="subtle">{installs.steam || "Not configured"}</span></div>
        <div><strong>Game Pass lane</strong> <span className="subtle">{installs.gamepass || "Not configured"}</span></div>
        <div><Link href="/setup" className="btn btn-ghost"><Icon name="settings" /> Application Setup</Link></div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <span className="subtle" style={{ alignSelf: "center", fontWeight: 700 }}>Launch with</span>
        <button className={`btn ${platform === "steam" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPlatform("steam")}>Steam</button>
        <button className={`btn ${platform === "gamepass" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPlatform("gamepass")}>PC Game Pass</button>
      </div>
      {results.length > 0 && <div style={{ display: "grid", gap: 8, marginTop: 12 }}>{results.map((world) => {
        const exists = profiles.some((p) => p.server_world_id === world.worldId && (p.connection?.address === world.queriedIp || p.connection?.internalIp === world.queriedIp));
        return <div className="panel-inset" key={`${world.worldId}:${world.queriedIp}:${world.syncPort}`} style={{ padding: 12, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <img src={world.identity?.iconData || "/rsdw/rsdwl-icon.webp"} alt="" style={{ width: 44, height: 44, borderRadius: 9, objectFit: "cover" }} />
          <div style={{ flex: 1, minWidth: 210 }}><strong>{world.name}</strong><div style={{ display: "flex", gap: 5, flexWrap: "wrap", margin: "4px 0" }}><RsdwBadge label={world.rules?.access || "Private"} /><RsdwBadge label={world.rules?.passwordRequired ? "PASSWORD" : "OPEN"} />{(world.modBadges || []).map((badge) => <RsdwBadge key={badge} label={badge} />)}</div><div className="subtle" style={{ fontSize: ".78rem" }}>{world.queriedIp}:{world.syncPort} · {world.modCount} required unit(s) · game port {world.rules?.gamePort || world.gamePort}</div></div>
          <button className="btn btn-primary" disabled={exists} onClick={() => downloadManifest(world)}>{exists ? "Manifest saved" : "Download Manifest"}</button>
        </div>;
      })}</div>}
    </div>
    </>}
    {profiles.length === 0 ? <div className="panel" style={{ padding: "2.2rem", textAlign: "center" }}><Icon name="users" size={34} /><h2 className="heading">No player servers yet</h2><p className="subtle">Choose Connect to World to discover a LAN broadcast or enter a server IP, then keep the Worlds you play on here.</p></div> :
      <div style={{ display: "grid", gap: 10 }}>{profiles.map((p, index) => {
        const identity = p.connection?.worldIdentity || {};
        const banner = identity.bannerData || `/rsdw/placards/${index % 9 + 1}.webp`;
        const icon = identity.iconData || portraitFor(p.profile_id);
        return <div className="panel" key={p.profile_id}
          onContextMenu={(e) => { e.preventDefault(); setContextMenu({ x: e.clientX, y: e.clientY, profile: p }); }}
          title="Right-click for World actions"
          style={{ position: "relative", isolation: "isolate", overflow: "hidden", padding: "1rem", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", minHeight: 76, borderColor: identity.accentColor || undefined }}>
        <div aria-hidden style={{ position: "absolute", inset: 0, zIndex: -2, background: `linear-gradient(90deg, color-mix(in srgb,var(--card) 94%,transparent) 35%, color-mix(in srgb,var(--card) 70%,transparent)), url("${banner}") center/cover`, opacity: .48 }} />
        <img src={icon} alt="" style={{ width: 48, height: 48, borderRadius: 10, objectFit: "cover", border: "1px solid var(--line-strong)" }} />
        <div style={{ flex: 1, minWidth: 200 }}><strong className="heading">{p.display_name}</strong><div style={{ display: "flex", gap: 5, flexWrap: "wrap", margin: "4px 0" }}><RsdwBadge label="MANIFEST SAVED" /><RsdwBadge label={(p.connection?.platform || "steam") === "gamepass" ? "GAME PASS" : "STEAM"} /><RsdwBadge label={p.connection?.rules?.access || p.connection?.worldType || "Private"} />{p.connection?.rules?.passwordRequired && <RsdwBadge label="PASSWORD" />}{(p.connection?.modBadges || []).map((b) => <RsdwBadge key={b} label={b} />)}{p.connection?.modCount > 0 && <RsdwBadge label={`${p.connection.modCount} MODS`} />}</div><div className="subtle" style={{ fontSize: ".78rem" }}>{p.connection?.address || p.connection?.internalIp || "No address"}:{p.connection?.syncPort || 4318} · {installs[(p.connection?.platform || "steam")] || "Application Setup required"}</div></div>
        <Link className="btn btn-primary" href={`/profiles/${p.profile_id}/player`}>Sync</Link>
        <button className="btn btn-ghost" title="Remove profile" onClick={() => remove(p)}><Icon name="trash" /></button>
      </div>})}</div>}

    {contextMenu && <div className="panel" style={{ position: "fixed", left: contextMenu.x, top: contextMenu.y, zIndex: 200, padding: 6, minWidth: 190, boxShadow: "0 10px 28px rgba(0,0,0,.35)" }}>
      <button className="btn btn-ghost" style={{ width: "100%", justifyContent: "flex-start" }}
        onClick={() => { const p = contextMenu.profile; setContextMenu(null); sendProfileToDesktop(p); }}>
        <Icon name="download" size={16} /> Send to Desktop
      </button>
    </div>}
  </div>;
}

const fieldStyle = { width: "100%", boxSizing: "border-box", border: "1px solid var(--line-strong)", borderRadius: 8, background: "var(--card-2)", color: "var(--ink)", padding: ".7rem .8rem", font: "inherit" };

const portraits = ["female_auburn_ponytail.webp", "female_cobalt_warrior_ponytail.webp", "female_dark_curls.webp", "female_teal_battlemage_braids.webp", "male_blond_undercut.webp", "male_dark_curls.webp", "male_forest_ranger_dreadlocks.webp", "androgynous_burgundy_battlemage.webp"];
function portraitFor(value = "") { let hash = 0; for (const c of value) hash = ((hash << 5) - hash + c.charCodeAt(0)) | 0; return `/rsdw/portraits/${portraits[Math.abs(hash) % portraits.length]}`; }
function RsdwBadge({ label }) { return <span style={{ display: "inline-flex", alignItems: "center", minHeight: 19, padding: "2px 7px", border: "1px solid color-mix(in srgb,var(--yellow) 45%,var(--line))", borderRadius: 999, background: "color-mix(in srgb,var(--yellow) 9%,var(--card))", color: "var(--yellow)", fontSize: ".62rem", fontWeight: 900, letterSpacing: ".045em" }}>{label}</span>; }

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
        {w.icon_data ? <img src={w.icon_data} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : <img src="/rsdw/dragonwilds-mark.png" alt="" style={{ width: "76%", height: "76%", objectFit: "contain" }} />}
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
  const { t } = useTranslation();
  return (
    <div className="panel" style={{ padding: "3rem 2rem", textAlign: "center" }}>
      <div style={{ width: 66, height: 66, borderRadius: 8, background: "var(--yellow)", display: "grid", placeItems: "center", margin: "0 auto 1rem" }}>
        <Icon name="globe" size={34} />
      </div>
      <h2 className="heading" style={{ fontSize: "1.4rem", margin: "0 0 0.4rem" }}>{t("worlds.emptyTitle")}</h2>
      <p className="subtle" style={{ fontWeight: 700, maxWidth: 460, margin: "0 auto 1.3rem" }}>
        {t("worlds.emptyBody")}
      </p>
      <button className="btn btn-primary" onClick={onCreate}><Icon name="plus" /> {t("worlds.createWorld")}</button>
    </div>
  );
}
