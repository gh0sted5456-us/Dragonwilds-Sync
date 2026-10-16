const fs = require("fs");
const path = require("path");

function createStartupGate({ onEnter, onStatus = () => {} }) {
  let state = { ready: false, entered: false, message: "Starting RSDW Sync…", error: "", revision: 0 };
  const update = (patch) => { state = { ...state, ...patch, revision: state.revision + 1 }; onStatus({ ...state }); };
  return {
    snapshot: () => ({ ...state }),
    reset: (ready = false) => update({ ready, entered: false, error: "", message: ready ? "Ready when you are" : "Starting RSDW Sync…" }),
    progress: (message) => update({ message, error: "" }),
    ready: () => update({ ready: true, message: "Ready when you are", error: "" }),
    fail: (error) => update({ ready: false, entered: false, error: String(error), message: "Unable to start — see launcher.log" }),
    async enter() {
      if (!state.ready || state.entered) return false;
      update({ entered: true, message: "Opening your workspace…", error: "" });
      try {
        if (await onEnter() === false) throw new Error("The interface could not open. Try Enter again.");
        return true;
      } catch (error) {
        update({ entered: false, message: "Try Enter again", error: error.message || String(error) });
        return false;
      }
    },
  };
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function imageData(publicDirectory, relative, mime) {
  try { return `data:${mime};base64,${fs.readFileSync(path.join(publicDirectory, relative)).toString("base64")}`; }
  catch { return ""; }
}

function startupHtml(publicDirectory, state = {}) {
  const dragonwilds = imageData(publicDirectory, "rsdw/dragonwilds-wordmark.png", "image/png");
  const rsdw = imageData(publicDirectory, "rsdw/app-icon.webp", "image/webp");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>RSDW Sync</title><style>
  *{box-sizing:border-box}body{margin:0;color:#f1f3fb;background:#11151d;font:15px system-ui,"Segoe UI",sans-serif}
  .caption{height:46px;padding:0 150px 0 18px;display:flex;align-items:center;border-bottom:1px solid #303b4e;background:#11151d;font-size:13px;font-weight:700;-webkit-app-region:drag}
  main{height:calc(100vh - 46px);min-height:360px;display:grid;grid-template-rows:minmax(180px,1fr) auto;justify-items:center;padding:24px 24px 40px;background:radial-gradient(circle at 50% 44%,#252435 0%,#11151d 58%)}
  .logos{position:relative;align-self:center;width:min(72vw,620px);height:min(48vh,350px);display:grid;place-items:center}
  .logos img{position:absolute;max-width:100%;max-height:100%;object-fit:contain}
  .dragonwilds{width:620px;opacity:0;animation:dragonwilds 2.8s ease-in-out both}
  .rsdw{width:300px;opacity:1;animation:rsdw 2.8s ease-in-out both}
  .fallback{font-size:32px;font-weight:800;color:#c1a56d}
  .entry{width:min(100%,720px);display:grid;justify-items:center;gap:12px;text-align:center}
  .label{color:#aaa397;font-size:11px;font-weight:800;letter-spacing:.2em}
  button{min-width:158px;border:1px solid #c1a56d;border-radius:999px;padding:12px 28px;background:#24282c;color:#f3efe7;font:800 14px system-ui;letter-spacing:.12em;text-transform:uppercase;cursor:pointer}
  button:disabled{cursor:wait;color:#c7c1b7;border-color:#766746}button:not(:disabled):hover,button:focus-visible{background:#c1a56d;color:#1d1a14;outline:2px solid #d0b47a;outline-offset:3px}
  #status{margin:0;color:#aaa397;font-size:13px}#error{margin:0;color:#e3a66f;font-size:13px;overflow-wrap:anywhere}small{color:#aaa397;font-size:12px}
  @keyframes dragonwilds{0%,26%{opacity:1;transform:scale(1)}80%,100%{opacity:0;transform:scale(1.025)}}
  @keyframes rsdw{0%,26%{opacity:0;transform:scale(.97)}80%,100%{opacity:1;transform:scale(1)}}
  @media(prefers-reduced-motion:reduce){.dragonwilds,.rsdw{animation:none}.dragonwilds{display:none}}
  </style></head><body><header class="caption">RuneScape: Dragonwilds — Sync Launcher</header><main>
  <div class="logos" aria-hidden="true">${dragonwilds ? `<img class="dragonwilds" src="${dragonwilds}" alt="">` : ""}${rsdw ? `<img class="rsdw" src="${rsdw}" alt="">` : '<span class="fallback">RSDW Sync</span>'}</div>
  <div class="entry"><span class="label">DRAGONWILDS PROFILES</span><button id="enter" ${state.ready && !state.entered ? "" : "disabled"}>Enter</button><p id="status" role="status">${escapeHtml(state.message || "Starting RSDW Sync…")}</p><p id="error" role="alert">${escapeHtml(state.error)}</p><small>Press Enter when ready</small></div>
  </main><script>
  (() => {
    const button = document.getElementById('enter');
    const status = document.getElementById('status');
    const error = document.getElementById('error');
    let ready = false, entering = false, revision = -1;
    const apply = (state) => {
      if (!state || state.revision < revision) return;
      revision = state.revision;
      ready = !!state.ready; entering = !!state.entered;
      button.disabled = !ready || entering;
      status.textContent = state.message || (ready ? 'Ready when you are' : 'Starting RSDW Sync…');
      error.textContent = state.error || '';
    };
    const enter = async () => {
      if (!ready || entering || !window.desktop?.enterStartup) return;
      entering = true; button.disabled = true; status.textContent = 'Opening your workspace…';
      try { await window.desktop.enterStartup(); }
      catch (failure) { entering = false; button.disabled = !ready; error.textContent = failure.message || 'Unable to open the workspace'; }
    };
    button.addEventListener('click', enter);
    window.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.repeat) { event.preventDefault(); enter(); } });
    const unsubscribe = window.desktop?.onStartupStatus?.(apply);
    window.addEventListener('unload', () => unsubscribe?.(), {once:true});
    window.desktop?.getStartupState?.().then(apply).catch(() => { error.textContent = 'Startup status unavailable. Restart RSDW Sync.'; });
  })();
  </script></body></html>`;
}

module.exports = { createStartupGate, startupHtml };
