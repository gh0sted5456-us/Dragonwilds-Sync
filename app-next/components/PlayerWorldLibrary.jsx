"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { createPortal } from "react-dom";
import { api, Icon, toast } from "@/components/ui";
import LocalWorldScanner from "@/components/LocalWorldScanner";
import { LayoutToggle, useLayoutPreference, RsdwBadge } from "@/components/LibraryChrome";

export default function PlayerWorldLibrary() {
  const [profiles, setProfiles] = useState([]);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [results, setResults] = useState([]);
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [installs, setInstalls] = useState({ steam: "", epic: "", gamepass: "" });
  const [platform, setPlatform] = useState("steam");
  const [finding, setFinding] = useState(false);
  const [searchKind, setSearchKind] = useState(null);
  const [discoveryMessage, setDiscoveryMessage] = useState("");
  const [checkingUpdates, setCheckingUpdates] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);
  const [localService, setLocalService] = useState("steam");
  const [contextMenu, setContextMenu] = useState(null);
  const [profileLayout, setProfileLayout] = useLayoutPreference("player");

  const loadProfiles = useCallback(() => api("/api/profiles").then((r) => setProfiles(r.profiles)).catch((e) => toast(e.message, "error")).finally(() => setProfilesLoading(false)), []);
  useEffect(() => {
    // Show the cached library immediately; a remote heartbeat must not gate it.
    void loadProfiles();
    api("/api/application-setup/play").then((r) => setInstalls({
      steam: r.play?.steam?.installDir || "",
      epic: r.play?.epic?.installDir || "",
      gamepass: r.play?.gamepass?.installDir || "",
    })).catch((e) => toast(e.message, "error"));
  }, [loadProfiles]);

  useEffect(() => {
    let stopped = false;
    const heartbeat = async () => {
      try {
        await api("/api/profiles/heartbeat", { method: "POST", body: {} });
        if (!stopped) await loadProfiles();
      } catch {
        // A failed monitor must not interrupt navigation or prevent cached
        // profiles from appearing.
        if (!stopped) await loadProfiles();
      }
    };
    void heartbeat();
    const timer = setInterval(heartbeat, 10 * 60 * 1000);
    return () => { stopped = true; clearInterval(timer); };
  }, [loadProfiles]);

  useEffect(() => {
    const close = () => setContextMenu(null);
    const escape = (event) => { if (event.key === "Escape") close(); };
    window.addEventListener("click", close);
    window.addEventListener("blur", close);
    window.addEventListener("keydown", escape);
    return () => { window.removeEventListener("click", close); window.removeEventListener("blur", close); window.removeEventListener("keydown", escape); };
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
        service: profile.connection?.service || profile.connection?.platform || "steam",
      });
      toast(`Desktop launcher created: ${shortcut}`, "success");
    } catch (e) { toast(e.message, "error"); }
  };

  const find = async (kind = "ip") => {
    if (finding || (kind === "ip" && !address.trim())) return;
    setFinding(true); setSearchKind(kind); setResults([]); setDiscoveryMessage("");
    try {
      const r = await api("/api/sync/discover", { method: "POST", body: { address: kind === "lan" ? "" : address.trim(), mode: kind } });
      setResults(r.worlds || []);
      setDiscoveryMessage(r.worlds?.length
        ? `${r.worlds.length} world(s) found${kind === "lan" ? " on your network" : " at this address"}. Download a manifest to add one to your library.`
        : kind === "lan" ? "No discoverable worlds found. The host must enable LAN discovery and allow UDP 27051 plus its Sync TCP port through the firewall. You can also enter its IP directly." : "No RSDW Sync worlds were published at that address.");
    } catch (e) { setDiscoveryMessage(e.message); toast(e.message, "error"); } finally { setFinding(false); setSearchKind(null); }
  };
  const downloadManifest = async (world) => {
    try {
      await api("/api/sync/import", { method: "POST", body: { address: world.queriedIp || address.trim(), syncPort: world.syncPort, worldId: world.worldId, password, service: platform } });
      toast(`${world.name || "World"} manifest downloaded.`, "success");
      await loadProfiles();
    } catch (e) { toast(e.message, "error"); }
  };
  const checkProfileUpdates = async () => {
    setCheckingUpdates(true);
    try {
      const result = await api("/api/profiles/updates", { method: "POST", body: {} });
      await loadProfiles();
      const detail = result.errors ? ` ${result.errors} World(s) could not be reached.` : "";
      toast(result.updates ? `${result.updates} World profile(s) have updated mod manifests.${detail}` : `All ${result.checked} connected World profile(s) are current.${detail}`, result.errors && !result.checked ? "error" : result.updates ? "info" : "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setCheckingUpdates(false); }
  };
  const remove = async (profile) => {
    try { await api(`/api/profiles/${profile.profile_id}`, { method: "DELETE" }); loadProfiles(); }
    catch (e) { toast(e.message, "error"); }
  };

  return <div>
    <header className="worlds-overview-header">
      <div className="worlds-overview-copy">
        <div>
          <div className="eyebrow">YOUR LIBRARY</div>
          <h1 className="heading">My Worlds</h1>
          <p className="subtle">Your saves and friends' worlds, each with its own mods and launch settings.</p>
        </div>
        <img className="dragonwilds-header-logo" src="/rsdw/dragonwilds-wordmark.png" alt="RuneScape Dragonwilds" />
      </div>
      <div className="worlds-overview-actions worlds-player-actions">
        <div className="library-view-controls">
        <LayoutToggle value={profileLayout} onChange={setProfileLayout} label="World view" />
        <span className="library-count">{profiles.length} saved world{profiles.length === 1 ? "" : "s"}</span>
        </div>
        <div className="library-action-group">
        <button className="btn btn-ghost" disabled={checkingUpdates} onClick={checkProfileUpdates}><Icon name="refresh" /> {checkingUpdates ? "Checking…" : "Check for Updates"}</button>
        <button className={`btn ${scanOpen ? "btn-primary" : "btn-ghost"}`} aria-expanded={scanOpen} onClick={() => { setConnectOpen(false); setScanOpen((open) => !open); }}><Icon name="search" /> {scanOpen ? "Close Scanner" : "Scan for Worlds"}</button>
        <button className="btn btn-primary" aria-expanded={connectOpen} onClick={() => { setScanOpen(false); setConnectOpen((open) => !open); }}>
          {connectOpen ? <span aria-hidden style={{ fontSize: "1.25rem", lineHeight: 1 }}>×</span> : <Icon name="globe" />} {connectOpen ? "Close" : "Connect to World"}
        </button>
        </div>
      </div>
    </header>
    {scanOpen && <LocalWorldScanner service={localService} onService={setLocalService} onClose={() => setScanOpen(false)} onCreated={loadProfiles} />}
    {connectOpen && <>
    {!installs.steam && !installs.epic && !installs.gamepass && <div className="panel" style={{ padding: "1rem", marginBottom: "1rem", border: "1px solid var(--yellow)" }}>
      <h2 className="heading" style={{ margin: "0 0 .35rem" }}>Play lanes are not configured</h2>
      <p className="subtle">Prepare Steam, Epic Games, PC Game Pass, or any combination under Application Setup. Each World remembers its own service and executable.</p>
      <Link className="btn btn-primary" href="/setup"><Icon name="settings" /> Open Application Setup</Link>
    </div>}
    <div className="panel" style={{ padding: "1rem", marginBottom: "1rem" }}>
      <div className="eyebrow">CONNECT A WORLD</div>
      <h2 className="heading" style={{ margin: ".25rem 0 .65rem", fontSize: "1.2rem" }}>Find your host</h2>
      <ol className="connection-flow" aria-label="Connection workflow"><li><span>1</span>Find the host</li><li><span>2</span>Download manifest</li><li><span>3</span>Sync, verify & launch</li></ol>
      <p className="subtle" style={{ margin: "0 0 .7rem" }}>Scan your local network, or enter a host IP. Add <code>:port</code> only when the host changed the default Sync port. Discovery never bypasses the world's password or verification.</p>
      <div className="connection-search">
        <input aria-label="Host IP address" value={address} onChange={(e) => setAddress(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && address.trim()) find("ip"); }} placeholder="Server IP — for example 203.0.113.25" style={fieldStyle} />
        <button className="btn btn-ghost" disabled={finding} onClick={() => find("lan")}><Icon name="globe" /> {searchKind === "lan" ? "Scanning LAN…" : "Scan LAN"}</button>
        <button className="btn btn-primary" disabled={finding || !address.trim()} onClick={() => find("ip")}><Icon name="search" /> {searchKind === "ip" ? "Searching…" : "Search IP"}</button>
      </div>
      <p className="subtle discovery-status" role="status" aria-live="polite">{finding ? searchKind === "lan" ? "Scanning network adapters and reading discovered host directories…" : "Reading the host directory…" : discoveryMessage}</p>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(210px,1fr) auto", gap: 8, marginBottom: 8 }}>
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" placeholder="World password (same password used in game)" style={fieldStyle} />
        <span />
      </div>
      <div className="panel-inset" style={{ padding: 10, display: "grid", gap: 6, marginBottom: 8 }}>
        <div><strong>Steam lane</strong> <span className="subtle">{installs.steam || "Not configured"}</span></div>
        <div><strong>Epic Games lane</strong> <span className="subtle">{installs.epic || "Not configured"}</span></div>
        <div><strong>Game Pass lane</strong> <span className="subtle">{installs.gamepass || "Not configured"}</span></div>
        <div><Link href="/setup" className="btn btn-ghost"><Icon name="settings" /> Application Setup</Link></div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <span className="subtle" style={{ alignSelf: "center", fontWeight: 700 }}>Launch with</span>
        <button className={`btn ${platform === "steam" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPlatform("steam")}>Steam</button>
        <button className={`btn ${platform === "epic" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPlatform("epic")}>Epic Games</button>
        <button className={`btn ${platform === "gamepass" ? "btn-primary" : "btn-ghost"}`} onClick={() => setPlatform("gamepass")}>PC Game Pass</button>
      </div>
      {results.length > 0 && <div style={{ display: "grid", gap: 8, marginTop: 12 }}>{results.map((world) => {
        const exists = profiles.some((p) => p.server_world_id === world.worldId && (p.connection?.address === world.queriedIp || p.connection?.internalIp === world.queriedIp));
        return <div className="panel-inset" key={`${world.worldId}:${world.queriedIp}:${world.syncPort}`} style={{ padding: 12, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <img src={world.identity?.iconData || "/icon.png"} alt="" style={{ width: 44, height: 44, borderRadius: 9, objectFit: "contain" }} />
          <div style={{ flex: 1, minWidth: 210 }}><strong>{world.name}</strong><div style={{ display: "flex", gap: 5, flexWrap: "wrap", margin: "4px 0" }}><RsdwBadge label={world.rules?.access || "Private"} /><RsdwBadge label={world.rules?.passwordRequired ? "PASSWORD" : "OPEN"} />{(world.modBadges || []).map((badge) => <RsdwBadge key={badge} label={badge} />)}</div><div className="subtle" style={{ fontSize: ".78rem" }}>{world.queriedIp}:{world.syncPort} · {world.modCount} required unit(s) · game port {world.rules?.gamePort || world.gamePort}</div></div>
          <button className="btn btn-primary" disabled={exists} onClick={() => downloadManifest(world)}>{exists ? "Manifest saved" : "Download Manifest"}</button>
        </div>;
      })}</div>}
    </div>
    </>}
    {profilesLoading ? <div className="panel-inset" role="status" style={{ padding: "2rem", color: "var(--ink-muted)" }}>Loading your worlds…</div> : profiles.length === 0 ? <section className="library-empty" aria-label="Add your first world"><span className="library-empty-symbol"><Icon name="globe" size={34} /></span><div className="eyebrow">READY WHEN YOU ARE</div><h2 className="heading">Make room for your next adventure.</h2><p className="subtle">Start with a save on this computer, or bring a friend's world into your library.</p><div className="library-empty-options"><button className="menu-card" onClick={() => { setConnectOpen(false); setScanOpen(true); }}><span className="menu-card-icon"><Icon name="search" /></span><span className="menu-card-copy"><strong>Find my local worlds</strong><small>Scan saves and create a managed world profile.</small></span><Icon name="chevronRight" /></button><button className="menu-card" onClick={() => { setScanOpen(false); setConnectOpen(true); }}><span className="menu-card-icon"><Icon name="globe" /></span><span className="menu-card-copy"><strong>Connect to a world</strong><small>Get the host's manifest and required mods.</small></span><Icon name="chevronRight" /></button></div></section> :
      <div className={profileLayout === "placards" ? "rsdw-placard-grid" : "rsdw-row-list"}>{profiles.map((p, index) => {
        const props = { key: p.profile_id, profile: p, index, installs, onRemove: remove, onContext: (e) => { e.preventDefault(); setContextMenu({ x: e.clientX, y: e.clientY, profile: p }); } };
        return profileLayout === "placards" ? <PlayerPlacard {...props} /> : <PlayerRow {...props} />;
      })}</div>}

    {contextMenu && createPortal(<div className="panel world-context-menu" role="menu" aria-label="World actions" style={{ left: `clamp(8px, ${contextMenu.x}px, calc(100vw - 246px))`, top: `clamp(var(--app-titlebar-height, 0px), ${contextMenu.y}px, calc(100dvh - 64px))` }}>
      <button className="btn btn-ghost" role="menuitem" style={{ width: "100%", justifyContent: "flex-start" }}
        onClick={() => { const p = contextMenu.profile; setContextMenu(null); sendProfileToDesktop(p); }}>
        <Icon name="download" size={16} /> Send to Desktop
      </button>
    </div>, document.body)}
  </div>;
}

const fieldStyle = { width: "100%", boxSizing: "border-box", border: "1px solid var(--line-strong)", borderRadius: 8, background: "var(--card-2)", color: "var(--ink)", padding: ".7rem .8rem", font: "inherit" };

function serviceName(service) { if (service === "gamepass") return "PC Game Pass"; if (service === "epic") return "Epic Games"; return "Steam"; }
function deliveryName(connection = {}) {
  if (connection.deliveryMode === "hybrid") return "HYBRID DELIVERY";
  if (connection.deliveryMode !== "cloud") return "DIRECT DELIVERY";
  if (connection.deliveryProvider === "google") return "GOOGLE DRIVE DELIVERY";
  if (connection.deliveryProvider === "onedrive") return "ONEDRIVE DELIVERY";
  if (connection.deliveryProvider === "dropbox") return "DROPBOX DELIVERY";
  return "CLOUD DELIVERY";
}
function PlayerBadges({ profile }) {
  return <div className="placard-badges">
    <RsdwBadge label="WORLD" />
    {profile.connection?.localWorld && <RsdwBadge label="LOCAL SAVE" />}
    {profile.connection?.manifestUpdate?.available && <RsdwBadge label="MOD UPDATE AVAILABLE" />}
    {profile.connection?.shareEnabled && <RsdwBadge label="SHARING FILES" />}
    {!profile.connection?.localWorld && <RsdwBadge label="MANIFEST SAVED" />}
    {!profile.connection?.localWorld && <RsdwBadge label={profile.connection?.hostingType === "managed" ? "MANAGED HOST" : profile.connection?.hostingType === "remote" ? "REMOTE / VPS" : "SELF-HOSTED"} />}
    {!profile.connection?.localWorld && <RsdwBadge label={deliveryName(profile.connection)} />}
    {profile.connection?.cachedModProfile?.files > 0 && <RsdwBadge label={`PROFILE CACHE · ${profile.connection.cachedModProfile.files}`} />}
    <RsdwBadge label={serviceName(profile.connection?.service || profile.connection?.platform).toUpperCase()} />
    <RsdwBadge label={profile.connection?.rules?.access || profile.connection?.worldType || "Private"} />
    {profile.connection?.rules?.passwordRequired && <RsdwBadge label="PASSWORD" />}
    {(profile.connection?.modBadges || []).map((badge) => <RsdwBadge key={badge} label={badge} />)}
    {profile.connection?.modCount > 0 && <RsdwBadge label={`${profile.connection.modCount} MODS`} />}
  </div>;
}

function HeartbeatStatus({ profile, compact = false }) {
  const heartbeat = profile.connection?.heartbeat;
  const stale = !heartbeat?.checkedAt || Date.now() - Number(heartbeat.checkedAt) > 20 * 60 * 1000;
  const state = stale ? "checking" : heartbeat.state;
  const label = state === "online" ? "Sync online" : state === "credentials" ? "Credentials need attention" : state === "offline" ? "Sync offline" : "Checking Sync status";
  return <span className={`world-heartbeat world-heartbeat-${state}`} title={`${label}${heartbeat?.latencyMs != null && !stale ? ` · ${heartbeat.latencyMs} ms` : ""}`} aria-label={label}>
    <span aria-hidden />{!compact && <small>{label}</small>}
  </span>;
}

function PlayerRow({ profile, index, installs, onRemove, onContext }) {
  const identity = profile.connection?.worldIdentity || {};
  const banner = identity.bannerData || `/rsdw/placards/${index % 9 + 1}.webp`;
  const icon = identity.iconData || "/icon.png";
  return <div className="panel world-card" onContextMenu={onContext} title="Right-click for World actions"
    style={{ position: "relative", isolation: "isolate", overflow: "hidden", padding: "1rem", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", minHeight: 76, borderColor: identity.accentColor || undefined }}>
    <div aria-hidden style={{ position: "absolute", inset: 0, zIndex: -2, background: `linear-gradient(90deg, color-mix(in srgb,var(--card) 94%,transparent) 35%, color-mix(in srgb,var(--card) 70%,transparent)), url("${banner}") center/cover`, opacity: .48 }} />
    <div style={{ position: "relative" }}><img src={icon} alt="" style={{ width: 48, height: 48, borderRadius: 10, objectFit: "cover", border: "1px solid var(--line-strong)" }} />{!profile.connection?.localWorld && <HeartbeatStatus profile={profile} compact />}</div>
    <div style={{ flex: 1, minWidth: 200 }}><strong className="heading">{profile.display_name}</strong><PlayerBadges profile={profile} /><div className="subtle" style={{ fontSize: ".78rem" }}>{profile.connection?.localWorld ? "Local save profile" : `${profile.connection?.address || profile.connection?.internalIp || "No address"}:${profile.connection?.syncPort || 4318}`} · {profile.client_install || installs[(profile.connection?.service || profile.connection?.platform || "steam")] || "Application Setup required"}</div></div>
    <Link className="btn btn-primary" href={`/profiles/${profile.profile_id}/player`}>{profile.connection?.localWorld ? "Open World" : "Sync"}</Link>
    <button className="btn btn-ghost" title="Remove profile" onClick={() => onRemove(profile)}><Icon name="trash" /></button>
  </div>;
}

function PlayerPlacard({ profile, index, installs, onRemove, onContext }) {
  const identity = profile.connection?.worldIdentity || {};
  const banner = identity.bannerData || `/rsdw/placards/${index % 9 + 1}.webp`;
  const icon = identity.iconData || "/icon.png";
  const endpoint = profile.connection?.localWorld ? "Local save profile" : `${profile.connection?.address || profile.connection?.internalIp || "No address"}:${profile.connection?.syncPort || 4318}`;
  return <article className="rsdw-placard" onContextMenu={onContext} title="Right-click for World actions" style={{ "--placard-accent": identity.accentColor || "var(--yellow)" }}>
    <div className="rsdw-placard-mode">{profile.connection?.localWorld ? "LOCAL WORLD" : "CONNECTED WORLD"}</div>{!profile.connection?.localWorld && <HeartbeatStatus profile={profile} />}
    <div className="rsdw-placard-media"><img src={banner} alt="" /><div /></div>
    <div className="rsdw-placard-body">
      <div className="rsdw-placard-identity"><img src={icon} alt="" /><div><h2>{profile.display_name}</h2><span>{endpoint}</span></div></div>
      <p>{identity.description || "A saved Dragonwilds World manifest ready to compare and synchronize."}</p>
      <PlayerBadges profile={profile} />
      <div className="rsdw-placard-detail"><span>PLAYER SERVICE</span><strong>{serviceName(profile.connection?.service || profile.connection?.platform)}</strong><small>{profile.client_install || installs[(profile.connection?.service || profile.connection?.platform || "steam")] || "Setup required"}</small></div>
    </div>
    <div className="rsdw-placard-actions"><Link className="btn btn-primary" href={`/profiles/${profile.profile_id}/player`}>{profile.connection?.localWorld ? "Open World" : "Sync World"}</Link><button className="btn btn-ghost" title="Remove profile" onClick={() => onRemove(profile)}><Icon name="trash" /></button></div>
  </article>;
}
