"use client";
import { useEffect, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { api, Icon, toast } from "@/components/ui";
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
    { id: "appearance", icon: "sun" },
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
        <h1 className="heading" style={{ fontSize: "1.9rem", margin: "0 0 1.2rem" }}>{t("settings.title")}</h1>
        <div style={{ display: "grid", gap: "0.6rem", maxWidth: 680 }}>
          {cats.map((c) => (
            <button key={c.id} className="panel" onClick={() => setSection(c.id)}
              style={{ display: "flex", alignItems: "center", gap: "1rem", padding: "1rem 1.2rem", textAlign: "left", cursor: "pointer", width: "100%" }}>
              <span style={{ display: "grid", placeItems: "center", width: 40, height: 40, borderRadius: 10, background: "var(--panel-inset, rgba(127,127,127,0.12))", flexShrink: 0 }}>
                <Icon name={c.icon} size={19} />
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "flex", alignItems: "center", gap: "0.45rem", fontWeight: 800, fontSize: "0.98rem" }}>
                  {t(`settings.cat.${c.id}`)}
                  {c.id === "updates" && componentUpdates?.updateAvailable && (
                    <span className="chip" style={{ background: "var(--yellow)", color: "#161108", fontSize: "0.62rem" }}>UPDATE</span>
                  )}
                </span>
                <span className="subtle" style={{ display: "block", fontWeight: 600, fontSize: "0.78rem", marginTop: 2 }}>{t(`settings.cat.${c.id}Desc`)}</span>
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
      <button className="btn btn-ghost" style={{ padding: "0.35rem 0.7rem", marginBottom: "1rem" }} onClick={() => setSection(null)}>
        <Icon name="back" size={16} /> {t("settings.title")}
      </button>
      <h1 className="heading" style={{ fontSize: "1.6rem", margin: "0 0 1.2rem" }}>{t(`settings.cat.${section}`)}</h1>

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
