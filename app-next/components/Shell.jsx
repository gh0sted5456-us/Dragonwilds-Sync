"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/components/ThemeProvider";
import { Icon, registerToast } from "@/components/ui";
import { useJobsPoll, summarize, ProgressBar } from "@/components/jobsClient";

// labelKey resolves through t() at render time — NAV is a module-level const, so it
// can't call the translation hook itself.
const NAV = [
  { href: "/", asset: "/rsdw/navigation/dragonwilds.webp", label: "Worlds", match: (p) => p === "/" || p.startsWith("/worlds") || p.startsWith("/profiles") },
  { href: "/remote-access", material: "sync", label: "Sync", match: (p) => p.startsWith("/remote-access") },
  { href: "/usage", material: "activity", label: "Activity", match: (p) => p.startsWith("/usage") },
  { href: "/settings", material: "settings", label: "Settings", match: (p) => p.startsWith("/settings") },
  { href: "/info", material: "help", label: "Helpy", match: (p) => p.startsWith("/info") },
];

const MATERIAL_NAV = {
  sync: "M7.41 13.41 6 12l-4 4 4 4 1.41-1.41L5.83 17H13v-2H5.83l1.58-1.59zM16.59 10.59 18 12l4-4-4-4-1.41 1.41L18.17 7H11v2h7.17l-1.58 1.59z",
  activity: "M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z",
  settings: "M19.43 12.98c.04-.32.07-.65.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.37-.31-.6-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98L14.5 2.42C14.47 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42L9.13 5.07c-.61.25-1.17.58-1.69.98l-2.49-1c-.23-.09-.48 0-.6.22l-2 3.46c-.12.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.37.31.6.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.58 1.69-.98l2.49 1c.23.09.48 0 .6-.22l2-3.46c.12-.22.07-.49-.12-.64zM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5z",
  help: "M11 18h2v-2h-2v2zm1-16C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16zm0-14c-2.21 0-4 1.79-4 4h2a2 2 0 1 1 3.41 1.41c-.82.82-1.41 1.48-1.41 3.59h2c0-1.37.37-1.75 1.12-2.5A4 4 0 0 0 12 6z",
  downloads: "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
};

function MaterialNavIcon({ name, size = 22 }) {
  const d = MATERIAL_NAV[name];
  return <svg aria-hidden viewBox="0 0 24 24" width={size} height={size} fill="currentColor"><path d={d} /></svg>;
}

export default function Shell({ children }) {
  const { theme, toggle } = useTheme();
  const { t } = useTranslation();
  const path = usePathname();
  const [toasts, setToasts] = useState([]);
  const [collapsed, setCollapsed] = useState(false);
  const [ver, setVer] = useState(null);
  const [componentUpdates, setComponentUpdates] = useState(null);
  const jobs = useJobsPoll();
  const jobSummary = summarize(jobs);

  useEffect(() => {
    const load = () => fetch("/api/app/version").then((r) => r.json()).then(setVer).catch(() => {});
    const loadComponents = () => fetch("/api/component-updates").then((r) => r.json()).then(setComponentUpdates).catch(() => {});
    load();
    loadComponents();
    const id = setInterval(() => { load(); loadComponents(); }, 30 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  const openRelease = () => {
    const url = ver?.releaseUrl;
    if (url) { try { window.open(url, "_blank"); } catch {} }
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
  // sidebar, jobs, or first-run wizard. (/remote-access is the admin page and keeps the
  // sidebar.) Hooks above always run; only the chrome is skipped.
  if (path === "/remote" || path.startsWith("/remote/")) return <>{children}</>;

  return (
    <div style={{ display: "flex", minHeight: "100vh", height: "100vh", overflow: "hidden" }}>
      {/* Single merged collapsible sidebar */}
      <aside style={{
        width: W, background: "var(--sidebar)", display: "flex", flexDirection: "column",
        flexShrink: 0, borderRight: "1px solid var(--line-strong)",
        transition: "width 0.22s cubic-bezier(0.4,0,0.2,1)", overflow: "hidden",
      }}>
        {/* brand + collapse toggle */}
        <div style={{ height: 56, display: "flex", alignItems: "center", padding: collapsed ? "0" : "0 0.9rem", justifyContent: collapsed ? "center" : "space-between", borderBottom: "1px solid var(--line-strong)", flexShrink: 0 }}>
          {!collapsed && (
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", minWidth: 0 }}>
              <div style={{ width: 34, height: 34, borderRadius: 10, overflow: "hidden", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <img src="/rsdw/rsdwl-icon.webp" alt="RSDW" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              </div>
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "0.92rem", whiteSpace: "nowrap" }}>RSDW</span>
            </div>
          )}
          <button onClick={toggleCollapse} title={collapsed ? t("action.expand") : t("action.collapse")}
            style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--ink-soft)", padding: 7, borderRadius: 8, display: "grid", placeItems: "center", transition: "background 0.15s" }}
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

        {/* footer: app version / update + theme */}
        <div style={{ padding: "0.55rem", borderTop: "1px solid var(--line-strong)", flexShrink: 0 }}>
          {!collapsed && ver?.updateAvailable && (
            <button onClick={openRelease} title="Open the latest release to download"
              style={{
                width: "100%", marginBottom: "0.5rem", padding: "0.45rem 0.6rem", borderRadius: 8,
                background: "var(--accent)", color: "var(--accent-ink)", border: "none", cursor: "pointer",
                display: "flex", alignItems: "center", gap: "0.45rem", fontWeight: 700, fontSize: "0.78rem",
              }}>
              <Icon name="download" size={15} />
              <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {t("app.updateAvailable", { version: ver.latest })}
              </span>
            </button>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: "0.55rem", justifyContent: collapsed ? "center" : "space-between" }}>
            {!collapsed && (
              <div style={{ lineHeight: 1.1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: "0.78rem", whiteSpace: "nowrap" }}>
                  RSDW Sync
                </div>
                <div className="subtle" style={{ fontSize: "0.68rem" }}>
                  v1.0.0{ver && !ver.updateAvailable && ver.checked ? ` · ${t("app.upToDate")}` : ""}
                </div>
              </div>
            )}
            {collapsed && ver?.updateAvailable ? (
              <button onClick={openRelease} title={t("app.updateAvailable", { version: ver.latest })}
                style={{ background: "var(--accent)", border: "none", cursor: "pointer", color: "var(--accent-ink)", padding: 7, borderRadius: 8, display: "grid", placeItems: "center" }}>
                <Icon name="download" size={18} />
              </button>
            ) : (
              <button onClick={toggle} title={t("action.toggleTheme")}
                style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--ink-soft)", padding: 7, borderRadius: 8, display: "grid", placeItems: "center", transition: "background 0.15s" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--line)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main style={{ flex: 1, overflowY: "auto", background: "var(--bg)" }}>
        <div style={{ padding: "1.4rem 1.8rem 3rem", maxWidth: 1120, margin: "0 auto" }}>
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
  );
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
