// lib/warn.js  (v1.5.0 pre-shutdown warning countdown)
// Broadcasts timed notices to players before a restart/update, then hands the
// final stretch off to Palworld's native red shutdown countdown.
//
// The only built-in "big red" banner is the shutdown countdown triggered by the
// `shutdown` command's waittime. So we send our custom messages at each checkpoint —
// on every player's screen via the PSMBroadcast mod when it's installed, otherwise as
// REST `announce` broadcasts — then stop with a native countdown for the last minute,
// and that final minute is the red banner players can't miss.
const dbm = require("./db");
const rest = require("./restclient");

// Seconds of the very end handled by Palworld's native red shutdown countdown.
const FINAL = 60;
// Waittime used when warnings are off — matches the app's previous behaviour.
const DEFAULT_WAITTIME = 20;

const sleep = (ms) => new Promise((r) => setTimeout(r, Math.max(0, ms)));

// Deliver one warning notice: on every player's screen via the PSMBroadcast mod when
// it's installed, otherwise Palworld's REST announce (chat feed). Supervisor is
// required lazily to avoid a require cycle (supervisor reaches warn via the scheduler).
async function deliverNotice(w, message) {
  const sup = require("./supervisor");
  if (w && sup.broadcastModInstalled(w.install_dir)) {
    sup.enqueueBroadcast(w.install_dir, message);
  } else {
    await rest.announce(w, message);
  }
}

// Fill {minutes} / {seconds} in the user's message template.
function fmt(tpl, totalSeconds) {
  const minutes = Math.max(1, Math.round(totalSeconds / 60));
  return String(tpl || "The server will restart in {minutes} minute(s).")
    .split("{minutes}").join(String(minutes))
    .split("{seconds}").join(String(totalSeconds));
}

// Warnings are unsupported for RuneScape: Dragonwilds because it lacks any
// reliable in-game broadcast or REST announce endpoint. Always return false so
// callers skip the countdown/delivery path and proceed immediately.
function shouldWarn() { return false; }

// Run the warning countdown, blocking for (lead - final) so the caller can then
// stop the world with the returned finalWaittime for the native red countdown.
// No-ops (returns the default waittime immediately) when warnings don't apply.
//
// `override` = { leadMinutes, intervalMinutes, message } lets a caller impose a
// fixed cadence instead of the world's own warn settings — auto-update uses it to
// alert every minute for 5 minutes no matter how the world is configured.
async function runPreShutdownWarning(worldId, isRunning, override = null) {
  // Warnings are disabled; return the default waittime so callers proceed
  // immediately to the native shutdown handoff without delivering notices.
  return { finalWaittime: DEFAULT_WAITTIME };
}

// Warn players, then restart. Meant to be run in the background (it can block for
// the full lead time). Requires supervisor lazily to avoid a require cycle.
async function warnedRestart(worldId) {
  const sup = require("./supervisor");
  try {
    const { finalWaittime } = await runPreShutdownWarning(worldId, sup.isAlive);
    await sup.restartWorld(worldId, { waittime: finalWaittime });
  } catch (e) {
    dbm.logEvent(worldId, "warn", `Warned restart failed: ${e.message}`);
  }
}

module.exports = { runPreShutdownWarning, warnedRestart, shouldWarn };
