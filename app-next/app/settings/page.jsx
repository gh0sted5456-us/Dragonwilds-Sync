"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation, Trans } from "react-i18next";
import { api, Icon, toast } from "@/components/ui";
import { PageHeader } from "@/components/PageChrome";
// Pal name mapping removed for RSDW — Pals are not a thing in Dragonwilds.

export default function SettingsPage() {
  const { t } = useTranslation();
  const [s, setS] = useState(null);
  const [steam, setSteam] = useState(null);
  const [saving, setSaving] = useState(false);
  const [backupLoc, setBackupLoc] = useState(null);
  const [backupPath, setBackupPath] = useState("");
  const [autoLaunch, setAutoLaunchState] = useState(null);
  const [closeToTray, setCloseToTrayState] = useState(null);
  const [componentUpdates, setComponentUpdates] = useState(null);
  const [componentChecking, setComponentChecking] = useState(false);
  const [nexusApiKey, setNexusApiKey] = useState("");
  const [curseForgeApiKey, setCurseForgeApiKey] = useState("");
  const [section, setSection] = useState(null); // null = category list; otherwise the open category id
  const isElectron = typeof window !== "undefined" && window.desktop?.isElectron;

  useEffect(() => {
    api("/api/settings").then((r) => setS(r.settings)).catch(() => {});
    api("/api/steamcmd").then(setSteam).catch(() => {});
    api("/api/settings/backup-dir").then((r) => { setBackupLoc(r.backup); setBackupPath(r.backup.custom ? r.backup.path : ""); }).catch(() => {});
    const readDesktopFlag = async (method, fallback, setter) => {
      try {
        const fn = window.desktop?.[method];
        setter(isElectron && typeof fn === "function" ? !!(await fn()) : fallback);
      } catch {
        setter(fallback);
      }
    };
    void readDesktopFlag("getAutoLaunch", false, setAutoLaunchState);
    void readDesktopFlag("getCloseToTray", true, setCloseToTrayState);
  }, []);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("section");
    if (["tools", "appearance", "server", "integrations", "updates", "backups", "desktop", "system"].includes(requested)) setSection(requested);
  }, []);

  const loadComponentUpdates = async (force = false) => {
    setComponentChecking(true);
    try {
      const result = await api(`/api/component-updates${force ? "?force=1" : ""}`);
      setComponentUpdates(result);
    } catch (e) {
      setComponentUpdates({ ok: false, updateAvailable: false, items: [], error: e.message });
    } finally {
      setComponentChecking(false);
    }
  };

  const saveBackupDir = async (p) => {
    setSaving(true);
    try {
      const r = await api("/api/settings/backup-dir", { method: "POST", body: { path: p } });
      setBackupLoc(r.backup);
      setBackupPath(r.backup.custom ? r.backup.path : "");
      toast(r.backup.custom ? t("settings.backupLocationUpdated") : t("settings.backupLocationReset"), "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  };

  const pickBackupDir = async () => {
    if (!isElectron) return;
    const p = await window.desktop.pickDirectory();
    if (p) setBackupPath(p);
  };

  const toggleAutoLaunch = async () => {
    if (!isElectron || autoLaunch === null) return;
    const next = !autoLaunch;
    setAutoLaunchState(next);
    try { await window.desktop.setAutoLaunch(next); }
    catch (e) { setAutoLaunchState(!next); toast(e.message, "error"); }
  };

  const toggleCloseToTray = async () => {
    if (!isElectron || closeToTray === null) return;
    const next = !closeToTray;
    setCloseToTrayState(next);
    try { await window.desktop.setCloseToTray(next); }
    catch (e) { setCloseToTrayState(!next); toast(e.message, "error"); }
  };

  const save = async (patch) => {
    setSaving(true);
    try {
      const r = await api("/api/settings", { method: "POST", body: patch });
      setS(r.settings);
      toast(t("settings.saved"), "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  };

  useEffect(() => {
    if (section === "updates" && !componentUpdates && !componentChecking) loadComponentUpdates(false);
  }, [section]);

  if (!s) return <div className="subtle" style={{ fontWeight: 700 }}>{t("common.loading")}</div>;

  // Settings are grouped into categories. The landing view is a clickable list; picking
  // one drills into just that category's panels with a back button, so no single page is
  // crammed. `electronOnly` categories are hidden in the browser build.
  const CATEGORIES = [
    { id: "tools", icon: "grid" },
    { id: "appearance", icon: "sun" },
    { id: "server", icon: "terminal" },
    { id: "integrations", icon: "globe" },
    { id: "updates", icon: "refresh" },
    { id: "backups", icon: "download" },
    { id: "desktop", icon: "settings" },
    { id: "system", icon: "cpu" },
  ];
  const cats = CATEGORIES.filter((c) => !c.electronOnly || isElectron);

  // Landing: the category menu.
  if (!section) {
    return (
      <div>
        <PageHeader eyebrow="RSDW SYNC" title={t("settings.title")} description="Application tools, server behavior, integrations, updates, backups, and desktop preferences." icon="settings" />
        <div className="settings-category-grid">
          {cats.map((c) => (
            <button key={c.id} className="menu-card" onClick={() => setSection(c.id)}>
              <span className="menu-card-icon">
                <Icon name={c.icon} size={19} />
              </span>
              <span className="menu-card-copy">
                <strong>
                  {c.id === "tools" ? "Application tools" : t(`settings.cat.${c.id}`)}
                  {c.id === "updates" && componentUpdates?.updateAvailable && (
                    <span className="chip" style={{ background: "var(--yellow)", color: "#161108", fontSize: "0.62rem" }}>UPDATE</span>
                  )}
                </strong>
                <small>{c.id === "tools" ? "Application Setup, Sync access, save maintenance, and Activity history." : t(`settings.cat.${c.id}Desc`)}</small>
              </span>
              <Icon name="chevronRight" size={18} />
            </button>
          ))}
        </div>
      </div>
    );
  }

  // Detail: one category's panels, with a back button to the menu.
  return (
    <div>
      <button className="page-back" onClick={() => setSection(null)}>
        <Icon name="back" size={16} /> {t("settings.title")}
      </button>
      <PageHeader eyebrow="SETTINGS" title={section === "tools" ? "Application tools" : t(`settings.cat.${section}`)} description={section === "tools" ? "Machine setup, authenticated Sync access, save maintenance, and application activity." : t(`settings.cat.${section}Desc`)} icon={cats.find((item) => item.id === section)?.icon || "settings"} />

      {section === "tools" && <div style={{ display: "grid", gap: 10, maxWidth: 760 }}>
        <SettingsTool href="/setup" icon="settings" title="Application Setup" detail="Configure SteamCMD, dedicated server files, and Steam, Epic, or Game Pass play lanes." />
        <SettingsTool href="/remote-access" icon="sync" title="Sync & Remote Access" detail="Control local-network access and the authenticated service used for World manifests and downloads." />
        <SettingsTool href="/save-cleaner" icon="shield" title="Player & World Save Cleaner" detail="Preview registry-orphaned player records or safely rebuild a World's disposable SPUD cache, with progress and recovery backups." />
        <SettingsTool href="/usage" icon="activity" title="Activity" detail="Review application, server, synchronization, and download activity." />
      </div>}

      {section === "appearance" && (
      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("settings.appearance")}</h3>
        <label className="label">{t("settings.theme")}</label>
        <div className="panel-inset" style={{ padding: "0.8rem 0.9rem", display: "flex", alignItems: "center", gap: "0.7rem", borderColor: "var(--line-strong)" }}>
          <Icon name="moon" />
          <div>
            <div style={{ fontWeight: 850 }}>RSDW Dark</div>
            <div className="subtle" style={{ fontSize: "0.75rem", fontWeight: 600 }}>Matte black surfaces with muted gold borders and controls.</div>
          </div>
        </div>
      </div>
      )}

      {section === "server" && (
      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>Dedicated Server Mode</h3>
        <p className="subtle" style={{ fontWeight: 650, lineHeight: 1.55 }}>
          Turn this on only when this computer hosts headless Dragonwilds servers. The default player experience shows Worlds without server setup, process controls, or server-only records.
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
          <button className={`btn ${s.serverModeEnabled === true ? "btn-primary" : "btn-ghost"}`}
            onClick={() => save({ serverModeEnabled: s.serverModeEnabled !== true })} disabled={saving}>
            {s.serverModeEnabled === true ? "Server Mode On" : "Server Mode Off"}
          </button>
          <span className="subtle" style={{ fontWeight: 650, fontSize: "0.78rem" }}>
            {s.serverModeEnabled === true ? "Dedicated Servers are visible on the Worlds page." : "Only player Worlds are shown."}
          </span>
        </div>
      </div>
      )}

      {section === "integrations" && (
      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem", maxWidth: 780 }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>Mod catalog connections</h3>
        <p className="subtle" style={{ fontWeight: 650, lineHeight: 1.55 }}>
          Nexus catalog browsing works without a key. A Nexus key enables installed-mod update checks; a CurseForge key enables its complete catalog and update checks. Keys stay in this computer&apos;s local RSDW database and are never returned to the browser after saving.
        </p>
        <div style={{ display: "grid", gap: "1rem" }}>
          <label><span className="label">Nexus Mods personal API key · {s.nexusApiConfigured ? "Configured" : "Not configured"}</span><input className="input" type="password" autoComplete="off" value={nexusApiKey} onChange={(event) => setNexusApiKey(event.target.value)} placeholder={s.nexusApiConfigured ? "Enter a replacement key" : "Paste a testing/personal API key"} /></label>
          <label><span className="label">CurseForge API key · {s.curseForgeApiConfigured ? "Configured" : "Not configured"}</span><input className="input" type="password" autoComplete="off" value={curseForgeApiKey} onChange={(event) => setCurseForgeApiKey(event.target.value)} placeholder={s.curseForgeApiConfigured ? "Enter a replacement key" : "Paste a CurseForge API key"} /></label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-primary" disabled={saving || (!nexusApiKey.trim() && !curseForgeApiKey.trim())} onClick={async () => { await save({ ...(nexusApiKey.trim() ? { nexusApiKey } : {}), ...(curseForgeApiKey.trim() ? { curseForgeApiKey } : {}) }); setNexusApiKey(""); setCurseForgeApiKey(""); }}><Icon name="download" /> Save connections</button>
            {(s.nexusApiConfigured || s.curseForgeApiConfigured) && <button className="btn btn-ghost" disabled={saving} onClick={async () => { await save({ nexusApiKey: "", curseForgeApiKey: "" }); setNexusApiKey(""); setCurseForgeApiKey(""); }}>Clear saved keys</button>}
          </div>
        </div>
      </div>
      )}

      {section === "desktop" && (<>
      {isElectron && (
        <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
          <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("settings.autoLaunchTitle")}</h3>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <button className={`btn ${autoLaunch !== false ? "btn-primary" : "btn-ghost"}`} style={{ padding: "0.35rem 0.7rem" }}
              onClick={toggleAutoLaunch} disabled={autoLaunch === null}>
              {autoLaunch !== false ? t("common.on") : t("common.off")}
            </button>
            <span className="subtle" style={{ fontWeight: 600, fontSize: "0.78rem" }}>{t("settings.autoLaunchDesc")}</span>
          </div>
        </div>
      )}

      {isElectron && (
        <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
          <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("settings.closeToTrayTitle")}</h3>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <button className={`btn ${closeToTray !== false ? "btn-primary" : "btn-ghost"}`} style={{ padding: "0.35rem 0.7rem" }}
              onClick={toggleCloseToTray} disabled={closeToTray === null}>
              {closeToTray !== false ? t("common.on") : t("common.off")}
            </button>
            <span className="subtle" style={{ fontWeight: 600, fontSize: "0.78rem" }}>{t("settings.closeToTrayDesc")}</span>
          </div>
        </div>
      )}

      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("settings.hideConsoleTitle")}</h3>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <button className={`btn ${s.hideConsoleWindow !== false ? "btn-primary" : "btn-ghost"}`} style={{ padding: "0.35rem 0.7rem" }}
            onClick={() => save({ hideConsoleWindow: s.hideConsoleWindow === false })} disabled={saving}>
            {s.hideConsoleWindow !== false ? t("common.on") : t("common.off")}
          </button>
          <span className="subtle" style={{ fontWeight: 600, fontSize: "0.78rem" }}>
            <Trans i18nKey="settings.hideConsoleDesc" components={{ b: <b /> }} />
          </span>
        </div>
        {s.hideConsoleWindow === false && (
          <p className="subtle" style={{ fontSize: "0.78rem", marginBottom: 0, marginTop: "0.6rem" }}>
            <Trans i18nKey="settings.hideConsoleWarn" components={{ b: <b /> }} />
          </p>
        )}
      </div>
      </>)}

      {section === "updates" && (
      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("settings.autoUpdateTitle")}</h3>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <button className={`btn ${s.autoUpdateEnabled === true ? "btn-primary" : "btn-ghost"}`} style={{ padding: "0.35rem 0.7rem" }}
            onClick={() => save({ autoUpdateEnabled: s.autoUpdateEnabled !== true })} disabled={saving}>
            {s.autoUpdateEnabled === true ? t("common.on") : t("common.off")}
          </button>
          <span className="subtle" style={{ fontWeight: 600, fontSize: "0.78rem" }}>
            <Trans i18nKey="settings.autoUpdateDesc" components={{ b: <b /> }} />
          </span>
        </div>
        <div style={{ marginTop: "1.1rem", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
          <label className="label">{t("settings.updateCheckInterval")}</label>
          <div style={{ display: "flex", gap: "0.5rem", maxWidth: 260 }}>
            <input className="input" type="number" min="5" value={s.updateCheckIntervalMinutes ?? 30}
              onChange={(e) => setS({ ...s, updateCheckIntervalMinutes: Number(e.target.value) })} />
            <button className="btn btn-primary" onClick={() => save({ updateCheckIntervalMinutes: Math.max(5, Number(s.updateCheckIntervalMinutes) || 30) })} disabled={saving}>{t("common.save")}</button>
          </div>
          <p className="subtle" style={{ fontWeight: 600, fontSize: "0.72rem", margin: "0.5rem 0 0" }}>{t("settings.updateCheckIntervalHelp")}</p>
        </div>

        <div style={{ marginTop: "1.1rem", borderTop: "1px solid var(--line)", paddingTop: "1rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.7rem" }}>
            <div>
              <div className="heading" style={{ fontSize: "0.92rem" }}>Game and framework update notifications</div>
              <div className="subtle" style={{ fontSize: "0.72rem", fontWeight: 600 }}>
                Checks the Steam dedicated-server branch, the configured Steam and PC Game Pass player installations, UE4SS releases, and RuneSchema. Update badges appear here and in the sidebar.
              </div>
            </div>
            <button className="btn btn-ghost" style={{ marginLeft: "auto", padding: "0.3rem 0.55rem" }}
              disabled={componentChecking} onClick={() => loadComponentUpdates(true)}>
              <Icon name="refresh" size={14} /> {componentChecking ? "Checking…" : "Check now"}
            </button>
          </div>

          {!componentUpdates ? (
            <div className="subtle" style={{ fontSize: "0.78rem", fontWeight: 700 }}>Checking framework releases…</div>
          ) : componentUpdates.items?.length ? (
            <div style={{ display: "grid", gap: "0.5rem" }}>
              {componentUpdates.items.map((item) => {
                const amber = item.updateAvailable;
                const stateLabel = amber
                  ? "UPDATE"
                  : item.installedVersion && item.latestVersion
                    ? "CURRENT"
                    : item.installed
                      ? "VERSION UNKNOWN"
                      : "NOT INSTALLED";
                return (
                  <button key={item.id} className="panel-inset"
                    onClick={() => item.url && window.open(item.url, "_blank")}
                    style={{
                      width: "100%", cursor: item.url ? "pointer" : "default", textAlign: "left",
                      padding: "0.75rem 0.85rem", display: "grid", gridTemplateColumns: "minmax(150px,1fr) auto",
                      gap: "0.75rem", alignItems: "center",
                      border: `1px solid ${amber ? "var(--yellow)" : "var(--line)"}`,
                      background: amber ? "color-mix(in srgb,var(--yellow) 8%,var(--card-2))" : "var(--card-2)",
                      color: "var(--ink)",
                    }}>
                    <span>
                      <span style={{ display: "block", fontWeight: 850, fontSize: "0.86rem" }}>{item.label}</span>
                      <span className="subtle" style={{ display: "block", fontSize: "0.7rem", fontWeight: 650, marginTop: 2 }}>
                        Installed: {item.installedVersion || (item.installed ? "detected · version unknown" : "not detected")}
                        {" · "}Latest: {item.latestVersion || "unavailable"}
                      </span>
                      {item.error && <span style={{ display: "block", color: "var(--yellow)", fontSize: "0.68rem", marginTop: 2 }}>{item.error}</span>}
                    </span>
                    <span className="chip" style={{
                      background: amber ? "var(--yellow)" : "var(--line)",
                      color: amber ? "#161108" : "var(--ink-soft)",
                      fontWeight: 900, letterSpacing: ".035em",
                    }}>
                      {stateLabel}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="subtle" style={{ fontSize: "0.78rem", fontWeight: 700 }}>
              Release status is unavailable right now.
            </div>
          )}
        </div>
      </div>
      )}

      {section === "backups" && (
      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("settings.backupsTitle")}</h3>
        <label className="label">{t("settings.keepLastN")}</label>
        <div style={{ display: "flex", gap: "0.5rem", maxWidth: 260 }}>
          <input className="input" type="number" min="1" value={s.backupRetention ?? 10} onChange={(e) => setS({ ...s, backupRetention: Number(e.target.value) })} />
          <button className="btn btn-primary" onClick={() => save({ backupRetention: s.backupRetention })} disabled={saving}>{t("common.save")}</button>
        </div>

        {backupLoc && (
          <div style={{ marginTop: "1.1rem", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
            <label className="label">{t("settings.backupLocation")}</label>
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.78rem", margin: "0 0 0.5rem" }}>
              <Trans i18nKey="settings.backupLocationDesc"
                values={{ where: backupLoc.custom ? t("settings.customFolder") : t("settings.defaultFolder") }}
                components={{ b: <b />, w: <span style={{ fontWeight: 800 }} /> }} />
            </p>
            <p className="subtle" style={{ fontFamily: "var(--font-mono)", fontSize: "0.74rem", margin: "0 0 0.6rem", wordBreak: "break-all" }}>{backupLoc.path}</p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
              <input className="input" style={{ flex: 1, minWidth: 220 }} placeholder={t("settings.backupPathPlaceholder")}
                value={backupPath} onChange={(e) => setBackupPath(e.target.value)} />
              {isElectron && (
                <button className="btn btn-ghost" onClick={pickBackupDir} disabled={saving}><Icon name="folder" size={15} /> {t("settings.chooseFolder")}</button>
              )}
              <button className="btn btn-primary" onClick={() => saveBackupDir(backupPath)} disabled={saving}>{t("common.save")}</button>
              {backupLoc.custom && (
                <button className="btn btn-ghost" onClick={() => saveBackupDir("")} disabled={saving}>{t("common.reset")}</button>
              )}
            </div>
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.72rem", margin: "0.5rem 0 0" }}>
              {t("settings.existingBackupsNote")}
            </p>
          </div>
        )}
      </div>
      )}

      {section === "system" && (<>
      <div className="panel" style={{ padding: "1.3rem", marginBottom: "1rem" }}>
        <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("settings.steamcmdTitle")}</h3>
        <p style={{ fontWeight: 700, fontSize: "0.86rem", margin: 0 }}>
          <span className={steam?.installed ? "s-running" : "s-crashed"}>
            {steam?.installed ? t("settings.steamcmdInstalled") : t("settings.steamcmdNotInstalled")}
          </span>
          <span className="subtle">{t("settings.steamcmdNote")}</span>
        </p>
        {steam?.path && <p className="subtle" style={{ fontFamily: "var(--font-mono)", fontSize: "0.74rem", marginTop: 6 }}>{steam.path}</p>}
      </div>

      </>)}
    </div>
  );
}

function SettingsTool({ href, icon, title, detail }) {
  return <Link href={href} className="menu-card" style={{ textDecoration: "none" }}>
    <span className="menu-card-icon"><Icon name={icon} size={20} /></span>
    <span className="menu-card-copy"><strong>{title}</strong><small>{detail}</small></span>
    <Icon name="chevronRight" size={18} />
  </Link>;
}
