// Dragonwilds currently has no reliable in-game broadcast endpoint. Keep the
// shutdown-warning interface as a compatibility boundary for callers, but return
// immediately rather than running legacy game-specific timers or network requests.
const dbm = require("./db");
const DEFAULT_WAITTIME = 20;

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
async function runPreShutdownWarning() {
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
