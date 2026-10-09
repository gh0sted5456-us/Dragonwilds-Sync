const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

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
  console.log("Lifecycle launch guard: OK");
})().finally(() => {
  try { require("../lib/db").db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
