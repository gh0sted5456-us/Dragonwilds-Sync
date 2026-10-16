"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, Icon, toast } from "@/components/ui";
import { PageHeader } from "@/components/PageChrome";

const emptyLinks = { steam: "", epic: "", curseforge: "", nexus: "" };

function fileToDataUrl(file, maxBytes) {
  if (!file) return Promise.resolve(null);
  if (!/^image\/(png|jpe?g|webp)$/i.test(file.type)) return Promise.reject(new Error("Choose a PNG, JPEG, or WebP image."));
  if (file.size > maxBytes) return Promise.reject(new Error(`Image must be smaller than ${Math.round(maxBytes / 1024 / 1024)} MB.`));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Could not read that image."));
    reader.readAsDataURL(file);
  });
}

export default function ProfilePage() {
  const [data, setData] = useState({ profiles: [], activeId: null });
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState({ worlds: [], servers: [] });
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (preferredId) => {
    const result = await api("/api/launcher-profiles");
    setData(result);
    const id = preferredId || selectedId || result.activeId || result.profiles?.[0]?.profile_id;
    setSelectedId(id);
    if (id) {
      const info = await api(`/api/launcher-profiles/${id}`);
      setDraft({ ...info.profile, links: { ...emptyLinks, ...(info.profile.links || {}) } });
      setDetail({ worlds: info.worlds || [], servers: info.servers || [] });
    }
  }, [selectedId]);

  useEffect(() => { load().catch((error) => toast(error.message, "error")); }, []);

  const selected = useMemo(() => data.profiles.find((profile) => profile.profile_id === selectedId), [data, selectedId]);

  const select = async (id) => {
    setSelectedId(id);
    try {
      const info = await api(`/api/launcher-profiles/${id}`);
      setDraft({ ...info.profile, links: { ...emptyLinks, ...(info.profile.links || {}) } });
      setDetail({ worlds: info.worlds || [], servers: info.servers || [] });
    } catch (error) { toast(error.message, "error"); }
  };

  const create = async () => {
    try {
      const result = await api("/api/launcher-profiles", { method: "POST", body: { display_name: `Player ${data.profiles.length + 1}` } });
      window.dispatchEvent(new Event("rsdw-launcher-profile-updated"));
      await load(result.profile.profile_id);
      toast("Player profile created and activated.", "success");
    } catch (error) { toast(error.message, "error"); }
  };

  const activate = async () => {
    try {
      await api("/api/launcher-profiles/active", { method: "POST", body: { profileId: selectedId } });
      setData((current) => ({ ...current, activeId: selectedId }));
      window.dispatchEvent(new Event("rsdw-launcher-profile-updated"));
      toast("Profile activated. Worlds now follow this profile.", "success");
    } catch (error) { toast(error.message, "error"); }
  };

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    try {
      await api(`/api/launcher-profiles/${draft.profile_id}`, {
        method: "PATCH",
        body: { display_name: draft.display_name, icon_data: draft.icon_data, banner_data: draft.banner_data, links: draft.links },
      });
      await load(draft.profile_id);
      window.dispatchEvent(new Event("rsdw-launcher-profile-updated"));
      toast("Player profile saved.", "success");
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    if (!selected || data.profiles.length <= 1) return;
    if (!window.confirm(`Delete ${selected.display_name}? Its Worlds will move to another profile.`)) return;
    try {
      await api(`/api/launcher-profiles/${selected.profile_id}`, { method: "DELETE" });
      setSelectedId(null);
      window.dispatchEvent(new Event("rsdw-launcher-profile-updated"));
      await load();
      toast("Profile removed; its Worlds were preserved.", "success");
    } catch (error) { toast(error.message, "error"); }
  };

  const chooseImage = async (event, field, maxBytes) => {
    try {
      const value = await fileToDataUrl(event.target.files?.[0], maxBytes);
      if (value) setDraft((current) => ({ ...current, [field]: value }));
    } catch (error) { toast(error.message, "error"); }
    event.target.value = "";
  };

  if (!draft) return <div className="subtle" style={{ fontWeight: 700 }}>Loading player profile…</div>;

  return <div>
    <PageHeader backHref="/" backLabel="Back to World Management" eyebrow="PLAYER IDENTITY" title="Player Profiles" description="Switch identities to change the Worlds, saves, mod sets, and linked services shown in the launcher." icon="users" actions={<button className="btn btn-primary" onClick={create}><Icon name="plus" /> New Profile</button>} />

    <div className="profile-management-layout">
      <aside className="panel" style={{ padding: 8 }}>
        {data.profiles.map((profile) => <button key={profile.profile_id} onClick={() => select(profile.profile_id)}
          style={{ width: "100%", display: "flex", gap: 10, alignItems: "center", padding: ".65rem", border: 0, borderRadius: 8, color: "var(--ink)", background: profile.profile_id === selectedId ? "var(--accent)" : "transparent", cursor: "pointer", textAlign: "left" }}>
          <img src={profile.icon_data || "/icon.png"} alt="" style={{ width: 38, height: 38, borderRadius: 10, objectFit: "cover", background: "var(--card-2)" }} />
          <span style={{ minWidth: 0 }}><strong style={{ display: "block", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{profile.display_name}</strong><small style={{ opacity: .78 }}>{profile.world_count || 0} Worlds{profile.server_count ? ` · ${profile.server_count} Servers` : ""}</small></span>
        </button>)}
      </aside>

      <section className="panel" style={{ overflow: "hidden" }}>
        <div style={{ minHeight: 170, position: "relative", background: draft.banner_data ? `url(${draft.banner_data}) center/cover` : "linear-gradient(120deg, #211a2e, #4d2b72 55%, #b08a4b)" }}>
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(transparent, rgba(8,8,10,.78))" }} />
          <img src={draft.icon_data || "/icon.png"} alt="" style={{ position: "absolute", left: 24, bottom: -36, width: 92, height: 92, borderRadius: 22, objectFit: "cover", border: "4px solid var(--card)", background: "var(--card-2)" }} />
        </div>
        <div style={{ padding: "3.2rem 1.3rem 1.3rem" }}>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap", marginTop: -43, marginBottom: 20 }}>
            {data.activeId !== selectedId && <button className="btn btn-ghost" onClick={activate}><Icon name="check" /> Use Profile</button>}
            {data.activeId === selectedId && <span className="chip">ACTIVE PROFILE</span>}
            <label className="btn btn-ghost" style={{ cursor: "pointer" }}><Icon name="image" /> Icon<input hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => chooseImage(event, "icon_data", 1024 * 1024)} /></label>
            <label className="btn btn-ghost" style={{ cursor: "pointer" }}><Icon name="image" /> Banner<input hidden type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => chooseImage(event, "banner_data", 3 * 1024 * 1024)} /></label>
          </div>

          <label className="label">Display name</label>
          <input className="input" value={draft.display_name || ""} maxLength={80} onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} />

          <h2 className="heading" style={{ fontSize: "1.05rem", margin: "1.3rem 0 .75rem" }}>Links</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10 }}>
            {[["steam", "Steam profile"], ["epic", "Epic Games"], ["curseforge", "CurseForge"], ["nexus", "Nexus Mods"]].map(([key, label]) => <label key={key}><span className="label">{label}</span><input className="input" type="url" placeholder="https://…" value={draft.links?.[key] || ""} onChange={(event) => setDraft({ ...draft, links: { ...draft.links, [key]: event.target.value } })} /></label>)}
          </div>

          <h2 className="heading" style={{ fontSize: "1.05rem", margin: "1.3rem 0 .75rem" }}>Associated Worlds</h2>
          <div className="panel-inset" style={{ padding: ".8rem", display: "grid", gap: 6 }}>
            {!detail.worlds.length && !detail.servers.length && <span className="subtle">No Worlds belong to this profile yet.</span>}
            {detail.worlds.map((world) => <Link key={world.profile_id} href={`/profiles/${world.profile_id}/player`} style={{ color: "var(--ink)", fontWeight: 750 }}>{world.display_name}</Link>)}
            {detail.servers.map((server) => <Link key={server.world_id} href={`/worlds/${server.world_id}`} style={{ color: "var(--ink)", fontWeight: 750 }}>{server.display_name} <span className="subtle">· dedicated server</span></Link>)}
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: "1.2rem", justifyContent: "space-between" }}>
            <button className="btn btn-ghost" onClick={remove} disabled={data.profiles.length <= 1}><Icon name="trash" /> Delete Profile</button>
            <button className="btn btn-primary" onClick={save} disabled={busy || !draft.display_name?.trim()}><Icon name="check" /> {busy ? "Saving…" : "Save Profile"}</button>
          </div>
        </div>
      </section>
    </div>
  </div>;
}
