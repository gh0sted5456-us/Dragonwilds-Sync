const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-lifecycle-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");

const supervisor = require("../lib/supervisor");
const { serializeLifecycle } = supervisor.__testing;

(async () => {
  let concurrent = 0;
  let peak = 0;
  let restartRuns = 0;
  const order = [];

  const first = serializeLifecycle("world-a", "restart", async () => {
    restartRuns += 1;
    concurrent += 1;
    peak = Math.max(peak, concurrent);
    order.push("restart-start");
    await new Promise((resolve) => setTimeout(resolve, 25));
    order.push("restart-end");
    concurrent -= 1;
    return { started: true };
  });
  const duplicate = serializeLifecycle("world-a", "restart", async () => {
    restartRuns += 1;
    throw new Error("duplicate restart executed");
  });
  assert.strictEqual(duplicate, first, "duplicate lifecycle requests were not coalesced");

  const stop = serializeLifecycle("world-a", "stop", async () => {
    concurrent += 1;
    peak = Math.max(peak, concurrent);
    order.push("stop");
    concurrent -= 1;
  });

  await Promise.all([first, duplicate, stop]);
  assert.strictEqual(restartRuns, 1, "duplicate restart ran more than once");
  assert.strictEqual(peak, 1, "lifecycle operations overlapped");
  assert.deepStrictEqual(order, ["restart-start", "restart-end", "stop"], "lifecycle queue order changed");

  const source = fs.readFileSync(path.join(__dirname, "..", "lib", "supervisor.js"), "utf8");
  assert(!source.includes("Owned server API unresponsive — restarting"), "REST health can still restart a live server");
  assert(source.includes("actual process"), "process-exit-only crash guard contract is missing");
  assert(source.includes("server endpoint already active"), "untracked live-server port guard is missing");

  // The primary Stop path must terminate even a persisted process that this app
  // no longer has a ChildProcess handle for (for example after an interface crash).
  const dbm = require("../lib/db");
  const worldId = "immediate-stop-test";
  dbm.insertWorld({
    world_id: worldId,
    display_name: "Immediate stop test",
    install_dir: sandbox,
    platform: process.platform === "win32" ? "windows" : "linux",
    env_vars: "{}",
    wine_binary: "wine",
    wine_prefix: null,
    wine_launch_flags: "",
    game_port: 48111,
    query_port: 48112,
    rest_api_port: 48113,
    rcon_port: 48114,
    admin_password: "",
    rest_api_enabled: 0,
    owner_id: null,
    default_world_name: null,
    status: "stopped",
    autostart: 0,
    crash_guard: 1,
    build_id: null,
    extra_args: "",
    created_at: Date.now(),
  });
  const victim = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], { stdio: "ignore", windowsHide: true });
  dbm.updateWorld(worldId, { process_id: victim.pid, status: "running" });
  const stopStarted = Date.now();
  await supervisor.stopWorld(worldId, { graceful: false });
  assert(Date.now() - stopStarted < 6000, "immediate Stop waited too long");
  assert(!supervisor.pidAlive(victim.pid), "immediate Stop left the server process alive");
  assert.strictEqual(dbm.getWorld(worldId).status, "stopped", "immediate Stop did not reconcile world status");
  console.log("Lifecycle launch guard: OK");
})().finally(() => {
  try { require("../lib/db").db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
