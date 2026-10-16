"use client";
import { useEffect, useRef, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { api, Icon, toast } from "@/components/ui";
import { useJobsPoll, JobCard } from "@/components/jobsClient";

function stripWrappingQuotes(value) {
  const text = value == null ? "" : String(value);
  if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
    return text.slice(1, -1);
  }
  return text;
}

export default function AdminPanel({ world, running, onChange }) {
  const { t } = useTranslation();
  const [name, setName] = useState(world.display_name);
  const [password, setPassword] = useState(world.admin_password);
  const [serverPassword, setServerPassword] = useState(stripWrappingQuotes(world.server_password));
  const [extraArgs, setExtraArgs] = useState(world.extra_args || "");
  const [envVars, setEnvVars] = useState(envObjectToText(world.env_vars));
  const [wineBinary, setWineBinary] = useState(world.wine_binary || "wine");
  const [winePrefix, setWinePrefix] = useState(world.wine_prefix || "");
  const [wineLaunchFlags, setWineLaunchFlags] = useState(world.wine_launch_flags || "");
  const [crashGuard, setCrashGuard] = useState(!!world.crash_guard);
  const [autoUpdate, setAutoUpdate] = useState(!!world.auto_update);
  const [saving, setSaving] = useState(false);
  const [installDir, setInstallDir] = useState(world.install_dir || "");
  const [ownerId, setOwnerId] = useState(world.owner_id || "");
  const [defaultWorldName, setDefaultWorldName] = useState(world.default_world_name || "");
  const [movingDir, setMovingDir] = useState(false);
  const [migrationPlan, setMigrationPlan] = useState(null);
  const [migrationError, setMigrationError] = useState("");
  const [reviewingMigration, setReviewingMigration] = useState(false);
  const [migrationConfirmed, setMigrationConfirmed] = useState(false);
  const [requestingMigration, setRequestingMigration] = useState(false);
  const [forkJobId, setForkJobId] = useState(null);
  const forkJobs = useJobsPoll();
  const forkJob = forkJobs.find((job) => job.id === forkJobId);
  const forkNotified = useRef(false);
  useEffect(() => {
    let cancelled = false;
    setInstallDir(world.install_dir || "");
    setMigrationConfirmed(false);
    setReviewingMigration(false);
    api(`/api/worlds/${world.world_id}/fork`).then((r) => {
      if (!cancelled) { setMigrationPlan(r.plan); setMigrationError(""); }
    }).catch((e) => { if (!cancelled) { setMigrationPlan(null); setMigrationError(e.message); } });
    return () => { cancelled = true; };
  }, [world.world_id, world.install_dir, running]);
  useEffect(() => {
    if (forkJob?.status !== "success" || forkNotified.current) return;
    forkNotified.current = true;
    setMigrationPlan(null);
    setReviewingMigration(false);
    toast("Migration verified. Original files retained; Server remains stopped.", "success");
    onChange();
  }, [forkJob?.status, onChange]);
  const [ports, setPorts] = useState({ game_port: world.game_port, query_port: world.query_port, rest_api_port: world.rest_api_port });
  const [savingPorts, setSavingPorts] = useState(false);
  const isElectron = typeof window !== "undefined" && window.desktop?.isElectron;
  const portsChanged = ["game_port", "query_port", "rest_api_port"].some((k) => Number(ports[k]) !== Number(world[k]));
  const migrating = requestingMigration || forkJob?.status === "running";

  const savePorts = async () => {
    if (running) return toast(t("admin.stopBeforePorts"), "error");
    setSavingPorts(true);
    try {
      await api(`/api/worlds/${world.world_id}`, { method: "PATCH", body: ports });
      toast(t("admin.portsUpdated"), "success");
      onChange();
    } catch (e) { toast(e.message, "error"); }
    finally { setSavingPorts(false); }
  };

  const pickDir = async () => {
    if (isElectron) { const p = await window.desktop.pickDirectory(); if (p) setInstallDir(p); }
    else toast(t("create.typePathToast"));
  };

  const changeInstallDir = async () => {
    const target = installDir.trim();
    if (!target || target === world.install_dir) return;
    if (running) return toast(t("admin.stopBeforeFolder"), "error");
    setMovingDir(true);
    try {
      await api(`/api/worlds/${world.world_id}`, { method: "PATCH", body: { install_dir: target } });
      toast(t("admin.installFolderUpdated"), "success");
      onChange();
    } catch (e) { toast(e.message, "error"); }
    finally { setMovingDir(false); }
  };

  const reviewMigration = async () => {
    try {
      const result = await api(`/api/worlds/${world.world_id}/fork`);
      setMigrationPlan(result.plan); setMigrationError(""); setMigrationConfirmed(false);
      setReviewingMigration(true);
    } catch (e) { setMigrationError(e.message); toast(e.message, "error"); }
  };

  const migrateInstall = async () => {
    if (!migrationConfirmed || !migrationPlan?.canMigrate || migrating) return;
    setRequestingMigration(true);
    try {
      const { source, destination, coreDir } = migrationPlan;
      const result = await api(`/api/worlds/${world.world_id}/fork`, { method: "POST", body: { confirm: true, source, destination, coreDir } });
      forkNotified.current = false;
      setForkJobId(result.jobId);
      try { window.dispatchEvent(new Event("rsdw-jobs-ping")); } catch {}
      toast("Migrating and verifying Server files. Follow progress in Downloads.", "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setRequestingMigration(false); }
  };

  const saveProfile = async () => {
    setSaving(true);
    try {
      await api(`/api/worlds/${world.world_id}`, {
        method: "PATCH",
        body: {
          display_name: name, admin_password: password, server_password: stripWrappingQuotes(serverPassword),
          extra_args: extraArgs, env_vars: envTextToObject(envVars),
                crash_guard: crashGuard ? 1 : 0,
                auto_update: autoUpdate ? 1 : 0,
                owner_id: ownerId.trim() || null, default_world_name: defaultWorldName.trim() || null,
        },
      });
      toast(t("admin.profileSaved"), "success");
      onChange();
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  };

  const saveWine = async () => {
    if (running) return toast(t("admin.stopBeforeWine"), "error");
    setSaving(true);
    try {
      await api(`/api/worlds/${world.world_id}`, {
        method: "PATCH",
        body: {
          wine_binary: wineBinary.trim() || "wine",
                wine_prefix: winePrefix.trim() || null,
                wine_launch_flags: wineLaunchFlags.trim(),
        },
      });
      toast(t("admin.profileSaved"), "success");
      onChange();
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  };

  return (
    <div style={{ display: "grid", gap: "1.6rem" }}>
      <section>
        <h3 className="heading" style={{ fontSize: "1rem" }}>{t("admin.worldProfile")}</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
          <div>
            <label className="label">{t("admin.displayName")}</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="label">{t("admin.adminPasswordRest")}</label>
            <input className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="label">{t("admin.serverPassword")}</label>
            <input className="input" value={serverPassword} onChange={(e) => setServerPassword(e.target.value)} placeholder={t("admin.serverPasswordPlaceholder")} />
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.74rem", marginTop: 4 }}>
              <Trans i18nKey="admin.serverPasswordHint" components={{ code: <code /> }} />
            </p>
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="label">{t("admin.extraArgs")}</label>
            <input className="input" value={extraArgs} onChange={(e) => setExtraArgs(e.target.value)} placeholder="Optional dedicated-server arguments" />
          </div>
          <div>
            <label className="label">Owner ID</label>
            <input className="input" value={ownerId} onChange={(e) => setOwnerId(e.target.value)} placeholder="Owner's Player ID (required)" />
          </div>
          <div>
            <label className="label">Default world name</label>
            <input className="input" value={defaultWorldName} onChange={(e) => setDefaultWorldName(e.target.value)} placeholder="DefaultWorldName" />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="label">{t("admin.envVars")}</label>
            <textarea className="input" rows={3} style={{ fontFamily: "monospace", resize: "vertical" }}
              value={envVars} onChange={(e) => setEnvVars(e.target.value)}
              placeholder={"WINEDEBUG=-all\nSOME_VAR=value"} />
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.74rem", marginTop: 4 }}>{t("admin.envVarsHint")}</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: "0.8rem", marginTop: "0.9rem", flexWrap: "wrap" }}>
          <Toggle label={t("admin.crashGuard")} on={crashGuard} onClick={() => setCrashGuard((v) => !v)} />
          <Toggle label="Update and restart automatically" on={autoUpdate} onClick={() => setAutoUpdate((v) => !v)} />
        </div>
        <p className="subtle" style={{ fontWeight: 600, fontSize: "0.72rem", marginTop: 6 }}>
          When Steam publishes a new dedicated-server build, RSDW warns connected players, stops this profile, validates the update through SteamCMD, and restarts only after verification succeeds.
        </p>

        {world.platform === "windows" && (
          <div className="panel-inset" style={{ padding: "0.9rem 1.1rem", marginTop: "0.9rem" }}>
            <div className="heading" style={{ fontSize: "0.92rem" }}>{t("admin.wineTitle")}</div>
            <p className="subtle" style={{ fontWeight: 600, fontSize: "0.78rem", marginTop: 2 }}>{t("admin.wineDesc")}</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem", marginTop: "0.6rem" }}>
              <div>
                <label className="label">{t("admin.wineBinary")}</label>
                <input className="input" value={wineBinary} onChange={(e) => setWineBinary(e.target.value)} disabled={running} placeholder="wine" />
              </div>
              <div>
                <label className="label">{t("admin.winePrefix")}</label>
                <input className="input" value={winePrefix} onChange={(e) => setWinePrefix(e.target.value)} disabled={running} placeholder={t("admin.winePrefixPlaceholder")} />
              </div>
              <div style={{ gridColumn: "1 / -1" }}>
                <label className="label">{t("admin.wineLaunchFlags")}</label>
                <input className="input" value={wineLaunchFlags} onChange={(e) => setWineLaunchFlags(e.target.value)} disabled={running} placeholder={t("admin.wineLaunchFlagsPlaceholder")} />
                <p className="subtle" style={{ fontWeight: 600, fontSize: "0.74rem", marginTop: 4 }}>
                  {t("admin.wineLaunchFlagsHint")}
                </p>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.7rem" }}>
              <button className="btn btn-ghost" onClick={saveWine} disabled={saving || running}>
                {saving ? t("common.saving") : t("common.save")}
              </button>
            </div>
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1rem" }}>
          <button className="btn btn-primary" onClick={saveProfile} disabled={saving}><Icon name="download" /> {saving ? t("common.saving") : t("admin.saveProfile")}</button>
        </div>
        {world.crash_count > 0 && (
          <p className="subtle" style={{ fontWeight: 700, fontSize: "0.76rem", marginTop: "0.6rem" }}>
            {t("admin.crashRestarted", { count: world.crash_count })}
          </p>
        )}
      </section>

      <section>
        <h3 className="heading" style={{ fontSize: "1rem" }}>{t("admin.installFolder")}</h3>
        <p className="subtle" style={{ fontWeight: 600, fontSize: "0.8rem", marginTop: 0, marginBottom: "0.6rem" }}>
          <Trans i18nKey="admin.installFolderDesc" components={{ code: <code /> }} />
        </p>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input className="input" value={installDir} onChange={(e) => setInstallDir(e.target.value)}
            disabled={running || movingDir || migrating}
            placeholder={isElectron ? t("create.browseFolderPlaceholder") : "e.g. D:\\SteamLibrary\\steamapps\\common\\GameServer"} />
          <button className="btn btn-ghost" onClick={pickDir} disabled={running || movingDir || migrating}><Icon name="folder" /> {t("common.browse")}</button>
          <button className="btn btn-primary" onClick={changeInstallDir}
            disabled={running || movingDir || migrating || !installDir.trim() || installDir.trim() === world.install_dir}>
            {movingDir ? t("common.checking") : t("common.change")}
          </button>
        </div>
        {running && <p className="subtle" style={{ fontWeight: 700, fontSize: "0.74rem", marginTop: 4 }}>{t("admin.stopToChangeFolder")}</p>}
        <div className="panel-inset" style={{ marginTop: 12, padding: ".9rem" }}>
          <strong>Managed Server folder migration</strong>
          <p className="subtle" style={{ fontSize: ".78rem", margin: "6px 0 10px" }}>Copy an older private or shared installation into the configured RSDW/Profiles folder. Saves, settings, credentials and mods are verified before switching paths. The original folder remains available for recovery. Migration never starts or restarts the Server.</p>
          {(migrationError || (migrationPlan && !migrationPlan.canMigrate)) && <p className="subtle" role="status">{migrationError || migrationPlan.reason}</p>}
          <button className="btn btn-ghost" disabled={running || migrating} onClick={reviewMigration}><Icon name="folder" /> Review migration</button>
          {reviewingMigration && migrationPlan && <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
            <div><span className="label">Current folder · retained as recovery copy</span><code style={{ display: "block", overflowWrap: "anywhere" }}>{migrationPlan.source}</code></div>
            <div><span className="label">New private profile folder</span><code style={{ display: "block", overflowWrap: "anywhere" }}>{migrationPlan.destination}</code></div>
            <div><span className="label">Shared Server Core</span><code style={{ display: "block", overflowWrap: "anywhere" }}>{migrationPlan.coreDir}</code></div>
            {migrationPlan.shared && <p className="subtle">This shared folder must contain this profile's current save. All hosted Servers must be stopped.</p>}
            {migrationPlan.resume && <p className="subtle">An interrupted migration left a verified copy. Both folders will be checked again before completing.</p>}
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}><input type="checkbox" checked={migrationConfirmed} disabled={!migrationPlan.canMigrate || migrating} onChange={(e) => setMigrationConfirmed(e.target.checked)} /> I reviewed these paths and confirmed that the current save belongs to this profile.</label>
            <div><button className="btn btn-primary" disabled={running || migrating || !migrationConfirmed || !migrationPlan.canMigrate} onClick={migrateInstall}>{migrating ? "Migrating…" : migrationPlan.resume ? "Verify and finish migration" : "Migrate and verify"}</button></div>
          </div>}
        </div>
        {forkJob && <div style={{ marginTop: 10 }}><JobCard job={forkJob} defaultShowLog /></div>}
      </section>

      <section>
        <h3 className="heading" style={{ fontSize: "1rem" }}>{t("admin.connection")}</h3>
        <div className="panel-inset" style={{ padding: "0.8rem 1rem", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", gap: "0.6rem" }}>
          <PortField label={t("admin.portGameUdp")} value={ports.game_port} disabled={running} onChange={(v) => setPorts((p) => ({ ...p, game_port: v }))} />
          <PortField label={t("admin.portQuery")} value={ports.query_port} disabled={running} onChange={(v) => setPorts((p) => ({ ...p, query_port: v }))} />
          <PortField label={t("admin.portRest")} value={ports.rest_api_port} disabled={running} onChange={(v) => setPorts((p) => ({ ...p, rest_api_port: v }))} />
        </div>
        <p className="subtle" style={{ fontWeight: 700, fontSize: "0.74rem", marginTop: "0.5rem" }}>
          {t("admin.portsHint")}
          {running ? t("admin.portsHintStop") : t("admin.portsHintNext")}
        </p>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.6rem" }}>
          <button className="btn btn-primary" onClick={savePorts} disabled={running || savingPorts || !portsChanged}>
            {savingPorts ? t("common.saving") : t("admin.savePorts")}
          </button>
        </div>
      </section>
    </div>
  );
}

function PortField({ label, value, onChange, disabled }) {
  return (
    <div>
      <label className="label" style={{ fontSize: "0.7rem" }}>{label}</label>
      <input className="input" type="number" value={value} disabled={disabled}
        onChange={(e) => onChange(parseInt(e.target.value || "0", 10))} />
    </div>
  );
}

function Toggle({ label, on, onClick }) {
  return (
    <button className={`btn ${on ? "btn-primary" : "btn-ghost"}`} onClick={onClick}>
      <span className="statdot" style={{ background: on ? "var(--accent-ink)" : "var(--ink-soft)" }} /> {label}
    </button>
  );
}

// worlds.env_vars is stored as a JSON object; the UI edits it as plain
// "KEY=value" lines, one per line, "#" for comments.
function envObjectToText(json) {
  try {
    const obj = JSON.parse(json || "{}");
    return Object.entries(obj).map(([k, v]) => `${k}=${v}`).join("\n");
  } catch { return ""; }
}
function envTextToObject(text) {
  const out = {};
  for (const raw of String(text).split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const i = line.indexOf("=");
    if (i === -1) continue;
    const k = line.slice(0, i).trim();
    if (k) out[k] = line.slice(i + 1).trim();
  }
  return out;
}
