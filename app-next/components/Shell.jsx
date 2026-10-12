"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslation } from "react-i18next";
import { Icon, registerToast, toast } from "@/components/ui";
import { useJobsPoll, summarize, ProgressBar } from "@/components/jobsClient";

// labelKey resolves through t() at render time — NAV is a module-level const, so it
// can't call the translation hook itself.
const NAV = [
  { href: "/", asset: "/rsdw/dragonwilds-mark.png", label: "Worlds", match: (p) => p === "/" || p.startsWith("/worlds") || p.startsWith("/profiles") },
  { href: "/socials", material: "discord", label: "Socials", match: (p) => p.startsWith("/socials") },
  { href: "/settings", material: "settings", label: "Settings", match: (p) => p.startsWith("/settings") || p.startsWith("/setup") || p.startsWith("/remote-access") || p.startsWith("/usage") },
];

const MATERIAL_NAV = {
  sync: "M7.41 13.41 6 12l-4 4 4 4 1.41-1.41L5.83 17H13v-2H5.83l1.58-1.59zM16.59 10.59 18 12l4-4-4-4-1.41 1.41L18.17 7H11v2h7.17l-1.58 1.59z",
  activity: "M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z",
  settings: "M19.43 12.98c.04-.32.07-.65.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.37-.31-.6-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98L14.5 2.42C14.47 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42L9.13 5.07c-.61.25-1.17.58-1.69.98l-2.49-1c-.23-.09-.48 0-.6.22l-2 3.46c-.12.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.37.31.6.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.58 1.69-.98l2.49 1c.23.09.48 0 .6-.22l2-3.46c.12-.22.07-.49-.12-.64zM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5z",
  downloads: "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
  discord: "M19.5 5.3A16.3 16.3 0 0 0 15.4 4l-.5 1a15 15 0 0 0-5.8 0l-.5-1a16.3 16.3 0 0 0-4.1 1.3C1.9 9.1 1.2 12.8 1.5 16.4A16.6 16.6 0 0 0 6.6 19l1.2-1.6a10.5 10.5 0 0 1-1.8-.9l.4-.3c3.5 1.6 7.7 1.6 11.2 0l.4.3c-.6.4-1.2.7-1.8.9l1.2 1.6a16.6 16.6 0 0 0 5.1-2.6c.4-4.2-.7-7.8-3-11.1zM8.6 14.5c-1 0-1.9-1-1.9-2.2s.8-2.2 1.9-2.2 1.9 1 1.9 2.2-.9 2.2-1.9 2.2zm6.8 0c-1 0-1.9-1-1.9-2.2s.8-2.2 1.9-2.2 1.9 1 1.9 2.2-.9 2.2-1.9 2.2z",
};

function MaterialNavIcon({ name, size = 22 }) {
  const d = MATERIAL_NAV[name];
  return <svg aria-hidden viewBox="0 0 24 24" width={size} height={size} fill="currentColor"><path d={d} /></svg>;
}

export default function Shell({ children }) {
  const { t } = useTranslation();
  const path = usePathname();
  const [toasts, setToasts] = useState([]);
  const [collapsed, setCollapsed] = useState(false);
  const [ver, setVer] = useState(null);
  const [appUpdate, setAppUpdate] = useState({ stage: "idle", percent: null, error: "" });
  const [componentUpdates, setComponentUpdates] = useState(null);
  const [launcherProfiles, setLauncherProfiles] = useState({ profiles: [], activeId: null });
  const isGuest = path === "/remote" || path.startsWith("/remote/");
  const jobs = useJobsPoll(!isGuest);
  const jobSummary = summarize(jobs);

  useEffect(() => {
    if (isGuest) return undefined;
    // GUI startup is intentionally observational. Do not inspect game installs,
    // UE4SS, RuneSchema, SteamCMD, or server runtime state from the shell.
    const load = () => fetch("/api/app/version?refresh=1", { cache: "no-store" }).then((r) => r.json()).then(setVer).catch(() => {});
    load();
    const id = setInterval(load, 60 * 60 * 1000);
    return () => clearInterval(id);
  }, [isGuest]);

  useEffect(() => {
    if (isGuest) return undefined;
    let stopped = false;
    const loadProfiles = () => fetch("/api/launcher-profiles", { cache: "no-store" })
      .then((response) => response.json())
      .then((result) => { if (!stopped && result?.ok) setLauncherProfiles(result); })
      .catch(() => {});
    loadProfiles();
    window.addEventListener("rsdw-launcher-profile-updated", loadProfiles);
    return () => { stopped = true; window.removeEventListener("rsdw-launcher-profile-updated", loadProfiles); };
  }, [isGuest]);

  useEffect(() => {
    if (!window.desktop?.onAppUpdateProgress) return undefined;
    return window.desktop.onAppUpdateProgress((progress) => setAppUpdate({ ...progress, error: "" }));
  }, []);

  useEffect(() => {
    if (isGuest) return undefined;
    let stopped = false;
    const loadUpdates = () => fetch("/api/component-updates", { cache: "no-store" })
      .then((response) => response.json())
      .then((result) => { if (!stopped && result?.ok) setComponentUpdates(result); })
      .catch(() => {});
    // Keep startup responsive; version monitoring begins after the shell is visible.
    const initial = setTimeout(loadUpdates, 4000);
    const interval = setInterval(loadUpdates, 30 * 60 * 1000);
    return () => { stopped = true; clearTimeout(initial); clearInterval(interval); };
  }, [isGuest]);

  useEffect(() => {
    const available = (componentUpdates?.items || []).filter((item) => item.updateAvailable);
    if (!available.length) return;
    const signature = available.map((item) => `${item.id}:${item.latestVersion}`).sort().join("|");
    try {
      if (localStorage.getItem("rsdw-update-notice") === signature) return;
      localStorage.setItem("rsdw-update-notice", signature);
    } catch {}
    const id = `updates-${Date.now()}`;
    setToasts((current) => [...current, { id, msg: `${available.length} Dragonwilds update${available.length === 1 ? "" : "s"} available — open Settings → Updates`, kind: "info" }]);
    setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 7000);
  }, [componentUpdates]);

  const handleVersionClick = async () => {
    if (["checking", "downloading", "verifying", "restarting"].includes(appUpdate.stage)) return;
    let status = ver;
    if (!status?.checked || !status?.updateAvailable || !status?.canAutoUpdate) {
      setAppUpdate({ stage: "checking", percent: null, error: "" });
      try {
        const response = await fetch("/api/app/version?refresh=1", { cache: "no-store" });
        const fresh = await response.json();
        setVer(fresh);
        status = fresh;
      } catch (error) {
        setAppUpdate({ stage: "error", percent: null, error: error.message || "Update check failed" });
        return;
      }
    }
    if (!status?.updateAvailable) {
      setAppUpdate({ stage: "idle", percent: null, error: "" });
      return;
    }
    if (!status.canAutoUpdate || !window.desktop?.installAppUpdate) {
      setAppUpdate({ stage: "idle", percent: null, error: "" });
      const url = status.releaseUrl;
      if (url) { try { window.open(url, "_blank"); } catch {} }
      return;
    }
    setAppUpdate({ stage: "downloading", percent: 0, error: "" });
    try {
      await window.desktop.installAppUpdate(status.updateAsset);
    } catch (error) {
      setAppUpdate({ stage: "error", percent: null, error: error.message || "Update failed" });
    }
  };

  useEffect(() => {
    // restore collapse preference
    try { const v = window.__dwsmSidebar; if (typeof v === "boolean") setCollapsed(v); } catch {}
  }, []);
  const toggleCollapse = () => setCollapsed((c) => { const n = !c; try { window.__dwsmSidebar = n; } catch {} return n; });

  useEffect(() => {
    registerToast((msg, kind) => {
      const id = Math.random().toString(36).slice(2);
      setToasts((t) => [...t, { id, msg, kind }]);
      setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3800);
    });
  }, []);

  const W = collapsed ? 68 : 236;

  // The Remote Access guest surface (/remote) is its own self-contained shell — no admin
  // sidebar or jobs. (/remote-access is the admin page and keeps the
  // sidebar.) Hooks above always run; only the chrome is skipped.
  if (isGuest) return <>{children}</>;

  return (
    <div className="desktop-shell">
      <SplashGate />
      <DesktopTitleBar />
      <div className="app-frame">
      {/* Single merged collapsible sidebar */}
      <aside style={{
        width: W, background: "var(--sidebar)", display: "flex", flexDirection: "column",
        flexShrink: 0, borderRight: "1px solid var(--line-strong)",
        transition: "width 0.22s cubic-bezier(0.4,0,0.2,1)", overflow: "hidden",
      }}>
        {/* brand + collapse toggle */}
        <div style={{ height: 64, position: "relative", display: "grid", placeItems: "center", borderBottom: "1px solid var(--line-strong)", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: collapsed ? 0 : "0.55rem", minWidth: 0 }}>
            <div style={{ width: collapsed ? 34 : 38, height: collapsed ? 34 : 38, borderRadius: 10, overflow: "hidden", display: "grid", placeItems: "center", flexShrink: 0 }}>
              <img src="/icon.png" alt="RSDW Sync" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            </div>
            {!collapsed && <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "0.92rem", whiteSpace: "nowrap" }}>RSDW</span>}
          </div>
          <button onClick={toggleCollapse} title={collapsed ? t("action.expand") : t("action.collapse")}
            style={{ position: "absolute", right: collapsed ? 1 : 7, top: "50%", transform: "translateY(-50%)", background: "transparent", border: "none", cursor: "pointer", color: "var(--ink-soft)", padding: 6, borderRadius: 8, display: "grid", placeItems: "center", transition: "background 0.15s" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--line)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
            <Icon name={collapsed ? "chevronRight" : "chevronLeft"} size={18} />
          </button>
        </div>

        {/* nav */}
        <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", padding: "0.7rem 0.55rem" }}>
          {!collapsed && (
            <div className="subtle" style={{ fontSize: "0.64rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.05em", padding: "0.3rem 0.6rem 0.5rem" }}>
              {t("sidebar.management")}
            </div>
          )}
          {NAV.map((n) => (
            <NavItem
              key={n.href}
              {...n}
              active={n.match(path)}
              collapsed={collapsed}
              badge={n.href === "/settings" && componentUpdates?.updateAvailable}
            />
          ))}
          <DownloadsNavItem active={path.startsWith("/downloads")} collapsed={collapsed} summary={jobSummary} label={t("nav.downloads")} />
        </div>

        {/* footer: active launcher identity plus compact one-click updater */}
        <div style={{ padding: collapsed ? "0.5rem" : "0.55rem", borderTop: "1px solid var(--line-strong)", flexShrink: 0 }}>
          <ProfileSwitcher collapsed={collapsed} data={launcherProfiles} ver={ver} update={appUpdate} onVersionClick={handleVersionClick} />
        </div>
      </aside>

      {/* Main content */}
      <main className="app-main" style={{ flex: 1, overflowY: "auto", background: "var(--bg)" }}>
        <img className="app-watermark" src="/rsdw/app-icon.webp" alt="" aria-hidden="true" />
        <div className="app-content">
          {children}
        </div>
      </main>

      {/* Toasts */}
      <div style={{ position: "fixed", right: 18, bottom: 18, display: "flex", flexDirection: "column", gap: 8, zIndex: 50 }}>
        {toasts.map((t) => (
          <div key={t.id} className="panel animate-floatUp" style={{
            padding: "0.7rem 1rem", minWidth: 220, maxWidth: 340, fontWeight: 600, fontSize: "0.88rem",
            borderLeft: `3px solid ${t.kind === "error" ? "var(--red)" : t.kind === "success" ? "var(--green-bright)" : "var(--accent)"}`,
          }}>
            {t.msg}
          </div>
        ))}
      </div>
      </div>
    </div>
  );
}

function ProfileSwitcher({ collapsed, data, ver, update, onVersionClick }) {
  const [open, setOpen] = useState(false);
  const active = data.profiles?.find((profile) => profile.profile_id === data.activeId) || data.profiles?.[0];
  const switchTo = async (profileId) => {
    if (!profileId || profileId === active?.profile_id) { setOpen(false); return; }
    try {
      const response = await fetch("/api/launcher-profiles/active", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ profileId }),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Could not switch profile");
      window.location.assign("/");
    } catch (error) {
      setOpen(false);
      toast(error.message || "Could not switch profile", "error");
    }
  };
  const avatar = active?.icon_data || "/icon.png";
  return <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 3 }}>
    {open && <div className="panel" style={{ position: "absolute", left: collapsed ? 0 : 2, bottom: "calc(100% + 8px)", width: collapsed ? 220 : "calc(100% - 4px)", padding: 6, zIndex: 80, boxShadow: "0 14px 34px rgba(0,0,0,.45)" }}>
      <div className="subtle" style={{ padding: "0.35rem 0.45rem", fontSize: ".65rem", fontWeight: 800, letterSpacing: ".06em" }}>PLAYER PROFILE</div>
      {(data.profiles || []).map((profile) => <button key={profile.profile_id} type="button" onClick={() => switchTo(profile.profile_id)}
        style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: ".45rem", border: 0, borderRadius: 7, color: "var(--ink)", background: profile.profile_id === active?.profile_id ? "var(--card-2)" : "transparent", cursor: "pointer", textAlign: "left" }}>
        <img src={profile.icon_data || "/icon.png"} alt="" style={{ width: 28, height: 28, borderRadius: 8, objectFit: "cover", background: "var(--card-2)" }} />
        <span style={{ minWidth: 0, flex: 1, fontWeight: 750, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{profile.display_name}</span>
        {profile.profile_id === active?.profile_id && <Icon name="check" size={15} />}
      </button>)}
      <Link href="/profile" onClick={() => setOpen(false)} className="btn btn-ghost" style={{ width: "100%", marginTop: 4, justifyContent: "center", textDecoration: "none" }}><Icon name="settings" size={15} /> Manage Profile</Link>
    </div>}
    <button type="button" onClick={() => setOpen((value) => !value)} title={collapsed ? `Profile: ${active?.display_name || "Player"}` : "Switch player profile"}
      style={{ flex: 1, width: collapsed ? "100%" : "auto", minWidth: 0, display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "flex-start", gap: 9, padding: collapsed ? 4 : ".45rem .5rem", border: "1px solid transparent", borderRadius: 9, background: open ? "var(--card-2)" : "transparent", color: "var(--ink)", cursor: "pointer", textAlign: "left" }}>
      <img src={avatar} alt="" style={{ width: 34, height: 34, borderRadius: 9, objectFit: "cover", background: "var(--card-2)", flexShrink: 0 }} />
      {!collapsed && <><span style={{ minWidth: 0, flex: 1 }}><span className="subtle" style={{ display: "block", fontSize: ".61rem", fontWeight: 800 }}>PLAYER PROFILE</span><strong style={{ display: "block", fontSize: ".78rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{active?.display_name || "Player 1"}</strong></span><Icon name="chevronUp" size={15} /></>}
    </button>
    <VersionStatusDot collapsed={collapsed} ver={ver} update={update} onClick={onVersionClick} />
  </div>;
}

function VersionStatusDot({ collapsed, ver, update, onClick }) {
  const busy = ["checking", "downloading", "verifying", "restarting"].includes(update.stage);
  const updateReady = !!ver?.updateAvailable;
  const healthy = !!ver?.checked && !updateReady && update.stage !== "error";
  const color = update.stage === "error" ? "var(--red)" : updateReady ? "var(--yellow)" : healthy ? "var(--green-bright)" : "var(--ink-muted)";
  const status = update.stage === "checking" ? "Checking for updates…"
    : update.stage === "downloading" ? `Downloading update${Number.isFinite(update.percent) ? ` · ${update.percent}%` : "…"}`
      : update.stage === "verifying" ? "Verifying download…"
        : update.stage === "restarting" ? "Installing and restarting…"
          : update.stage === "error" ? update.error
            : updateReady && ver?.canAutoUpdate ? "Update available · click to install"
              : updateReady ? "New build is publishing · view release"
                : healthy ? "Up to date · click to check"
                  : "Update status unavailable · click to retry";
  const title = updateReady && ver?.canAutoUpdate
    ? "Download, verify, replace, and restart RSDW Sync"
    : status;

  const fullTitle = `RSDW Sync v${ver?.current || "0.1.1"} · ${title}`;
  return <button type="button" onClick={onClick} disabled={busy} title={fullTitle} aria-label={fullTitle}
    style={{ position: collapsed ? "absolute" : "relative", right: collapsed ? 2 : "auto", bottom: collapsed ? 2 : "auto", width: collapsed ? 17 : 26, height: collapsed ? 17 : 34, padding: 0, display: "grid", placeItems: "center", flexShrink: 0, borderRadius: 999, border: `1px solid color-mix(in srgb, ${color} 55%, var(--line))`, background: "var(--sidebar)", cursor: busy ? "wait" : "pointer" }}>
    <span className={busy ? "animate-pulseDot" : ""} style={{ width: collapsed ? 8 : 10, height: collapsed ? 8 : 10, borderRadius: 999, background: color, boxShadow: `0 0 0 3px color-mix(in srgb, ${color} 18%, transparent)` }} />
  </button>;
}

function DesktopTitleBar() {
  const [visible, setVisible] = useState(false);
  useEffect(() => setVisible(!!window.desktop?.isElectron && window.desktop?.platform === "win32"), []);
  if (!visible) return null;
  return <div className="desktop-titlebar" aria-label="RuneScape Dragonwilds Sync Launcher window title bar">
    <img src="/icon.png" alt="" />
    <span className="desktop-titlebar-product">RuneScape: Dragonwilds</span>
    <span className="desktop-titlebar-separator" aria-hidden="true">—</span>
    <span className="desktop-titlebar-context">Sync Launcher</span>
  </div>;
}

function SplashGate() {
  // Render the splash in the server HTML and on the very first client paint.
  // Starting hidden and enabling it in an effect lets the application shell flash
  // underneath for one frame, which is especially visible on fast desktop launches.
  const [visible, setVisible] = useState(true);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (!window.desktop?.isElectron) {
      setVisible(false);
    }
  }, []);

  const enter = () => {
    if (!visible || leaving) return;
    setLeaving(true);
    setTimeout(() => setVisible(false), 650);
  };

  useEffect(() => {
    if (!visible) return undefined;
    const keydown = (event) => { if (event.key === "Enter") enter(); };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [visible, leaving]);

  if (!visible) return null;
  return <div className={`launch-splash ${leaving ? "launch-splash-leaving" : ""}`} role="dialog" aria-label="Welcome to RSDW Sync">
    <div className="launch-splash-glow" />
    <div className="launch-splash-logos" aria-hidden="true">
      <img className="launch-splash-dragonwilds" src="/rsdw/dragonwilds-wordmark.png" alt="" />
      <img className="launch-splash-rsdw" src="/rsdw/app-icon.webp" alt="" />
    </div>
    <div className="launch-splash-copy">
      <span>DRAGONWILDS PROFILES</span>
      <button className="launch-splash-enter" onClick={enter}>Enter</button>
      <small>Press Enter</small>
    </div>
  </div>;
}

function NavItem({ href, icon, asset, material, label, active, collapsed, badge }) {
  return (
    <Link href={href} title={collapsed ? label : undefined}
      style={{
        display: "flex", alignItems: "center", gap: "0.6rem",
        padding: collapsed ? "0.6rem" : "0.55rem 0.6rem", borderRadius: 8,
        justifyContent: collapsed ? "center" : "flex-start",
        textDecoration: "none", fontFamily: "var(--font-display)",
        fontWeight: 600, fontSize: "0.9rem", marginBottom: 3,
        background: active ? "var(--accent)" : "transparent",
        color: active ? "var(--accent-ink)" : "var(--ink-soft)",
        transition: "background 0.15s, color 0.15s",
      }}
      onMouseEnter={(e) => { if (!active) { e.currentTarget.style.background = "var(--card-2)"; e.currentTarget.style.color = "var(--ink)"; } }}
      onMouseLeave={(e) => { if (!active) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--ink-soft)"; } }}
    >
      <span style={{ position: "relative", width: 24, height: 24, display: "grid", placeItems: "center", flexShrink: 0 }}>
        {asset
          ? <img src={asset} alt="" style={{ width: 24, height: 24, objectFit: "contain" }} />
          : material
            ? <MaterialNavIcon name={material} size={22} />
            : <Icon name={icon} size={20} />}
        {badge && <span title="Framework update available" style={{
          position: "absolute", top: -3, right: -4, width: 8, height: 8, borderRadius: 999,
          background: "var(--yellow)", border: "1.5px solid var(--sidebar)",
        }} />}
      </span>
      {!collapsed && <span style={{ whiteSpace: "nowrap" }}>{label}</span>}
    </Link>
  );
}

// Sidebar "Downloads" entry — a permanent nav item that shows a live count and
// aggregate progress while installs/updates run, and links to the Downloads page.
function DownloadsNavItem({ active, collapsed, summary, label }) {
  const { activeCount, percent, anyError } = summary;
  const busy = activeCount > 0;
  const dotColor = anyError ? "var(--red)" : "var(--accent)";

  return (
    <Link href="/downloads" title={collapsed ? `${label}${busy ? ` (${activeCount})` : ""}` : undefined}
      style={{
        display: "block", padding: collapsed ? "0.6rem" : "0.55rem 0.6rem", borderRadius: 8,
        textDecoration: "none", fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "0.9rem",
        marginBottom: 3, marginTop: 2,
        background: active ? "var(--accent)" : "transparent",
        color: active ? "var(--accent-ink)" : "var(--ink-soft)",
        transition: "background 0.15s, color 0.15s",
      }}
      onMouseEnter={(e) => { if (!active) { e.currentTarget.style.background = "var(--card-2)"; e.currentTarget.style.color = "var(--ink)"; } }}
      onMouseLeave={(e) => { if (!active) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--ink-soft)"; } }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", justifyContent: collapsed ? "center" : "flex-start", position: "relative" }}>
        <span style={{ position: "relative", display: "grid", placeItems: "center" }}>
          <MaterialNavIcon name="downloads" size={22} />
          {busy && (
            <span className="animate-pulseDot" style={{ position: "absolute", top: -3, right: -4, width: 8, height: 8, borderRadius: 999, background: dotColor, border: "1.5px solid var(--sidebar)" }} />
          )}
        </span>
        {!collapsed && <span style={{ whiteSpace: "nowrap", flex: 1 }}>{label}</span>}
        {!collapsed && busy && (
          <span className="chip" style={{ background: active ? "rgba(255,255,255,0.2)" : "var(--card-2)", fontSize: "0.7rem", fontWeight: 800, padding: "0.05rem 0.4rem" }}>
            {activeCount}
          </span>
        )}
      </div>
      {!collapsed && busy && (
        <ProgressBar percent={percent} style={{ marginTop: "0.5rem", height: 5 }} />
      )}
    </Link>
  );
}
