// lib/scheduler.js  (spec §7 scheduler, §8 update all)
const dbm = require("./db");
const steam = require("./steamcmd");
const sup = require("./supervisor");
const jobs = require("./jobs");
const warn = require("./warn");
const appver = require("./appversion");
const { createBackup } = require("./backups");
const { notify } = require("./notify");
const syncedMods = require("./mod-lanes");
const forks = require("./server-forks");

const g = globalThis;
if (!g.__APP_SCHED) g.__APP_SCHED = { timer: null, updating: new Set(), backupSkipped: new Set(), autoUpdating: false };
const ST = g.__APP_SCHED;
if (!ST.backupSkipped) ST.backupSkipped = new Set();

const SUPPORTED_JOBS = new Set(["restart", "stop", "backup", "update"]);

function ensureScheduler() {
  // Schedule jobs (backup/restart/update) are coarse — a once-a-minute check is fine.
  if (!ST.timer) {
    ST.timer = setInterval(tick, 60 * 1000);
    tick();
  }
}

function due(sched, now) {
  if (!sched.enabled || !SUPPORTED_JOBS.has(sched.job_type)) return false;
  const last = sched.last_run || 0;
  if (sched.mode === "interval" && sched.interval_hours) {
    return now - last >= sched.interval_hours * 3600 * 1000;
  }
  if (sched.mode === "minutes" && sched.interval_minutes) {
    return now - last >= sched.interval_minutes * 60 * 1000;
  }
  if (sched.mode === "daily" && sched.time_of_day) {
    const [h, m] = sched.time_of_day.split(":").map(Number);
    const d = new Date(now);
    const target = new Date(d); target.setHours(h, m, 0, 0);
    // fire within the minute window, and not already run today
    const ranToday = last && new Date(last).toDateString() === d.toDateString();
    return !ranToday && d >= target && d - target < 90 * 1000;
  }
  return false;
}

async function tick() {
  const now = Date.now();
  await maybeAutoCheckUpdates(now);
  // Refresh the app-version (GitHub) check on its own cadence — the module only
  // hits GitHub when its cache is stale (30 min), so calling every tick is cheap.
  appver.refreshIfStale(now).catch(() => {});
  // Apply Steam updates to opted-in servers. Fire-and-forget: a run can block for
  // minutes (5-minute player warning + SteamCMD), and it must not stall the
  // schedule loop below or the next tick. Its own ST.autoUpdating guard stops
  // overlapping ticks from starting a second sweep.
  runAutoUpdates().catch(() => {});
  for (const s of dbm.listSchedules()) {
    if (!due(s, now)) continue;
    // "Skip the next run": consume the one-shot flag before doing any work. Rebase the
    // timer (stamp last_run) so this occurrence is truly skipped rather than staying
    // due, then clear the flag so the schedule resumes on its normal cadence. Checked
    // ahead of the backup-when-stopped skip below so an admin's cancel always wins.
    if (s.skip_next) {
      dbm.updateScheduleRun(s.id, now);
      dbm.setScheduleSkipNext(s.id, false);
      ST.backupSkipped.delete(s.id);
      dbm.logEvent(s.world_id, "scheduler", `Skipped scheduled ${s.job_type} — cancelled by admin`);
      continue;
    }
    // A stopped world's save data can't change, so a scheduled backup of one is a
    // byte-identical duplicate — and since rotation keeps a fixed number of backups,
    // a few hours of those would quietly evict every real backup. Skip without
    // stamping last_run, so the backup that was owed runs as soon as the server is
    // back. Manual backups still work while stopped, on purpose.
    if (s.job_type === "backup" && !sup.isAlive(s.world_id)) {
      // The job stays due every tick while it's stopped, so log the skip once per
      // stretch rather than once a minute.
      if (!ST.backupSkipped.has(s.id)) {
        ST.backupSkipped.add(s.id);
        dbm.logEvent(s.world_id, "scheduler", "Skipped scheduled backup — the server isn't running");
      }
      continue;
    }
    ST.backupSkipped.delete(s.id);
    dbm.updateScheduleRun(s.id, now);
      try {
        if (s.job_type === "backup") await createBackup(s.world_id, "scheduled");
        else if (s.job_type === "restart") await scheduledRestart(s.world_id);
        else if (s.job_type === "stop") await scheduledStop(s.world_id);
        else if (s.job_type === "update") {
          // Before killing the server, verify an update is actually available.
          // Prefer the world's cached latest_known_build_id (refreshed by maybeAutoCheckUpdates);
          // if it's missing, run a fresh check.
          const w = dbm.getWorld(s.world_id);
          let latest = w?.latest_known_build_id;
          if (!latest) {
            try {
              const res = await checkUpdates();
              latest = res.latest;
            } catch (e) {
              dbm.logEvent(s.world_id, "scheduler", `Skipped scheduled update — failed to check latest build: ${e.message}`);
              continue;
            }
          }
          if (!latest) {
            dbm.logEvent(s.world_id, "scheduler", "Skipped scheduled update — couldn't determine latest build");
            continue;
          }
          if (w && w.build_id && w.build_id === latest) {
            dbm.logEvent(s.world_id, "scheduler", "Skipped scheduled update — already on latest build");
            continue;
          }
          // Update is needed — proceed to updateWorld which will warn/stop/start as required.
          await updateWorld(s.world_id);
        }
        dbm.logEvent(s.world_id, "scheduler", `Ran ${s.job_type} job`);
      } catch (e) {
        dbm.logEvent(s.world_id, "scheduler", `Job ${s.job_type} failed: ${e.message}`);
      }
  }
}

async function scheduledRestart(worldId) {
  const w = dbm.getWorld(worldId);
  if (!w) return;
  await createBackup(worldId, "pre-restart-safety").catch(() => {});
  await notify(worldId, "restart", `Scheduled restart of ${w.display_name}`, {});
  // Warn players first (if configured), then restart with the native red
  // countdown for the final minute.
  const { finalWaittime } = await warn.runPreShutdownWarning(worldId, sup.isAlive);
  await sup.restartWorld(worldId, { waittime: finalWaittime });
}

// A scheduled shutdown — the maintenance case: warn players, save, and take the
// world down (it stays down, unlike restart). A world that's already stopped is a
// no-op: nothing to save, and warning an empty server would be noise. Mirrors
// scheduledRestart's safety backup + player warning so a scheduled stop is as gentle
// as a scheduled restart.
async function scheduledStop(worldId) {
  const w = dbm.getWorld(worldId);
  if (!w) return;
  if (!sup.isAlive(worldId)) return; // already down — nothing to do
  await createBackup(worldId, "pre-stop-safety").catch(() => {});
  await notify(worldId, "stop", `Scheduled stop of ${w.display_name}`, {});
  // Warn players first (if configured), then stop with the native red countdown
  // for the final minute.
  const { finalWaittime } = await warn.runPreShutdownWarning(worldId, sup.isAlive);
  await sup.stopWorld(worldId, { graceful: true, waittime: finalWaittime });
}

// ---- Update All / per-world update (spec §8) ----
// The UI only offers an Update button once we know a newer build exists, which means
// latest_known_build_id has to be populated without the user pressing anything. Poll
// Steam on the minute tick, but no more often than the configured interval — a failed
// call (offline) just leaves the state unknown until the next window rather than
// nagging. One lightweight api.steamcmd.net call covers every world (the build id is
// global); each world's installed build is compared against it in checkUpdates().
const LAST_CHECK_SETTING = "lastUpdateCheck";
const CHECK_INTERVAL_SETTING = "updateCheckIntervalMinutes";
const DEFAULT_CHECK_MIN = 30;
const MIN_CHECK_MIN = 5; // floor so a bad setting can't hammer Steam

function updateCheckMs() {
  const n = parseInt(dbm.getSetting(CHECK_INTERVAL_SETTING, DEFAULT_CHECK_MIN), 10);
  const minutes = Number.isFinite(n) && n > 0 ? Math.max(MIN_CHECK_MIN, n) : DEFAULT_CHECK_MIN;
  return minutes * 60 * 1000;
}

async function maybeAutoCheckUpdates(now = Date.now()) {
  const last = Number(dbm.getSetting(LAST_CHECK_SETTING, 0)) || 0;
  if (now - last < updateCheckMs()) return;
  // Stamp before the call, not after: a Steam outage would otherwise retry every
  // minute for as long as it lasts.
  dbm.setSetting(LAST_CHECK_SETTING, now);
  try { await checkUpdates(); } catch { /* offline — try again next window */ }
}

// Fixed alert cadence for auto-updates: warn players once a minute for five minutes
// before the server goes down. The final minute uses the dedicated server's native
// shutdown countdown (see lib/warn.js), so players see notices at 5/4/3/2 minutes plus the
// native banner for the last minute.
const AUTO_UPDATE_WARN = { leadMinutes: 5, intervalMinutes: 1 };

// When the global setting or a profile's "auto-update" toggle is enabled, update
// any matching server whose installed build is behind the latest public build. Off
// by default; periodic checks still keep the "update available" chips accurate. Gated by
// ST.autoUpdating so overlapping ticks can't start two sweeps, and per-world by
// ST.updating inside updateWorld so it never collides with a manual/scheduled update.
async function runAutoUpdates() {
  const globalEnabled = dbm.getSetting("autoUpdateEnabled", false) === true;
  if (!globalEnabled && !dbm.listWorlds().some((world) => !!world.auto_update)) return;
  if (ST.autoUpdating) return;
  ST.autoUpdating = true;
  try {
    const handledInstalls = new Set();
    for (const w of dbm.listWorlds()) {
      if (!globalEnabled && !w.auto_update) continue;
      const installKey = String(w.install_dir || "").toLowerCase();
      if (handledInstalls.has(installKey)) continue;
      if (!w.build_id || !w.latest_known_build_id) continue; // never checked yet
      if (w.build_id === w.latest_known_build_id) continue;  // already current
      if (ST.updating.has(w.world_id)) continue;             // update already in flight
      handledInstalls.add(installKey);
      dbm.logEvent(w.world_id, "update", `Auto-update: new build ${w.latest_known_build_id} detected — warning players for 5 minutes, then updating`);
      try { await notify(w.world_id, "update", `${w.display_name}: a new Dragonwilds server build is out — auto-updating in 5 minutes`); } catch {}
      try {
        await updateWorld(w.world_id, () => {}, null, { warn: AUTO_UPDATE_WARN });
      } catch (e) {
        dbm.logEvent(w.world_id, "update", `Auto-update failed: ${e.message}`);
      }
    }
  } finally {
    ST.autoUpdating = false;
  }
}

async function checkUpdates() {
  const latest = await steam.fetchLatestBuildId();
  if (!latest) return { latest: null, worlds: [] };
  dbm.setSetting(LAST_CHECK_SETTING, Date.now()); // a manual check also satisfies the auto one
  const flagged = [];
  for (const w of dbm.listWorlds()) {
    dbm.updateWorld(w.world_id, { latest_known_build_id: latest });
    if (w.build_id && w.build_id !== latest) {
      flagged.push(w.world_id);
      const noticeKey = `updateNotice:server:${w.world_id}`;
      if (dbm.getSetting(noticeKey, null) !== latest) {
        dbm.setSetting(noticeKey, latest);
        dbm.logEvent(w.world_id, "update", `Dragonwilds dedicated-server build ${latest} is available (installed ${w.build_id})`);
        try { await notify(w.world_id, "update", `${w.display_name}: Dragonwilds server build ${latest} is available`, { installed: w.build_id, latest }); } catch {}
      }
    }
  }
  return { latest, worlds: flagged };
}

async function updateWorld(worldId, onLog = () => {}, jobId = null, opts = {}) {
  const emit = (l) => { onLog(l); if (jobId) jobs.logJob(jobId, l); };
  const phase = (p, m) => { if (jobId) jobs.setPhase(jobId, p, m); };
  if (jobs.listJobs().some((job) => job.id !== jobId && job.status === "running" && job.phase === "copy")) {
    const error = "Wait for the Server profile migration or file refresh to finish before updating.";
    emit(error);
    if (jobId) jobs.finishJob(jobId, false, { worldId, error });
    return { ok: false, error };
  }
  if (ST.updating.has(worldId)) {
    if (jobId) jobs.finishJob(jobId, false, { worldId, error: "Already updating" });
    return { skipped: "already updating" };
  }
  ST.updating.add(worldId);
  const w = dbm.getWorld(worldId);
  try {
    const prevBuild = w?.build_id;
    const wasRunning = sup.isAlive(worldId);
    if (wasRunning) {
      // Give players advance notice before we take the server down to update. A
      // caller can force the warning cadence (auto-update passes a fixed 5-min /
      // 1-min sequence); otherwise the world's own warn settings apply.
      const { finalWaittime } = await warn.runPreShutdownWarning(worldId, sup.isAlive, opts.warn || null);
      phase("finalizing", "Saving and shutting down…");
      emit("Saving and shutting down...");
      await sup.stopWorld(worldId, { graceful: true, waittime: finalWaittime });
    }
    dbm.updateWorld(worldId, { status: "updating" });
    phase("backup", "Creating safety backup…");
    emit("Creating safety backup...");
    await createBackup(worldId, "pre-update-safety").catch(() => {});
    // Worlds adopted from an existing install never went through provisioning, so
    // the shared SteamCMD may not be installed yet — updating would fail. Make sure
    // it's present before we try to run it.
    if (!steam.steamcmdInstalled()) {
      phase("steamcmd", "Installing SteamCMD…");
      emit("RSDW: SteamCMD not found — installing it first...");
      await steam.ensureSteamCmd((line) => emit(`SteamCMD: ${line}`));
    }
    const coreDir = dbm.getSetting("applicationSetup:serverDir", null);
    const managed = coreDir && forks.managedFork(w, coreDir);
    phase("steamcmd", managed ? "Updating shared Server Core with SteamCMD…" : "Running SteamCMD update…");
    emit(managed ? "RSDW: updating the shared Server Core first" : "Running SteamCMD update...");
    let res;
    let bid;
    if (managed) {
      res = await forks.updateCore(coreDir, w.platform, { onLog: emit });
      phase("copy", "Refreshing stopped Server profiles from Core…");
      if (jobId) jobs.setProgress(jobId, 0, "RSDW: staging profile core files…");
      const results = await forks.refreshStoppedProfiles(coreDir, {
        onLog: emit,
        onProgress: ({ worldName, completed, total, file }) => {
          if (jobId) jobs.setProgress(jobId, Math.round(100 * completed / Math.max(1, total)), `RSDW: ${worldName} · ${completed}/${total} files · ${file}`);
        },
      });
      const target = results.find((item) => item.worldId === worldId);
      if (target?.error || target?.pending || !target) throw new Error(target?.error || "This Server profile could not be refreshed from Core");
      bid = target.buildId || res.buildId;
    } else {
      res = await steam.installOrUpdate(w.install_dir, (line) => emit(`SteamCMD: ${line}`), w.platform);
      if (!res.ok) throw new Error(`SteamCMD failed (code ${res.code})${res.detail ? `: ${res.detail}` : ""}`);
      bid = res.buildId || steam.readInstalledBuildId(w.install_dir);
    }
    if (bid) {
      for (const profile of dbm.listWorlds()) {
        if (String(profile.install_dir).toLowerCase() === String(w.install_dir).toLowerCase()) {
          dbm.updateWorld(profile.world_id, { build_id: bid, latest_known_build_id: bid });
        }
      }
    }
    dbm.updateWorld(worldId, { status: "stopped" });
    try { syncedMods.reapplySelections(worldId); emit("Reapplied managed mod selection."); }
    catch (e) { emit(`Retained mod warning: ${e.message}`); dbm.logEvent(worldId, "mod", `Could not reapply retained mods after update: ${e.message}`); }
    if (wasRunning) { phase("finalizing", "Relaunching…"); emit("Relaunching..."); await sup.startWorld(worldId); }
    const updated = bid && (!prevBuild || String(bid) !== String(prevBuild));
    if (updated) {
      dbm.logEvent(worldId, "update", `Updated to build ${bid}`);
      await notify(worldId, "update", `${w.display_name} updated to build ${bid}`, { build: bid, updated: true });
    } else {
      dbm.logEvent(worldId, "update", `No update available (build ${bid || "?"}) — server restarted`);
      await notify(worldId, "update", `${w.display_name}: no update to apply — server restarted (build ${bid || "?"})`, { build: bid || "?", updated: false });
    }
    if (jobId) jobs.finishJob(jobId, true, { worldId });
    return { ok: true, build: bid };
  } catch (e) {
    dbm.updateWorld(worldId, { status: "stopped" });
    if (jobId) jobs.finishJob(jobId, false, { worldId, error: e.message });
    return { ok: false, error: e.message };
  } finally {
    ST.updating.delete(worldId);
  }
}

async function updateAll(onLog = () => {}) {
  const { worlds } = await checkUpdates();
  const results = [];
  for (const id of worlds) {
    const w = dbm.getWorld(id);
    const jobId = jobs.createJob({ type: "update", worldId: id, worldName: w?.display_name || "" });
    onLog(`Updating world ${id}...`);
    results.push({ worldId: id, ...(await updateWorld(id, onLog, jobId)) });
  }
  return results;
}

// Kick off a single world update as a tracked background job; returns the jobId
// immediately so the caller (HTTP route) doesn't block on the whole SteamCMD run.
function startUpdateJob(worldId) {
  const w = dbm.getWorld(worldId);
  if (!w) return null;
  const jobId = jobs.createJob({ type: "update", worldId, worldName: w.display_name || "" });
  // fire and forget — progress is polled via /api/jobs
  updateWorld(worldId, () => {}, jobId);
  return jobId;
}

module.exports = { ensureScheduler, tick, checkUpdates, maybeAutoCheckUpdates, runAutoUpdates, updateWorld, updateAll, startUpdateJob };
