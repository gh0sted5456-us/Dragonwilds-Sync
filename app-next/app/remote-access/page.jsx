"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { api, Icon, toast } from "@/components/ui";

// The world tabs a code can be granted, in display order. Labels reuse the existing
// world.tab.* strings. New codes default to everything except Admin.
const TAB_DEFS = [
  ["overview", "world.tab.overview"], ["players", "world.tab.players"], ["deaths", "world.tab.deaths"],
  ["map", "world.tab.map"], ["broadcast", "world.tab.broadcast"], ["chat", "world.tab.chat"],
  ["console", "world.tab.console"], ["settings", "world.tab.settings"], ["backups", "world.tab.backups"],
  ["schedule", "world.tab.schedule"], ["mods", "world.tab.mods"], ["discord", "world.tab.discord"],
  ["discordbot", "world.tab.discordBot"], ["admin", "world.tab.admin"],
];
const DEFAULT_TABS = TAB_DEFS.map(([id]) => id).filter((id) => id !== "admin");

export default function RemoteAccessPage() {
  const { t } = useTranslation();
  const [cfg, setCfg] = useState(null);
  const [codes, setCodes] = useState([]);
  const [worlds, setWorlds] = useState([]);
  const [busy, setBusy] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [editing, setEditing] = useState(null); // code object or {__new:true}
  const [auditFor, setAuditFor] = useState(null); // code object
  const isElectron = typeof window !== "undefined" && window.desktop?.isElectron;

  const loadCfg = useCallback(() => api("/api/remote/config").then(setCfg).catch(() => {}), []);
  const loadCodes = useCallback(() => api("/api/remote/codes").then((r) => setCodes(r.codes || [])).catch(() => {}), []);

  useEffect(() => {
    loadCfg();
    loadCodes();
    api("/api/worlds").then((r) => setWorlds(r.worlds || [])).catch(() => {});
  }, [loadCfg, loadCodes]);

  // Live active/inactive + activity for the codes list.
  useEffect(() => {
    const id = setInterval(loadCodes, 4000);
    return () => clearInterval(id);
  }, [loadCodes]);

  const setEnabled = async (on) => {
    setBusy(true);
    try {
      const r = await api("/api/remote/config", { method: "POST", body: { enabled: on } });
      setCfg(r);
      toast(on ? t("remote.enabledToast") : t("remote.disabledToast"), "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  };

  const setLan = async (on) => {
    setBusy(true);
    try {
      const r = await api("/api/remote/config", { method: "POST", body: { lanBind: on } });
      setCfg(r);
      if (isElectron && window.desktop?.setLanBind) {
        setRestarting(true);
        try { await window.desktop.setLanBind(on); } catch {}
        setRestarting(false);
        await loadCfg();
      }
      toast(on ? t("remote.lanOnToast") : t("remote.lanOffToast"), "success");
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); setRestarting(false); }
  };

  const toggleCode = async (c, on) => {
    try {
      await api(`/api/remote/codes/${c.id}`, { method: "PATCH", body: { enabled: on } });
      loadCodes();
    } catch (e) { toast(e.message, "error"); }
  };

  const deleteCode = async (c) => {
    if (!confirm(t("remote.deleteConfirm", { code: c.code }))) return;
    try {
      await api(`/api/remote/codes/${c.id}`, { method: "DELETE" });
      toast(t("remote.deletedToast"), "success");
      loadCodes();
    } catch (e) { toast(e.message, "error"); }
  };

  if (!cfg) return <div className="subtle" style={{ fontWeight: 700 }}>{t("common.loading")}</div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.7rem", marginBottom: "0.4rem" }}>
        <Icon name="share" size={26} />
        <h1 className="heading" style={{ fontSize: "1.7rem", margin: 0 }}>{t("remote.title")}</h1>
      </div>
      <p className="subtle" style={{ fontWeight: 600, fontSize: "0.86rem", marginTop: 0, maxWidth: 720 }}>
        {t("remote.intro")}
      </p>

      {/* Enable + access */}
      <div className="panel" style={{ padding: "1.2rem", marginTop: "1rem" }}>
        <ToggleRow
          title={t("remote.enableTitle")}
          desc={t("remote.enableDesc")}
          on={cfg.enabled} busy={busy}
          onChange={setEnabled}
        />
        {cfg.enabled && (
          <>
            <div style={{ borderTop: "1px solid var(--line)", margin: "1rem 0" }} />
            <ToggleRow
              title={t("remote.lanTitle")}
              desc={isElectron ? t("remote.lanDesc") : t("remote.lanDescWeb")}
              on={cfg.lanBind} busy={busy || restarting}
              onChange={setLan}
            />
            {restarting && <div className="subtle" style={{ fontWeight: 700, fontSize: "0.8rem", marginTop: 8 }}>{t("remote.restarting")}</div>}
          </>
        )}
      </div>

      {/* URLs */}
      {cfg.enabled && (
        <div className="panel" style={{ padding: "1.2rem", marginTop: "1rem" }}>
          <h3 className="heading" style={{ fontSize: "1.05rem", marginTop: 0 }}>{t("remote.urlsTitle")}</h3>
          <div style={{ display: "grid", gap: "0.5rem" }}>
            {cfg.lanBind && (cfg.lan || []).map((a) => (
              <UrlRow key={a.address} label={a.primary ? t("remote.lanUrl") : t("remote.otherAdapter")} url={a.url} accent={a.primary} />
            ))}
            <UrlRow label={t("remote.thisPcUrl")} url={cfg.local} />
            {!cfg.lanBind && (
              <div className="subtle" style={{ fontSize: "0.78rem", fontWeight: 600, marginTop: 4 }}>
                {t("remote.lanOffHint")}
              </div>
            )}
          </div>
          <div className="panel-inset" style={{ padding: "0.7rem 0.9rem", marginTop: "0.9rem", fontSize: "0.78rem", fontWeight: 600 }}>
            <Icon name="info" size={14} /> {t("remote.tunnelHint")}
          </div>
        </div>
      )}

      {/* Codes */}
      <div className="panel" style={{ padding: "1.2rem", marginTop: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.8rem", flexWrap: "wrap", gap: "0.5rem" }}>
          <h3 className="heading" style={{ fontSize: "1.05rem", margin: 0 }}>{t("remote.codesTitle")}</h3>
          <button className="btn btn-primary" onClick={() => setEditing({ __new: true })}>
            <Icon name="plus" size={16} /> {t("remote.newCode")}
          </button>
        </div>

        {codes.length === 0 ? (
          <p className="subtle" style={{ fontWeight: 700 }}>{t("remote.noCodes")}</p>
        ) : (
          <div style={{ display: "grid", gap: "0.6rem" }}>
            {codes.map((c) => (
              <CodeRow key={c.id} code={c} t={t}
                onToggle={(on) => toggleCode(c, on)}
                onEdit={() => setEditing(c)}
                onDelete={() => deleteCode(c)}
                onLog={() => setAuditFor(c)} />
            ))}
          </div>
        )}
      </div>

      {editing && (
        <CodeModal
          t={t} worlds={worlds}
          code={editing.__new ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); loadCodes(); }}
        />
      )}
      {auditFor && <AuditDrawer t={t} code={auditFor} onClose={() => setAuditFor(null)} />}
    </div>
  );
}

function ToggleRow({ title, desc, on, busy, onChange }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
      <div style={{ minWidth: 0 }}>
        <div className="heading" style={{ fontSize: "0.95rem" }}>{title}</div>
        <div className="subtle" style={{ fontWeight: 600, fontSize: "0.8rem", marginTop: 2 }}>{desc}</div>
      </div>
      <Switch on={on} busy={busy} onChange={onChange} />
    </div>
  );
}

function Switch({ on, busy, onChange }) {
  return (
    <button disabled={busy} onClick={() => onChange(!on)} aria-pressed={on}
      style={{
        flexShrink: 0, width: 46, height: 26, borderRadius: 999, border: "none", cursor: busy ? "wait" : "pointer",
        background: on ? "var(--green-bright, var(--accent))" : "var(--line-strong)",
        position: "relative", transition: "background 0.2s", opacity: busy ? 0.6 : 1,
      }}>
      <span style={{
        position: "absolute", top: 3, left: on ? 23 : 3, width: 20, height: 20, borderRadius: 999,
        background: "#fff", transition: "left 0.2s",
      }} />
    </button>
  );
}

function UrlRow({ label, url, accent }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = () => { try { navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch {} };
  return (
    <div className="panel-inset" style={{ display: "flex", alignItems: "center", gap: "0.7rem", padding: "0.55rem 0.9rem", borderLeft: accent ? "3px solid var(--accent)" : undefined }}>
      <Icon name="globe" size={16} />
      <div style={{ lineHeight: 1.2, minWidth: 0 }}>
        <div className="subtle" style={{ fontSize: "0.62rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
        <code style={{ fontSize: "0.9rem", fontWeight: 700, wordBreak: "break-all" }}>{url}</code>
      </div>
      <button className="btn btn-ghost" style={{ marginLeft: "auto", padding: "0.35rem 0.7rem", fontSize: "0.78rem" }} onClick={copy}>
        {copied ? t("common.copied") : t("common.copy")}
      </button>
    </div>
  );
}

function CodeRow({ code, t, onToggle, onEdit, onDelete, onLog }) {
  const active = code.activeSessions > 0;
  const scopeLabel = code.scope === "world" ? (code.worldName || t("remote.scopeWorld")) : t("remote.scopeFull");
  return (
    <div className="panel-inset" style={{ padding: "0.8rem 1rem", display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", minWidth: 150 }}>
        <span title={active ? t("remote.active") : t("remote.inactive")} style={{ width: 9, height: 9, borderRadius: 999, flexShrink: 0, background: active ? "var(--green-bright, var(--accent))" : "var(--line-strong)" }} />
        <code style={{ fontSize: "1.35rem", fontWeight: 800, letterSpacing: "0.12em" }}>{code.code}</code>
      </div>
      <div style={{ flex: 1, minWidth: 160 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
          {code.label && <span style={{ fontWeight: 700, fontSize: "0.86rem" }}>{code.label}</span>}
          <span className="chip" style={{ background: "var(--card-2)", border: "1px solid var(--line)" }}>{scopeLabel}</span>
          <span className="chip" style={{ background: "var(--card-2)", border: "1px solid var(--line)" }}>{t("remote.tabsCount", { count: code.tabs.length })}</span>
          {code.tabs.includes("admin") && <span className="chip" style={{ background: "var(--yellow)", color: "#1e1f22" }}>{t("world.tab.admin")}</span>}
        </div>
        <div className="subtle" style={{ fontWeight: 600, fontSize: "0.72rem", marginTop: 3 }}>
          {active ? t("remote.activeCount", { count: code.activeSessions }) : t("remote.inactive")}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
        <button className="btn btn-ghost" style={{ padding: "0.35rem 0.6rem", fontSize: "0.78rem" }} onClick={onLog} title={t("remote.viewLog")}><Icon name="eye" size={15} /></button>
        <button className="btn btn-ghost" style={{ padding: "0.35rem 0.6rem", fontSize: "0.78rem" }} onClick={onEdit}>{t("common.edit")}</button>
        <button className="btn btn-ghost" style={{ padding: "0.35rem 0.6rem", fontSize: "0.78rem", color: "var(--red)" }} onClick={onDelete}><Icon name="trash" size={15} /></button>
        <Switch on={code.enabled} onChange={onToggle} />
      </div>
    </div>
  );
}

function CodeModal({ t, worlds, code, onClose, onSaved }) {
  const [scope, setScope] = useState(code?.scope || "full");
  const [worldId, setWorldId] = useState(code?.worldId || (worlds[0]?.world_id ?? ""));
  const [label, setLabel] = useState(code?.label || "");
  const [tabs, setTabs] = useState(code?.tabs || DEFAULT_TABS);
  const [busy, setBusy] = useState(false);
  const toggleTab = (id) => setTabs((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const save = async () => {
    if (scope === "world" && !worldId) return toast(t("remote.pickWorld"), "error");
    setBusy(true);
    const body = { scope, worldId: scope === "world" ? worldId : null, tabs, label };
    try {
      if (code) await api(`/api/remote/codes/${code.id}`, { method: "PATCH", body });
      else await api("/api/remote/codes", { method: "POST", body });
      toast(t("remote.savedToast"), "success");
      onSaved();
    } catch (e) { toast(e.message, "error"); setBusy(false); }
  };

  return (
    <Backdrop onClose={onClose}>
      <div className="panel" style={{ width: "100%", maxWidth: 560, padding: "1.4rem", maxHeight: "88vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.9rem" }}>
          <h3 className="heading" style={{ fontSize: "1.15rem", margin: 0 }}>{code ? t("remote.editCode") : t("remote.newCode")}</h3>
          <button className="btn btn-ghost" style={{ padding: "0.3rem 0.5rem" }} onClick={onClose}><Icon name="x" size={16} /></button>
        </div>

        {code && (
          <div className="panel-inset" style={{ padding: "0.6rem 0.9rem", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <Icon name="key" size={16} />
            <code style={{ fontSize: "1.3rem", fontWeight: 800, letterSpacing: "0.12em" }}>{code.code}</code>
          </div>
        )}

        <label className="label">{t("remote.labelField")}</label>
        <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} placeholder={t("remote.labelPlaceholder")} />

        <label className="label" style={{ marginTop: "1rem" }}>{t("remote.scopeField")}</label>
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.4rem", flexWrap: "wrap" }}>
          <ScopeBtn active={scope === "full"} onClick={() => setScope("full")} title={t("remote.scopeFull")} desc={t("remote.scopeFullDesc")} />
          <ScopeBtn active={scope === "world"} onClick={() => setScope("world")} title={t("remote.scopeWorld")} desc={t("remote.scopeWorldDesc")} />
        </div>
        {scope === "world" && (
          <select className="input" value={worldId} onChange={(e) => setWorldId(e.target.value)}>
            {worlds.length === 0 && <option value="">{t("remote.noWorlds")}</option>}
            {worlds.map((w) => <option key={w.world_id} value={w.world_id}>{w.display_name}</option>)}
          </select>
        )}

        <label className="label" style={{ marginTop: "1rem" }}>{t("remote.tabsField")}</label>
        <div className="subtle" style={{ fontWeight: 600, fontSize: "0.76rem", marginBottom: "0.5rem" }}>{t("remote.tabsHelp")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px,1fr))", gap: "0.4rem" }}>
          {TAB_DEFS.map(([id, key]) => (
            <label key={id} style={{ display: "flex", alignItems: "center", gap: "0.45rem", padding: "0.4rem 0.6rem", borderRadius: 8, cursor: "pointer", background: tabs.includes(id) ? "var(--card-2)" : "transparent", border: `1px solid ${tabs.includes(id) ? "var(--accent)" : "var(--line)"}` }}>
              <input type="checkbox" checked={tabs.includes(id)} onChange={() => toggleTab(id)} />
              <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>{t(key)}{id === "admin" ? " ⚠️" : ""}</span>
            </label>
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1.3rem" }}>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>{t("common.cancel")}</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? t("common.saving") : t("common.save")}</button>
        </div>
      </div>
    </Backdrop>
  );
}

function ScopeBtn({ active, onClick, title, desc }) {
  return (
    <button onClick={onClick} className="panel-inset" style={{ flex: 1, minWidth: 160, textAlign: "left", padding: "0.7rem 0.9rem", cursor: "pointer", border: `1px solid ${active ? "var(--accent)" : "var(--line)"}`, background: active ? "var(--card-2)" : "transparent" }}>
      <div className="heading" style={{ fontSize: "0.88rem" }}>{title}</div>
      <div className="subtle" style={{ fontWeight: 600, fontSize: "0.72rem", marginTop: 2 }}>{desc}</div>
    </button>
  );
}

function AuditDrawer({ t, code, onClose }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    api(`/api/remote/codes/${code.id}/audit`).then((r) => setRows(r.audit || [])).catch(() => setRows([]));
  }, [code.id]);
  return (
    <Backdrop onClose={onClose}>
      <div className="panel" style={{ width: "100%", maxWidth: 620, padding: "1.4rem", maxHeight: "88vh", display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.9rem" }}>
          <h3 className="heading" style={{ fontSize: "1.15rem", margin: 0 }}>{t("remote.logTitle", { code: code.code })}</h3>
          <button className="btn btn-ghost" style={{ padding: "0.3rem 0.5rem" }} onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        {rows === null ? <p className="subtle" style={{ fontWeight: 700 }}>{t("common.loading")}</p> :
          rows.length === 0 ? <p className="subtle" style={{ fontWeight: 700 }}>{t("remote.noLog")}</p> : (
            <div style={{ display: "grid", gap: "0.3rem", overflow: "auto" }}>
              {rows.map((r) => (
                <div key={r.id} className="panel-inset" style={{ padding: "0.45rem 0.7rem", fontSize: "0.78rem", display: "flex", justifyContent: "space-between", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 700 }}>
                    <span className="chip" style={{ background: r.action === "denied" ? "var(--red)" : "var(--card-2)", color: r.action === "denied" ? "#fff" : undefined, border: "1px solid var(--line)", marginRight: 8 }}>{r.action}</span>
                    {r.detail || ""}
                  </span>
                  <span className="subtle" style={{ fontWeight: 700, fontSize: "0.7rem", whiteSpace: "nowrap" }}>{new Date(r.ts).toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
      </div>
    </Backdrop>
  );
}

function Backdrop({ children, onClose }) {
  return (
    <div onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "grid", placeItems: "center", zIndex: 60, padding: "1rem" }}>
      {children}
    </div>
  );
}
