"use client";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, Icon, toast } from "@/components/ui";

// Resize/compress an image file to a data URL under a target size.
function fileToDataURL(file, maxDim, { format = "image/jpeg", quality = 0.82 } = {}) {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) return reject(new Error("Choose an image file"));
    const img = new Image();
    const reader = new FileReader();
    reader.onload = () => { img.src = reader.result; };
    reader.onerror = reject;
    img.onload = () => {
      let { width, height } = img;
      if (width > maxDim || height > maxDim) {
        const scale = maxDim / Math.max(width, height);
        width = Math.round(width * scale);
        height = Math.round(height * scale);
      }
      const canvas = document.createElement("canvas");
      canvas.width = width; canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, width, height);
      resolve(canvas.toDataURL(format, quality));
    };
    img.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function CustomizeModal({ world, onClose, onDone }) {
  const { t } = useTranslation();
  const downOnBackdrop = useRef(false);
  const [name, setName] = useState(world.display_name || "");
  const [icon, setIcon] = useState(world.icon_data || null);
  const [banner, setBanner] = useState(world.banner_data || null);
  const [accent, setAccent] = useState(world.accent_color || "#c1a56d");
  const [saving, setSaving] = useState(false);

  const pickIcon = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    try { setIcon(await fileToDataURL(f, 256, { format: "image/png" })); } catch { toast(t("customize.readError"), "error"); }
  };
  const pickBanner = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    try { setBanner(await fileToDataURL(f, 1200, { format: "image/jpeg", quality: 0.82 })); } catch { toast(t("customize.readError"), "error"); }
  };

  const save = async () => {
    setSaving(true);
    try {
      await api(`/api/worlds/${world.world_id}/customize`, {
        method: "POST",
        body: { display_name: name, icon_data: icon, banner_data: banner, accent_color: accent },
      });
      toast(t("customize.saved"), "success");
      onDone?.();
    } catch (e) { toast(e.message, "error"); }
    finally { setSaving(false); }
  };

  return (
    <div className="modal-overlay"
      onMouseDown={(e) => { downOnBackdrop.current = e.target === e.currentTarget; }}
      onClick={(e) => { if (e.target === e.currentTarget && downOnBackdrop.current) onClose(); }}>
      <div className="panel animate-floatUp" style={{ width: 560, maxWidth: "94vw", maxHeight: "90vh", overflow: "auto", padding: 0 }}>
        {/* live preview banner */}
        <div style={{ position: "relative", height: 130, background: "var(--bg-2)", overflow: "hidden", borderTopLeftRadius: "inherit", borderTopRightRadius: "inherit" }}>
          {banner && <img src={banner} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to bottom, transparent 40%, var(--card) 100%)" }} />
          <div style={{ position: "absolute", left: 18, bottom: -22, width: 60, height: 60, borderRadius: 14, overflow: "hidden", border: "3px solid var(--card)", background: icon ? "transparent" : accent, display: "grid", placeItems: "center", boxShadow: "0 4px 14px rgba(0,0,0,0.4)" }}>
            {icon ? <img src={icon} alt="" style={{ width: "100%", height: "100%", objectFit: "contain" }} /> : <Icon name="globe" size={28} />}
          </div>
        </div>

        <div style={{ padding: "2rem 1.4rem 1.3rem" }}>
          <label className="label">{t("customize.worldName")}</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} style={{ marginBottom: "1rem" }} />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <label className="label">{t("customize.profileIcon")}</label>
              <div className="subtle" style={{ fontSize: "0.7rem", margin: "-0.2rem 0 0.45rem" }}>Square PNG recommended · transparency preserved</div>
              <div style={{ display: "flex", gap: 8 }}>
                <label className="btn btn-ghost" style={{ cursor: "pointer", flex: 1 }}>
                  <Icon name="upload" size={15} /> {t("customize.upload")}
                  <input type="file" accept="image/*" hidden onChange={pickIcon} />
                </label>
                {icon && <button className="btn btn-ghost" onClick={() => setIcon(null)} title={t("customize.removeTitle")}><Icon name="trash" size={15} /></button>}
              </div>
            </div>
            <div>
              <label className="label">{t("customize.banner")}</label>
              <div className="subtle" style={{ fontSize: "0.7rem", margin: "-0.2rem 0 0.45rem" }}>Wide image recommended · 1200 px max</div>
              <div style={{ display: "flex", gap: 8 }}>
                <label className="btn btn-ghost" style={{ cursor: "pointer", flex: 1 }}>
                  <Icon name="upload" size={15} /> {t("customize.upload")}
                  <input type="file" accept="image/*" hidden onChange={pickBanner} />
                </label>
                {banner && <button className="btn btn-ghost" onClick={() => setBanner(null)} title={t("customize.removeTitle")}><Icon name="trash" size={15} /></button>}
              </div>
            </div>
          </div>

          <label className="label">{t("customize.accentColor")} <span className="subtle" style={{ fontWeight: 600, textTransform: "none", letterSpacing: 0 }}>{t("customize.accentColorHint")}</span></label>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: "1.4rem" }}>
            <input type="color" value={accent} onChange={(e) => setAccent(e.target.value)} style={{ width: 48, height: 38, border: "1px solid var(--line)", borderRadius: 8, background: "none", cursor: "pointer" }} />
            <code style={{ fontWeight: 700 }}>{accent}</code>
            {["#c1a56d", "#6f4bd8", "#bd5f36", "#3f8b73"].map((color) => (
              <button key={color} type="button" aria-label={`Use ${color}`} onClick={() => setAccent(color)} style={{ width: 24, height: 24, padding: 0, borderRadius: 999, border: accent === color ? "2px solid var(--ink)" : "1px solid var(--line-strong)", background: color, cursor: "pointer" }} />
            ))}
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.6rem", flexWrap: "wrap" }}>
            <button className="btn btn-ghost" type="button" onClick={() => { setIcon(null); setBanner(null); setAccent("#c1a56d"); }}>Reset visuals</button>
            <div style={{ display: "flex", gap: "0.6rem" }}>
            <button className="btn btn-ghost" onClick={onClose}>{t("customize.cancel")}</button>
            <button className="btn btn-primary" onClick={save} disabled={saving}><Icon name="download" /> {saving ? t("customize.saving") : t("customize.save")}</button>
            </div>
          </div>
          <p className="subtle" style={{ fontSize: "0.7rem", fontWeight: 600, marginTop: 10, marginBottom: 0 }}>
            {t("customize.footer")}
          </p>
        </div>
      </div>
    </div>
  );
}
