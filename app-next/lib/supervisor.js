// lib/supervisor.js  (spec §4 lifecycle, §5 log capture, §9 crash guardian)
// Holds live child processes in memory (singleton across the Next server runtime).
const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn, spawnSync } = require("child_process");
const kill = require("tree-kill");
const { P } = require("./paths");
const dbm = require("./db");
const rest = require("./restclient");
const ini = require("./ini");
const notify = require("./notify");
const ports = require("./ports");
const RING = 500; // lines kept in memory per world

// Global singleton so hot-reload / multiple route handlers share state.
const g = globalThis;
if (!g.__APP_SUP) {
  g.__APP_SUP = {
    procs: new Map(),          // world_id -> child process
    logs: new Map(),           // world_id -> string[] ring buffer
    listeners: new Map(),      // world_id -> Set(fn) for live log streaming
    guardTimer: null,
    owned: new Set(),           // world_ids launched by this app process
    restartAttempts: new Map(), // world_id -> crash-restart timestamps
    operations: new Map(),      // world_id -> serialized lifecycle promise
    operationKinds: new Map(),  // world_id -> start | stop | restart
    desired: new Map(),         // world_id -> "running" | "stopped"
  };
}
const S = g.__APP_SUP;
// Hot reload can retain an older singleton shape.
if (!S.owned) S.owned = new Set();
if (!S.restartAttempts) S.restartAttempts = new Map();
if (!S.operations) S.operations = new Map();
if (!S.operationKinds) S.operationKinds = new Map();
if (!S.desired) S.desired = new Map();

function serializeLifecycle(worldId, kind, task) {
  if (S.operationKinds.get(worldId) === kind && S.operations.has(worldId)) return S.operations.get(worldId);
  const previous = S.operations.get(worldId) || Promise.resolve();
  const operation = previous.catch(() => {}).then(task);
  S.operations.set(worldId, operation);
  S.operationKinds.set(worldId, kind);
  const cleanup = () => {
    if (S.operations.get(worldId) !== operation) return;
    S.operations.delete(worldId);
    S.operationKinds.delete(worldId);
  };
  operation.then(cleanup, cleanup);
  return operation;
}

function hostPlatform() {
  return os.platform() === "win32" ? "windows" : "linux";
}

// The Windows dedicated server ships three binaries:
//   <launcher>.exe                    — a small launcher (GUI subsystem)
//   <server>-Win64-Shipping.exe     — the server itself, GUI subsystem
//   <server>-Win64-Shipping-Cmd.exe — the same server built as a console program
//
// Going through the launcher is what pops the black command window: the launcher starts
// the *-Cmd* build, and a console program with no console of its own gets a real window
// from Windows. No spawn flag of ours can stop it — our flags apply to the launcher, and
// CREATE_NO_WINDOW is documented to be ignored for GUI programs, which the launcher is.
//
// Starting the GUI server directly sidesteps the whole thing: same server, one process,
// no console anywhere in the tree, so no window can appear. Verified against a real
// install — via the launcher: the *-Cmd.exe process plus a visible window;
// direct: a single process, no window, REST API up either way.
//
// This applies to the Windows build whether it's running natively or under Wine — the
// launcher indirection isn't host-specific, it's a property of the Windows binaries.
function shippingBinary(installDir) {
  // Prefer a direct Windows server binary if present. Name depends on the
  // Dragonwilds packaging; check the common direct executable name.
  return path.join(installDir, "RSDragonwildsServer.exe");
}
// Hiding the console window is the default, and stays the default on a fresh install,
// a reinstall, or an upgrade: nothing seeds this key, so it is simply absent until
// someone turns it off, and only an explicit false counts as off. A null value — an
// older build, a half-written row — means "never chosen", which is on.
function hideConsoleEnabled() {
  return dbm.getSetting("hideConsoleWindow", true) !== false;
}

function serverBinary(world, { hidden = hideConsoleEnabled() } = {}) {
  const plat = world.platform || hostPlatform();
  if (plat === "linux") return path.join(world.install_dir, "RSDragonwildsServer.sh");
  // plat === "windows" — prefer the direct server binary name.
  return path.join(world.install_dir, "RSDragonwildsServer.exe");
}

// True when this world needs Wine to run here: it was provisioned for Windows,
// but this host isn't Windows. (The reverse — a Linux-provisioned world on a
// Windows host — has no equivalent and stays a hard error.)
function needsWine(world) {
  return world.platform === "windows" && hostPlatform() === "linux";
}
function parseWineFlags(world) {
  return (world.wine_launch_flags || "").trim().split(/\s+/).filter(Boolean);
}
function defaultWinePrefix(world) {
  return world.wine_prefix && world.wine_prefix.trim()
  ? world.wine_prefix.trim()
  : P.worldWinePrefix(world.world_id);
}
function checkWineAvailable(wineBin) {
  const r = spawnSync(wineBin, ["--help"], { timeout: 5000 });
  return !r.error;
}
// Custom env vars are stored as a JSON object; user text input is parsed into
// this shape before saving (see AdminPanel.jsx).
function parseCustomEnv(world) {
  try {
    const obj = JSON.parse(world.env_vars || "{}");
    const out = {};
    for (const [k, v] of Object.entries(obj)) if (k) out[String(k)] = String(v);
    return out;
  } catch { return {}; }
}

function buildArgs(world) {
  // Required launch flags for the dedicated server and logging behavior.
  const args = ["-server", "-log", "-NewConsole", `-port=${world.game_port}`, `-queryport=${world.query_port}`, `-RESTAPIPort=${world.rest_api_port}`];
  if (world.rest_api_enabled) args.push("-RESTAPIEnabled=true");
  // If mods are explicitly disabled for this world, hard-disable via launch flag.
  if (!world.mods_enabled) args.push("-NoMods");
  if (world.extra_args) args.push(...world.extra_args.split(/\s+/).filter(Boolean));
  const cap = require("./player-cap").settingsFor(world).maxPlayers;
  args.push(`-ini:Game:[/Script/Engine.GameSession]:MaxPlayers=${cap}`);
  return args;
}

function pushLog(worldId, line) {
  let buf = S.logs.get(worldId);
  if (!buf) { buf = []; S.logs.set(worldId, buf); }
  const stamped = `[${new Date().toISOString()}] ${line}`;
  buf.push(stamped);
  if (buf.length > RING) buf.shift();
  // append to rotating file
  try {
    fs.appendFileSync(path.join(P.worldLogDir(worldId), "console.log"), stamped + "\n");
  } catch {}
  // live listeners (SSE)
  const set = S.listeners.get(worldId);
  if (set) for (const fn of set) { try { fn(stamped); } catch {} }
}

function getLogs(worldId) {
  return S.logs.get(worldId) || [];
}
function subscribe(worldId, fn) {
  let set = S.listeners.get(worldId);
  if (!set) { set = new Set(); S.listeners.set(worldId, set); }
  set.add(fn);
  return () => set.delete(fn);
}

function isRunning(worldId) {
  const child = S.procs.get(worldId);
  return !!child && !child.killed && child.exitCode === null;
}

function pidAlive(pid) {
  if (!pid) return false;
  // signal 0 just probes existence. ESRCH = no such process (dead). EPERM = the
  // process exists but isn't ours to signal — which happens on Windows for a server
  // this process didn't spawn (e.g. after the app restarted), so that counts as alive.
  try { process.kill(pid, 0); return true; } catch (e) { return e.code === "EPERM"; }
}

// Like isRunning, but also true when we've lost the in-memory child handle (e.g. the
// app restarted while the world kept running) yet the recorded PID is still alive.
// Used by background delivery (scheduled broadcasts, warnings) so they don't silently
// treat a live server as offline after an app restart.
function isAlive(worldId) {
  if (isRunning(worldId)) return true;
  const w = dbm.getWorld(worldId);
  return !!(w && pidAlive(w.process_id));
}

async function startWorldUnlocked(worldId) {
  if (require("./jobs").listJobs().some((job) => job.status === "running" && job.phase === "copy")) {
    throw new Error("Wait for the private Server files copy to finish before starting a hosted Server.");
  }
  let world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  if (isRunning(worldId)) {
    S.owned.add(worldId);
    return { started: false, reason: "already running", pid: S.procs.get(worldId)?.pid || world.process_id || null };
  }
  // Never spawn a duplicate just because this Next process lost the ChildProcess
  // handle. A PID left by an older build is still a live server and must be
  // stopped/adopted before another launch.
  if (pidAlive(world.process_id)) {
    dbm.updateWorld(worldId, { status: "running" });
    return { started: false, reason: "server process already alive", pid: world.process_id };
  }
  // A previous app/interface crash can lose the persisted PID while leaving the
  // dedicated server behind. Its REST listener is an independent, OS-level guard:
  // never spawn another copy onto an already-owned world endpoint.
  if (world.rest_api_enabled && world.rest_api_port && !(await ports.isPortFree(world.rest_api_port))) {
    dbm.updateWorld(worldId, { status: "running", process_id: null });
    dbm.logEvent(worldId, "start", `Launch blocked: REST port ${world.rest_api_port} is already in use`);
    return { started: false, reason: "server endpoint already active", port: world.rest_api_port };
  }

  // Profile PIDs and the REST listener cannot identify an independently
  // launched copy of the SteamCMD template. Check the OS before touching the
  // active profile or spawning another dedicated server.
  require("./server-process-guard").assertNoConflictingServer(world);

  // A core update may have been published while this Server profile was
  // running. Apply its verified base-file delta only now, while launch owns
  // the profile lifecycle queue and before touching saves or mod loaders.
  const forks = require("./server-forks");
  const coreDir = dbm.getSetting("applicationSetup:serverDir", null);
  if (coreDir && forks.managedFork(world, coreDir) && forks.readLedger(world.install_dir)) {
    const result = await forks.refreshFork(coreDir, world, {
      onLog: (line) => pushLog(worldId, line),
      onProgress: ({ completed, total, file }) => pushLog(worldId, `RSDW core files ${completed}/${total}: ${file}`),
    });
    if (result.buildId) dbm.updateWorld(worldId, { build_id: result.buildId, latest_known_build_id: result.buildId });
  }

  // A running server keeps its world untouched. A queued selection is copied
  // into this profile's SaveGames only after it has stopped, immediately before
  // the next launch. Failure blocks launch instead of loading a fallback world.
  await applyPendingWorldSave(worldId);

  // Scheduled, remote and shortcut starts must obey the same active-profile
  // contract as the GUI. This loads that profile's settings and marker first.
  require("./active-server-profile").activate(worldId);
  require("./runtime-packages").materializeHost(worldId);
  world = dbm.getWorld(worldId);

  const plat = world.platform || hostPlatform();
  if (plat === "linux" && hostPlatform() === "win32") {
    throw new Error(
      "This world was provisioned for Linux and can't run on a Windows host. " +
      "Re-provision it for Windows, or run it on a Linux machine."
    );
  }

  // Re-assert this world's managed auth/network identity into DedicatedServer.ini
  // right before launch. The dedicated server may rewrite that file on a
  // clean shutdown, so a value it once loaded (e.g. a blank AdminPassword) would
  // otherwise persist across every restart — leaving REST enabled with no password,
  // which floods the log with "Unauthorized (AdminPassword is empty)" and blocks all
  // status polling. The DB is the source of truth; writing it here at every start
  // keeps a shutdown-clobbered ini from sticking. A REST-enabled world must never
  // have an empty admin password, so seed one if it's somehow blank.
  if (world.rest_api_enabled && !String(world.admin_password || "").trim()) {
    const pw = crypto.randomBytes(6).toString("hex");
    world = dbm.updateWorld(worldId, { admin_password: pw });
    dbm.logEvent(worldId, "settings", "Generated a missing admin password (REST API needs one)");
  }
  if (!fs.existsSync(world.install_dir)) throw new Error(`Server install folder missing: ${world.install_dir}`);
  const selectedSave = require("./provision").assertSelectedSaveReady(worldId);
  if (selectedSave) dbm.logEvent(worldId, "start", `Preflight confirmed selected world save ${selectedSave.activeSave} (${selectedSave.size} bytes)`);
  // Activation already wrote the profile once. Re-apply after any generated REST
  // password and require a successful read-back before spawning the server.
  ini.applyWorldNetworkSettings(world.install_dir, world);

  // Start the dedicated server directly as an app-owned subprocess. The desktop
  // lifecycle now shuts owned servers down cleanly instead of detaching them.
  const bin = serverBinary(world, { hidden: hideConsoleEnabled() });

  if (!fs.existsSync(bin)) throw new Error(`Server binary missing: ${bin}`);

  const wine = needsWine(world);
  let wineBin = null, winePrefix = null;
  if (wine) {
    wineBin = (world.wine_binary || "wine").trim() || "wine";
    if (!checkWineAvailable(wineBin)) {
      throw new Error(
        `Wine not found (tried "${wineBin}"). Install Wine, or set a different ` +
        `Wine binary path in this world's settings.`
      );
    }
    winePrefix = defaultWinePrefix(world);
    try { fs.mkdirSync(winePrefix, { recursive: true }); } catch {}
  }

  dbm.updateWorld(worldId, { status: "starting" });
  dbm.logEvent(worldId, "start", `Launching ${world.display_name}`);

  const args = buildArgs(world);
  pushLog(worldId, wine
    ? `Starting via Wine (${wineBin}${parseWineFlags(world).length ? " " + parseWineFlags(world).join(" ") : ""}, prefix ${winePrefix}): ${path.basename(bin)} ${args.join(" ")}`
    : `Starting: ${path.basename(bin)} ${args.join(" ")}`);

  // On Linux the .sh needs to be executable. A Windows .exe launched via Wine
  // doesn't need this, and native Windows hosts don't either.
  try { if (plat === "linux" && hostPlatform() !== "win32") fs.chmodSync(bin, 0o755); } catch {}

  const spawnOpts = {
    cwd: world.install_dir,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, ...parseCustomEnv(world) },
  };
  if (wine) {
    // WINEPREFIX/WINEDEBUG go in first so a user-supplied env var of the same
    // name (parseCustomEnv, merged above) can still override them deliberately.
    spawnOpts.env.WINEPREFIX = spawnOpts.env.WINEPREFIX || winePrefix;
    spawnOpts.env.WINEDEBUG = spawnOpts.env.WINEDEBUG || "-all";
  }

  const child = wine
    ? spawn(wineBin, [...parseWineFlags(world), bin, ...args], spawnOpts)
    : spawn(bin, args, spawnOpts);
  S.procs.set(worldId, child);
  S.owned.add(worldId);
  dbm.updateWorld(worldId, {
    status: "running",
    process_id: child.pid,
    last_started_at: Date.now(),
  });

  child.stdout.on("data", (d) => splitLines(d).forEach((l) => pushLog(worldId, l)));
  child.stderr.on("data", (d) => splitLines(d).forEach((l) => pushLog(worldId, l)));
  // The preflight prevents a wrong save at spawn time. Watch early startup too:
  // if Dragonwilds rejects it and creates a fallback .sav, stop immediately
  // rather than leaving a Standard world running under this profile.
  if (selectedSave) {
    let checks = 0;
    const checkSelectedSave = () => {
      if (S.procs.get(worldId) !== child || ++checks > 18) return;
      try { require("./provision").assertSelectedSaveReady(worldId); }
      catch (error) {
        pushLog(worldId, `Selected world save verification failed after launch: ${error.message}`);
        dbm.logEvent(worldId, "start", `Stopped to prevent a fallback world: ${error.message}`);
        void stopWorld(worldId, { graceful: false }).catch((stopError) => pushLog(worldId, `Could not stop fallback world: ${stopError.message}`));
        return;
      }
      const timer = setTimeout(checkSelectedSave, 5000);
      timer.unref?.();
    };
    const timer = setTimeout(checkSelectedSave, 5000);
    timer.unref?.();
  }
  child.on("close", (code) => {
    S.procs.delete(worldId);
    const w = dbm.getWorld(worldId);
    pushLog(worldId, `Process exited with code ${code}`);
    // If we weren't intentionally stopping/updating, mark crashed.
    if (w && w.status !== "stopping" && w.status !== "updating") {
      dbm.updateWorld(worldId, { status: "crashed", process_id: null });
      // A near-instant exit on Windows is very often missing runtimes (the server pops a
      // "component required" dialog and dies) — surface that specifically instead of a
      // generic crash, so the user knows to install the prerequisites.
      const quick = w.last_started_at && Date.now() - w.last_started_at < 15000;
      let pr = null;
      try { if (os.platform() === "win32" && quick) pr = require("./prereqs").check(); } catch {}
      if (pr && !pr.ok) {
        const miss = [!pr.vcredist && "Visual C++", !pr.directx && "DirectX"].filter(Boolean).join(" + ");
        const msg = `Failed to start — missing Windows runtime${miss.includes("+") ? "s" : ""}: ${miss}. Open the world → Install prerequisites.`;
        dbm.logEvent(worldId, "crash", msg);
        notify.notify(worldId, "crash", `${w.display_name}: ${msg}`, { code }).catch(() => {});
      } else {
        dbm.logEvent(worldId, "crash", `Exited unexpectedly (code ${code})`);
        notify.notify(worldId, "crash", `${w.display_name} crashed (exited unexpectedly, code ${code})`, { code });
      }
    } else {
      dbm.updateWorld(worldId, { status: "stopped", process_id: null });
    }
  });

  ensureGuardian();
  return { started: true, pid: child.pid };
}

async function stopWorldUnlocked(worldId, { graceful = true, waittime = 15 } = {}) {
  const world = dbm.getWorld(worldId);
  if (!world) throw new Error("World not found");
  // Removing ownership first makes a manual Stop authoritative: the crash
  // guardian cannot race the shutdown and relaunch it behind the user's back.
  S.owned.delete(worldId);
  S.restartAttempts.delete(worldId);
  dbm.updateWorld(worldId, { status: "stopping" });
  dbm.logEvent(worldId, "stop", `Stopping ${world.display_name}`);

  if (graceful && world.rest_api_enabled) {
    try {
      // Flush world data before shutdown. DedicatedServer.ini is NOT captured from
      // disk here: the selected Server profile is the source of truth and is
      // materialized again after the process exits.
      await rest.save(world).catch(() => {});
      await rest.shutdown(world, waittime, "Server shutting down.");
    } catch { /* fall through to hard kill */ }
  }
  const child = S.procs.get(worldId);
  const targetPid = child?.pid || world.process_id;
  await new Promise((resolve) => {
    let done = false;
    let poll = null;
    let hardTimer = null;
    let safetyTimer = null;
    const finish = () => {
      if (done) return;
      done = true;
      if (poll) clearInterval(poll);
      if (hardTimer) clearTimeout(hardTimer);
      if (safetyTimer) clearTimeout(safetyTimer);
      resolve();
    };

    const killTreeNow = () => {
      if (!targetPid || !pidAlive(targetPid)) return finish();
      // tree-kill uses taskkill /T /F on Windows and SIGKILL on Unix, so the
      // dedicated server and every launcher/worker it owns are terminated as one.
      const forceRoot = () => {
        if (!pidAlive(targetPid)) return;
        try { process.kill(targetPid, "SIGKILL"); } catch {}
      };
      // Some locked-down Windows hosts never return from taskkill's shell command.
      // Keep Stop authoritative by applying Node's direct process termination as a
      // bounded fallback, then let the existing liveness poll observe the exit.
      safetyTimer = setTimeout(() => { forceRoot(); setTimeout(finish, 250); }, 3500);
      kill(targetPid, "SIGKILL", (error) => {
        if (error && pidAlive(targetPid)) {
          pushLog(worldId, `Process-tree termination failed, forcing root process: ${error.message}`);
          forceRoot();
        }
        if (!pidAlive(targetPid)) finish();
      });
    };

    if (child) child.once("close", finish);
    if (!targetPid || !pidAlive(targetPid)) return finish();

    // Operator Stop is authoritative and immediate. Graceful callers (scheduled
    // restart/app exit) retain a bounded chance to save before the same hard kill.
    // Detect exit even for a persisted PID from an older app process where no
    // ChildProcess handle exists. This also makes immediate Stop return promptly.
    poll = setInterval(() => { if (!pidAlive(targetPid)) finish(); }, 50);

    if (!graceful) killTreeNow();
    else hardTimer = setTimeout(killTreeNow, (waittime + 5) * 1000);
  });
  if (targetPid && pidAlive(targetPid)) {
    dbm.updateWorld(worldId, { status: "running", process_id: targetPid });
    throw new Error(`Could not terminate server process tree ${targetPid}. Try running RSDW Sync as an administrator.`);
  }
  S.procs.delete(worldId);
  dbm.updateWorld(worldId, { status: "stopped", process_id: null });
  // Give Dragonwilds a moment to finish its exit-time writes, then put the
  // persisted Server profile back on disk. This prevents the game's shutdown
  // serialization from becoming the next launch's source of truth.
  if (graceful) await new Promise((r) => setTimeout(r, 800));
  try {
    const profiles = require("./active-server-profile");
    if (profiles.readActiveId() === worldId) {
      profiles.materialize(dbm.getWorld(worldId) || world);
      dbm.logEvent(worldId, "settings", "Re-materialized saved Server profile after shutdown");
    }
  } catch {}
  // A queued world can be placed as soon as the process is fully down. Stop
  // remains successful if the copy fails; the pending choice is retained and
  // startWorldUnlocked will retry (and fail closed rather than load the wrong save).
  if (pendingWorldSave(worldId)) {
    try { await applyPendingWorldSave(worldId); }
    catch (error) { dbm.logEvent(worldId, "import", `Queued world save still pending: ${error.message}`); }
  }
  return { stopped: true };
}

function startWorld(worldId, { automatic = false } = {}) {
  if (automatic && (!S.owned.has(worldId) || S.desired.get(worldId) === "stopped")) {
    return Promise.resolve({ started: false, reason: "automatic launch cancelled" });
  }
  if (!automatic || !S.desired.has(worldId)) S.desired.set(worldId, "running");
  return serializeLifecycle(worldId, "start", () => {
    if (S.desired.get(worldId) !== "running") return { started: false, reason: "launch cancelled by stop request" };
    return startWorldUnlocked(worldId);
  });
}

function runMaintenance(worldId, task, kind = "maintenance") {
  return serializeLifecycle(worldId, kind, async () => {
    if (isAlive(worldId)) throw new Error("Stop this Server profile before refreshing core files");
    return task();
  });
}

function stopWorld(worldId, options = {}) {
  // Record the operator's intent before waiting for an active start/restart. Any
  // queued automatic relaunch sees this immediately and becomes a no-op.
  S.desired.set(worldId, "stopped");
  S.owned.delete(worldId);
  S.restartAttempts.delete(worldId);
  return serializeLifecycle(worldId, "stop", () => stopWorldUnlocked(worldId, options));
}

function restartWorld(worldId, { waittime = 5, automatic = false } = {}) {
  if (automatic && (!S.owned.has(worldId) || S.desired.get(worldId) === "stopped")) {
    return Promise.resolve({ started: false, reason: "automatic restart cancelled" });
  }
  if (!automatic || !S.desired.has(worldId)) S.desired.set(worldId, "running");
  return serializeLifecycle(worldId, "restart", async () => {
    if (S.desired.get(worldId) !== "running") return { started: false, reason: "restart cancelled by stop request" };
    await stopWorldUnlocked(worldId, { graceful: true, waittime });
    if (S.desired.get(worldId) !== "running") return { started: false, reason: "restart cancelled by stop request" };
    await new Promise((r) => setTimeout(r, 700));
    if (S.desired.get(worldId) !== "running") return { started: false, reason: "restart cancelled by stop request" };
    // The unlocked variant is safe here because this whole restart owns the queue.
    return startWorldUnlocked(worldId);
  });
}

function pendingSaveKey(worldId) { return `pendingWorldSave:${worldId}`; }
function pendingWorldSave(worldId) { return dbm.getSetting(pendingSaveKey(worldId), null); }

async function applySaveSelection(worldId, selection) {
  const provision = require("./provision");
  // Preserve the just-stopped live save before staging a repository item with
  // the same filename. Otherwise activation's capture could overwrite the new
  // item in the slot vault before it reaches SaveGames.
  provision.listSaveSlots(worldId);
  const slotName = selection.repositoryId
    ? provision.stageRepositorySave(worldId, selection.repositoryId).slotName
    : selection.slotName;
  const activated = await provision.activateSaveSlot(worldId, slotName, { backupFirst: true });
  const verified = provision.verifyActiveSaveSlot(worldId, slotName);
  dbm.setSetting(pendingSaveKey(worldId), null);
  dbm.logEvent(worldId, "import", `Verified selected world save ${verified.activeSave} (${verified.size} bytes)`);
  return { ...activated, verified, queued: false, restarted: false };
}

async function applyPendingWorldSave(worldId) {
  const selection = pendingWorldSave(worldId);
  if (!selection) return null;
  if (isAlive(worldId)) throw new Error("Cannot replace a running server's world save");
  return applySaveSelection(worldId, selection);
}

function selectWorldSave(worldId, selection) {
  if (!dbm.getWorld(worldId)) return Promise.reject(new Error("World not found"));
  if (!selection || (!selection.slotName && !selection.repositoryId)) return Promise.reject(new Error("Choose a save slot or repository world"));
  return serializeLifecycle(worldId, "select-world-save", async () => {
    // Validate before recording a durable pending request.
    if (selection.repositoryId) require("./world-repository").getWorld(selection.repositoryId);
    else {
      const slot = require("./provision").listSaveSlots(worldId).find((item) => item.name === selection.slotName);
      if (!slot) throw new Error("Save slot not found");
    }
    if (isAlive(worldId)) {
      dbm.setSetting(pendingSaveKey(worldId), selection);
      dbm.logEvent(worldId, "import", "World save selection queued for the next server start; running server was not interrupted");
      return { queued: true, restarted: false, pending: selection };
    }
    return applySaveSelection(worldId, selection);
  });
}

function switchWorldSave(worldId, slotName) {
  return selectWorldSave(worldId, { slotName });
}

function removeWorldSave(worldId, selection) {
  if (!dbm.getWorld(worldId)) return Promise.reject(new Error("World not found"));
  return serializeLifecycle(worldId, "remove-world-save", () => selection.repositoryId
    ? require("./world-repository").removeWorld(selection.repositoryId)
    : require("./provision").removeSaveSlot(worldId, selection.slotName));
}

async function importAndSwitchWorldSave(worldId, sourcePath) {
  const item = require("./world-repository").importWorld(sourcePath);
  return selectWorldSave(worldId, { repositoryId: item.id });
}

// ---- Crash guardian (spec §9) ----
function ensureGuardian() {
  if (S.guardTimer) return;
  S.guardTimer = setInterval(guardTick, 20000);
}

function allowCrashRestart(worldId) {
  const now = Date.now();
  const windowStart = now - 10 * 60 * 1000;
  const attempts = (S.restartAttempts.get(worldId) || []).filter((at) => at >= windowStart);
  if (attempts.length >= 3) {
    S.owned.delete(worldId);
    S.restartAttempts.delete(worldId);
    dbm.logEvent(worldId, "guardian", "Crash guard paused after 3 restart attempts in 10 minutes; manual Start required");
    return false;
  }
  attempts.push(now);
  S.restartAttempts.set(worldId, attempts);
  return true;
}

async function guardTick() {
  const worlds = dbm.listWorlds();
  for (const w of worlds) {
    if (!w.crash_guard) continue;

    if (w.status === "crashed") {
      // Only relaunch a process this app deliberately launched. Stale status,
      // external processes and a previous app session never trigger surprise starts.
      if (!S.owned.has(w.world_id) || !allowCrashRestart(w.world_id)) continue;
      dbm.updateWorld(w.world_id, { crash_count: (w.crash_count || 0) + 1 });
      dbm.logEvent(w.world_id, "guardian", "Owned server crashed — restarting");
      try { await startWorld(w.world_id, { automatic: true }); } catch (e) {
        dbm.logEvent(w.world_id, "guardian", `Restart failed: ${e.message}`);
      }
      continue;
    }

    if (w.status === "running") {
      const alive = isRunning(w.world_id) || pidAlive(w.process_id);
      if (!alive) {
        dbm.updateWorld(w.world_id, { status: "crashed", process_id: null });
        continue;
      }

      // We can display/observe an older external PID, but we never restart it.
      if (!S.owned.has(w.world_id)) continue;

      // A slow, disabled, misconfigured, or still-booting REST API is not proof
      // that the game process has crashed. Restart only after an actual process
      // exit; otherwise a healthy dedicated server can be trapped in a loop.
    }
  }
}

async function stopManagedWorlds({ waittime = 5 } = {}) {
  const ids = [...S.owned];
  const results = [];
  for (const worldId of ids) {
    try {
      await stopWorld(worldId, { graceful: true, waittime });
      results.push({ worldId, stopped: true });
    } catch (e) {
      results.push({ worldId, stopped: false, error: e.message });
    }
  }
  return results;
}

function splitLines(buf) {
  return buf.toString("utf8").split(/\r?\n/).filter((l) => l.length);
}

module.exports = {
  serverBinary, shippingBinary, hideConsoleEnabled, buildArgs, startWorld, stopWorld, restartWorld, runMaintenance,
  switchWorldSave, importAndSwitchWorldSave, selectWorldSave, pendingWorldSave, removeWorldSave,
  isRunning, isAlive, pidAlive, getLogs, subscribe, pushLog, ensureGuardian, stopManagedWorlds,
  __testing: { serializeLifecycle },
};
