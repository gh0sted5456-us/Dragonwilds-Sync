"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";
import { api, Icon, toast } from "@/components/ui";

export default function CreateWorldModal({ onClose, onDone }) {
  return (
    <Overlay onClose={onClose}>
      <div className="panel" style={{ width: 640, maxWidth: "94vw", maxHeight: "90vh", overflow: "auto", padding: "1.5rem" }}>
        <CreateProfile onClose={onClose} onDone={onDone} />
      </div>
    </Overlay>
  );
}

function usePorts() {
  const [ports, setPorts] = useState(null);
  useEffect(() => { api("/api/ports").then((r) => setPorts(r.ports)).catch(() => {}); }, []);
  return [ports, setPorts];
}

function CreateProfile({ onClose, onDone }) {
  const { t } = useTranslation();
  const [server, setServer] = useState(null);
  const [name, setName] = useState(t("create.defaultWorldName"));
  const [ownerId, setOwnerId] = useState("");
  const [defaultWorldName, setDefaultWorldName] = useState("");
  const [ports, setPorts] = usePorts();
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api("/api/application-setup/server").then((r) => setServer(r.server)).catch(() => setServer({ ready: false }));
  }, []);

  const create = async () => {
    if (!server?.ready) return toast("Run Application Setup → Server first.", "error");
    setSaving(true);
    try {
      await api("/api/provision", { method: "POST", body: {
        display_name: name,
        ports,
        admin_password: password || undefined,
        owner_id: ownerId || undefined,
        default_world_name: defaultWorldName || undefined,
      }});
      toast("Server profile created.", "success");
      onDone();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return <div>
    <Header title="Create Server Profile" onClose={onClose} />
    <p className="subtle" style={{ fontWeight: 650, marginTop: 0 }}>
      Profiles do not install Dragonwilds. They use the machine-level dedicated-server lane prepared in Application Setup.
    </p>

    {!server ? (
      <div className="panel-inset subtle" style={{ padding: 12 }}>Checking Server lane…</div>
    ) : !server.ready ? (
      <div className="panel-inset" style={{ padding: 14, borderLeft: "3px solid var(--yellow)", marginBottom: 14 }}>
        <strong>Server lane is not configured.</strong>
        <p className="subtle" style={{ margin: "5px 0 10px", fontSize: ".8rem" }}>
          Install or link the generic dedicated-server files once, then create as many Server profiles as you want.
        </p>
        <Link href="/setup" className="btn btn-primary" onClick={onClose}><Icon name="settings" /> Open Application Setup</Link>
      </div>
    ) : (
      <div className="panel-inset" style={{ padding: 12, marginBottom: 14, borderLeft: "3px solid var(--accent)" }}>
        <strong>Using shared Server lane</strong>
        <div className="subtle" style={{ marginTop: 3, fontSize: ".76rem", wordBreak: "break-all" }}>
          {server.installDir} · build {server.buildId || "unknown"}
        </div>
      </div>
    )}

    <div style={{ display: "grid", gap: "0.9rem" }}>
      <Field label={t("create.worldName")}><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <PortGrid ports={ports} setPorts={setPorts} />
      <Field label={t("create.adminPassword")} hint={t("create.adminPasswordHint")}>
        <input className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <Field label="OwnerId" hint="The owner's Player ID for this World profile.">
        <input className="input" value={ownerId} onChange={(e) => setOwnerId(e.target.value)} placeholder="e.g. 7656119..." />
      </Field>
      <Field label="Default world name">
        <input className="input" value={defaultWorldName} onChange={(e) => setDefaultWorldName(e.target.value)} placeholder={t("create.defaultWorldName")} />
      </Field>
      <Actions>
        <button className="btn btn-ghost" onClick={onClose}>{t("common.cancel")}</button>
        <button className="btn btn-primary" disabled={saving || !server?.ready} onClick={create}>
          <Icon name="plus" /> {saving ? "Creating…" : "Create Profile"}
        </button>
      </Actions>
    </div>
  </div>;
}

function PortGrid({ ports, setPorts }) {
  const { t } = useTranslation();
  if (!ports) return null;
  return (
    <div className="panel-inset" style={{ padding: "0.8rem", display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "0.6rem" }}>
      <PortField label={t("create.portGame")} v={ports.game_port} onChange={(v) => setPorts({ ...ports, game_port: v, query_port: v + 1 })} />
      <PortField label={t("create.portQuery")} v={ports.query_port} onChange={(v) => setPorts({ ...ports, query_port: v })} />
      <PortField label={t("create.portRest")} v={ports.rest_api_port} onChange={(v) => setPorts({ ...ports, rest_api_port: v })} />
      <PortField label={t("create.portRcon")} v={ports.rcon_port} onChange={(v) => setPorts({ ...ports, rcon_port: v })} />
    </div>
  );
}

function Header({ title, onClose }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.7rem", marginBottom: "1.1rem" }}>
      <h2 className="heading" style={{ fontSize: "1.25rem", margin: 0, flex: 1 }}>{title}</h2>
      <button className="btn btn-ghost" onClick={onClose}>×</button>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && <p className="subtle" style={{ fontSize: "0.74rem", fontWeight: 600, marginTop: 4, marginBottom: 0 }}>{hint}</p>}
    </div>
  );
}

function Actions({ children }) {
  return <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem", marginTop: "0.4rem" }}>{children}</div>;
}

function PortField({ label, v, onChange }) {
  return (
    <div>
      <label className="label" style={{ fontSize: "0.62rem" }}>{label}</label>
      <input className="input" type="number" value={v} onChange={(e) => onChange(parseInt(e.target.value || "0", 10))} style={{ padding: "0.35rem 0.5rem" }} />
    </div>
  );
}

export function Overlay({ children, onClose }) {
  const downOnBackdrop = useRef(false);
  return (
    <div
      onMouseDown={(e) => { downOnBackdrop.current = e.target === e.currentTarget; }}
      onClick={(e) => { if (onClose && e.target === e.currentTarget && downOnBackdrop.current) onClose(); }}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "grid", placeItems: "center", zIndex: 40, padding: "1rem" }}>
      <div>{children}</div>
    </div>
  );
}
