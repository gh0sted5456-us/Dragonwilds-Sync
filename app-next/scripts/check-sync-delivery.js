const assert = require("assert");
const fs = require("fs");
const path = require("path");
const os = require("os");
const http = require("http");
const crypto = require("crypto");
const vm = require("vm");
const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-sync-delivery-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
process.env.PSM_SQLITE_BACKEND = "wasm";
const dbm = require("../lib/db");
const client = require("../lib/sync/client");
const manifestLib = require("../lib/sync/manifest");
const jobs = require("../lib/jobs");
const { journeyState, deliveryInfo } = require("../lib/sync-progress");
const { renameWithRetry } = require("../lib/sync/fs-retry");
const install = path.join(sandbox, "game");
fs.mkdirSync(path.join(install, "RSDragonwilds/Binaries/Win64"), { recursive: true });
fs.mkdirSync(path.join(install, "RSDragonwilds/Content"), { recursive: true });
dbm.setSetting("clientInstall:steam", install);
const scenarios = new Map();
const realFetch = global.fetch;
const cloudRequests = [];
const events = new Map();
let server;
const setSyncProgress = jobs.setSyncProgress;
jobs.setSyncProgress = (id, event) => {
  if (!events.has(id)) events.set(id, []);
  events.get(id).push(event);
  setSyncProgress(id, event);
};
// Exercise the actual Next route body against real modules, a disposable DB,
// real TCP streams, and a minimal NextResponse adapter (no Next server needed).
const routeFile = path.join(__dirname, "../app/api/profiles/[id]/sync/route.js");
const routeSource = fs.readFileSync(routeFile, "utf8")
  .replace('import { NextResponse } from "next/server";', 'const NextResponse = { json: (data, options) => ({ data, status: options?.status || 200 }) };')
  .replaceAll("export const ", "const ").replace("export async function POST", "async function POST");
const routeModule = { exports: {} };
vm.runInNewContext(routeSource + "\nmodule.exports = { POST };", { module: routeModule, require: (name) => require(name.startsWith("@/") ? path.join(__dirname, "..", name.slice(2)) : name), console });
const syncRoute = (id) => routeModule.exports.POST({ headers: new Headers() }, { params: { id } });

function define(id, mode, behavior = "valid", count = 1) {
  const files = Array.from({ length: count }, (_, i) => {
    const content = Buffer.from(`verified-${id}-mod-${i}-`.repeat(100));
    return { target: `RSDragonwilds/Content/Paks/~mods/${id}-${i}.pak`, size: content.length, sha256: crypto.createHash("sha256").update(content).digest("hex"), content };
  });
  const value = {
    protocol: manifestLib.PROTOCOL, protocolVersion: manifestLib.PROTOCOL_VERSION, revision: `revision-${id}`,
    world: { id, name: id, rules: {}, identity: {} }, prerequisites: {},
    transport: { kind: "http-over-tcp", storageMode: mode, storageProvider: "generic" },
    units: [{ key: id, name: id, type: "pak", bytes: files.reduce((n, f) => n + f.size, 0), fileCount: files.length, files: files.map(({ content, ...file }) => file) }],
  };
  const scenario = { id, value, files, mode, behavior, hostFiles: 0, cloudFiles: 0, fallbackFiles: 0, rejectApproval: false, manifestStatus: 200 };
  scenarios.set(id, scenario);
  dbm.upsertProfile({ profile_id: id, display_name: id, client_install: install, server_world_id: id, connection: { address: "127.0.0.1", syncPort: server.address().port, worldId: id, service: "steam", password: "fixture-world-secret" } });
  return scenario;
}
function json(res, status, body) { res.writeHead(status, { "Content-Type": "application/json" }); res.end(JSON.stringify(body)); }
function content(res, bytes) { res.writeHead(200, { "Content-Type": "application/octet-stream", "Content-Length": bytes.length }); res.end(bytes); }
async function host(req, res) {
  const url = new URL(req.url, "http://localhost");
  const parts = url.pathname.split("/");
  const scenario = scenarios.get(parts[4]);
  if (!scenario) return json(res, 404, { error: "Unknown fixture" });
  if (req.headers["x-rsdw-world-password"] !== "fixture-world-secret") return json(res, 401, { error: "World password is incorrect" });
  if (parts[5] === "file") {
    const file = scenario.files.find((f) => f.target === url.searchParams.get("target")) || scenario.files[0];
    if (url.searchParams.get("source") === "local") { scenario.fallbackFiles++; return content(res, file.content); }
    if (scenario.mode !== "local") { res.writeHead(307, { Location: `https://files.example.test/${scenario.id}/${scenario.files.indexOf(file)}` }); return res.end(); }
    scenario.hostFiles++; return content(res, file.content);
  }
  if (parts[5] === "admission") {
    let body = ""; for await (const chunk of req) body += chunk;
    if (scenario.approvalSeen) { scenario.approvalSeen(); await scenario.approvalHold; }
    if (scenario.rejectApproval) return json(res, 409, { error: "Manifest changed; sync again" });
    try {
      const approval = manifestLib.verifyClientAttestation(scenario.value, JSON.parse(body));
      return json(res, 200, { admission: { ...approval, token: "never-store-this-token", expiresAt: Date.now() + 60000, approvedAt: Date.now() } });
    } catch (error) { return json(res, 409, { error: error.message }); }
  }
  return json(res, scenario.manifestStatus, scenario.manifestStatus === 200 ? { manifest: scenario.value } : { error: "World password is incorrect" });
}
global.fetch = async (input, options = {}) => {
  const url = new URL(input);
  if (url.hostname !== "files.example.test") return realFetch(input, options);
  cloudRequests.push({ url: url.toString(), options });
  const scenario = scenarios.get(url.pathname.split("/")[1]);
  const file = scenario.files[Number(url.pathname.split("/")[2])] || scenario.files[0];
  scenario.cloudFiles++;
  assert(!new Headers(options.headers).has("x-rsdw-world-password"), "world password leaked to cloud");
  assert(!new Headers(options.headers).has("cookie"), "cookies leaked to cloud");
  assert.equal(options.redirect, "manual", "cloud redirects must be validated");
  if (scenario.behavior === "timeout") return new Promise((_, reject) => options.signal.addEventListener("abort", () => reject(new DOMException("Cloud timed out", "AbortError")), { once: true }));
  if (scenario.behavior === "expired") return new Response("Expired", { status: 401 });
  if (scenario.behavior === "unavailable") return new Response("Unavailable", { status: 503 });
  if (scenario.behavior === "interrupted") return new Response(new ReadableStream({ start(controller) { controller.enqueue(file.content.subarray(0, Math.floor(file.size / 2))); setTimeout(() => controller.error(new Error("Fixture connection interrupted")), 20); } }), { headers: { "Content-Type": "application/octet-stream" } });
  if (scenario.behavior === "html") return new Response("<html>Google login</html>", { headers: { "Content-Type": "text/html" } });
  if (scenario.behavior === "downgrade") return new Response(null, { status: 302, headers: { location: "http://files.example.test/unsafe" } });
  if (scenario.behavior === "oversized") return new Response(Buffer.concat([file.content, Buffer.from("extra")]), { headers: { "Content-Type": "application/octet-stream" } });
  return new Response(scenario.behavior === "corrupt" ? Buffer.alloc(file.size, 65) : file.content, { headers: { "Content-Length": String(file.size), "Content-Type": "application/octet-stream" } });
};

(async () => {
  let renameAttempts = 0;
  await renameWithRetry("fixture-candidate", "fixture-profile", { rename: async () => { if (++renameAttempts < 3) throw Object.assign(new Error("Temporarily locked"), { code: "EPERM" }); }, wait: async () => {} });
  assert.equal(renameAttempts, 3, "temporary Windows locks were not retried");
  renameAttempts = 0;
  await assert.rejects(renameWithRetry("a", "b", { attempts: 3, rename: async () => { renameAttempts++; throw Object.assign(new Error("Still locked"), { code: "EBUSY" }); }, wait: async () => {} }), /Still locked/);
  assert.equal(renameAttempts, 3, "rename retries must be bounded");
  await assert.rejects(renameWithRetry("a", "b", { rename: async () => { throw Object.assign(new Error("Occupied"), { code: "EEXIST" }); }, wait: async () => { throw new Error("must not retry occupied destinations"); } }), /Occupied/);
  server = http.createServer((req, res) => { host(req, res).catch((error) => json(res, 500, { error: error.message })); });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  let lastGood;
  for (const [id, mode, behavior, success] of [
    ["direct", "local", "valid", true], ["cloud", "cloud", "valid", true],
    ["hybrid", "hybrid", "valid", true], ["hybrid-expired", "hybrid", "expired", true],
    ["hybrid-corrupt", "hybrid", "corrupt", true], ["hybrid-html", "hybrid", "html", true],
    ["hybrid-interrupted", "hybrid", "interrupted", true],
    ["cloud-failed", "cloud", "unavailable", false], ["cloud-corrupt", "cloud", "corrupt", false],
    ["cloud-oversized", "cloud", "oversized", false], ["cloud-downgrade", "cloud", "downgrade", false],
  ]) {
    const scenario = define(id, mode, behavior, success ? 3 : 1);
    const before = lastGood && fs.readFileSync(path.join(install, lastGood.files[0].target));
    const response = await syncRoute(id);
    const job = jobs.listJobs().find((j) => j.worldId === id);
    assert.equal(response.status, success ? 200 : 400, `${id}: ${JSON.stringify(response.data)}`);
    assert.equal(job.status, success ? "success" : "error", id);
    assert(!JSON.stringify(job).includes("https://"), "cloud URL leaked into Downloads");
    assert(!JSON.stringify(job).includes("fixture-world-secret"), "password leaked into Downloads");
    if (success) {
      assert(response.data.admission.approved, id);
      assert.equal(job.sync.stage, "ready", id);
      assert.equal(job.sync.transfer.filesDone, scenario.files.length);
      assert.equal(job.sync.transfer.bytesDone, job.sync.transfer.bytesTotal, "retry bytes were double-counted");
      assert.equal(job.sync.transfer.fallbackCount, behavior === "valid" ? 0 : scenario.files.length);
      assert.equal(scenario.fallbackFiles, behavior === "valid" ? 0 : scenario.files.length);
      for (const file of scenario.files) assert(fs.readFileSync(path.join(install, file.target)).equals(file.content), id);
      const trace = events.get(job.id);
      const verify = trace.find((event) => event.phase === "verify");
      assert.equal(verify.transfer.filesDone, verify.transfer.filesTotal, "global verification advanced before all downloads were checked");
      assert(!JSON.stringify(JSON.parse(dbm.getProfile(id).connection_json).admission).includes("never-store"), "admission token persisted");
      lastGood = scenario;
    } else {
      assert.equal(scenario.fallbackFiles, 0, "cloud-only mode silently used the host");
      assert(!fs.existsSync(path.join(install, scenario.files[0].target)), "failed download was activated");
      if (before) assert(fs.readFileSync(path.join(install, lastGood.files[0].target)).equals(before), "failed transfer changed the active profile");
      const view = journeyState({ job });
      assert(view.error && !view.complete);
      assert.equal(view.steps.find((s) => s.state === "error").id, "download");
    }
  }

  const held = define("approval-held", "local");
  let seen, release;
  const incoming = new Promise((resolve) => { seen = resolve; });
  held.approvalSeen = seen; held.approvalHold = new Promise((resolve) => { release = resolve; });
  const pending = syncRoute(held.id);
  await incoming;
  const waiting = jobs.listJobs().find((j) => j.worldId === held.id);
  assert.equal(waiting.status, "running", "Downloads claimed success before host approval");
  assert.equal(waiting.sync.stage, "ack");
  assert(waiting.percent < 100);
  release(); assert.equal((await pending).status, 200);

  const denied = define("approval-denied", "local"); denied.rejectApproval = true;
  assert.equal((await syncRoute(denied.id)).status, 400);
  const deniedJob = jobs.listJobs().find((j) => j.worldId === denied.id);
  assert.equal(deniedJob.sync.failedStage, "ack");
  assert(!JSON.parse(dbm.getProfile(denied.id).connection_json).admission);
  denied.rejectApproval = false;
  const retry = await syncRoute(denied.id);
  assert.equal(retry.status, 200);
  assert.equal(retry.data.result.transfer.filesTotal, 0, "approval retry re-downloaded current files");
  denied.manifestStatus = 403;
  assert.equal((await syncRoute(denied.id)).status, 400, "bad credentials were hidden by cached manifest fallback");
  // A failed replacement must restore even the very operation whose projection
  // failed, not just operations completed earlier in the batch.
  const destination = path.join(install, denied.files[0].target);
  const snapshot = path.join(sandbox, "data/player-profiles", denied.id, denied.files[0].target);
  const isolation = require("../lib/client-isolation");
  const assertReady = isolation.assertManagedReady;
  const originals = Object.fromEntries(["link", "symlink", "copyFile"].map((name) => [name, fs.promises[name]]));
  try {
    isolation.assertManagedReady = (...args) => {
      assertReady(...args);
      // Simulate an external edit after the normal safety check has passed.
      fs.unlinkSync(destination); fs.writeFileSync(destination, "original before failed projection");
    };
    for (const name of Object.keys(originals)) fs.promises[name] = async (...args) => {
      if (args[0] === snapshot && args[1] === destination) throw Object.assign(new Error("Fixture projection failure"), { code: "EACCES" });
      return originals[name](...args);
    };
    await assert.rejects(client.activateProfileSnapshot(denied.id), /projection failure/);
    assert.equal(fs.readFileSync(destination, "utf8"), "original before failed projection", "failed projection lost the original destination file");
  } finally { isolation.assertManagedReady = assertReady; for (const name of Object.keys(originals)) fs.promises[name] = originals[name]; }

  const timeout = define("hybrid-timeout", "hybrid", "timeout");
  const staging = path.join(sandbox, "timeout"); fs.mkdirSync(staging);
  const file = timeout.value.units[0].files[0];
  let bytes = 0;
  const downloaded = await client.downloadChange(`http://127.0.0.1:${server.address().port}/api/sync/public/${timeout.id}`, { password: "fixture-world-secret" }, "steam", staging, { ...file, storageMode: "hybrid", storageProvider: "generic" }, (delta) => { bytes += delta; }, () => {}, { timeoutMs: 250 });
  assert.equal(downloaded.source, "fallback", "cloud timeout poisoned fallback's signal");
  assert.equal(bytes, file.size);

  const stale = jobs.createJob({ type: "sync", worldId: "phase-test" });
  jobs.setSyncProgress(stale, { phase: "download", percent: 50, message: "Safe https://storage.invalid/private?token=secret" });
  jobs.setSyncProgress(stale, { phase: "ack", percent: null, message: "Waiting" });
  assert.equal(jobs.getJob(stale).percent, null, "indeterminate phase retained a stale percentage");
  assert.equal(deliveryInfo({ storageMode: "cloud", storageProvider: "google" }).source, "Google Drive");
  assert.equal(journeyState({ stage: "ready", job: { status: "running", sync: { stage: "ack" } } }).current, "ready", "stale polling overrode a completed API response");
  assert(cloudRequests.length > 0);
  console.log("Sync delivery: direct/cloud/hybrid, expired/corrupt/HTML/oversized files, HTTPS redirect safety, timeout fallback, progress, activation safety, ACK timing/rejection/retry and credential privacy: OK");
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(async () => {
  global.fetch = realFetch; jobs.setSyncProgress = setSyncProgress;
  if (server?.listening) await new Promise((resolve) => server.close(resolve));
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
});
