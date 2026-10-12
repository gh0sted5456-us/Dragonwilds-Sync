"use client";
// The Remote Access entry point: type the 5-digit code shared by the server owner. On
// success the server sets an HttpOnly session cookie and we route into the granted view.
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { Icon } from "@/components/ui";

export default function RemoteEntry() {
  const { t } = useTranslation();
  const router = useRouter();
  const [digits, setDigits] = useState(["", "", "", "", ""]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lockedFor, setLockedFor] = useState(0);
  const inputs = useRef([]);

  // Already signed in? Skip straight to the granted view.
  useEffect(() => {
    fetch("/api/remote/session").then((r) => r.json()).then((r) => {
      if (r && r.ok && !r.revoked && r.scope) go(r);
    }).catch(() => {});
  }, []);

  // Lockout countdown.
  useEffect(() => {
    if (lockedFor <= 0) return;
    const id = setInterval(() => setLockedFor((n) => Math.max(0, n - 1)), 1000);
    return () => clearInterval(id);
  }, [lockedFor]);

  const go = (info) => {
    if (info.scope === "world" && info.worldId) router.push(`/remote/worlds/${info.worldId}`);
    else router.push("/remote/worlds");
  };

  const setDigit = (i, v) => {
    const d = v.replace(/\D/g, "").slice(-1);
    setDigits((prev) => { const n = [...prev]; n[i] = d; return n; });
    if (d && i < 4) inputs.current[i + 1]?.focus();
  };
  const onKey = (i, e) => {
    if (e.key === "Backspace" && !digits[i] && i > 0) inputs.current[i - 1]?.focus();
  };
  const onPaste = (e) => {
    const txt = (e.clipboardData.getData("text") || "").replace(/\D/g, "").slice(0, 5);
    if (txt) { e.preventDefault(); setDigits(txt.padEnd(5, "").split("").slice(0, 5).map((c) => c || "")); inputs.current[Math.min(txt.length, 4)]?.focus(); }
  };

  const submit = async () => {
    const code = digits.join("");
    if (code.length !== 5) { setError(t("remote.enterFive")); return; }
    setBusy(true); setError("");
    try {
      const res = await fetch("/api/remote/session", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) { go(data); return; }
      if (res.status === 429 || data.lockedFor) { setLockedFor(data.lockedFor || 60); setError(t("remote.lockedOut")); }
      else setError(data.error || t("remote.invalidCode"));
      setDigits(["", "", "", "", ""]);
      inputs.current[0]?.focus();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const locked = lockedFor > 0;

  return (
    <div style={{ maxWidth: 420, margin: "6vh auto 0", textAlign: "center" }}>
      <div style={{ width: 56, height: 56, borderRadius: 16, background: "var(--card-2)", display: "grid", placeItems: "center", margin: "0 auto 1rem" }}>
        <Icon name="key" size={26} />
      </div>
      <h1 className="heading" style={{ fontSize: "1.5rem", margin: 0 }}>{t("remote.entryTitle")}</h1>
      <p className="subtle" style={{ fontWeight: 600, fontSize: "0.86rem", marginTop: 6 }}>{t("remote.entryHelp")}</p>

      <div onPaste={onPaste} style={{ display: "flex", gap: "0.5rem", justifyContent: "center", margin: "1.6rem 0 0.6rem" }}>
        {digits.map((d, i) => (
          <input key={i} ref={(el) => (inputs.current[i] = el)}
            value={d} inputMode="numeric" maxLength={1} disabled={busy || locked}
            onChange={(e) => setDigit(i, e.target.value)}
            onKeyDown={(e) => { onKey(i, e); if (e.key === "Enter") submit(); }}
            autoFocus={i === 0}
            style={{
              width: 52, height: 62, textAlign: "center", fontSize: "1.8rem", fontWeight: 800,
              borderRadius: 12, border: "1px solid var(--line-strong)", background: "var(--card)", color: "var(--ink)",
            }} />
        ))}
      </div>

      {error && <div style={{ color: "var(--red)", fontWeight: 700, fontSize: "0.82rem", marginTop: 8 }}>
        {error}{locked ? ` (${lockedFor}s)` : ""}
      </div>}

      <button className="btn btn-primary" onClick={submit} disabled={busy || locked}
        style={{ marginTop: "1.2rem", width: "100%", justifyContent: "center", padding: "0.7rem" }}>
        {busy ? t("remote.connecting") : t("remote.connect")}
      </button>
    </div>
  );
}
