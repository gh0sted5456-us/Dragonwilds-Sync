const assert = require("assert");
const fs = require("fs");
const path = require("path");
const os = require("os");
const vm = require("vm");
const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-job-polling-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
process.env.DWSM_ADMIN_TOKEN = "jobs-test-only";
const dbm = require("../lib/db");
const jobs = require("../lib/jobs");
const { jobsResponse } = require("../lib/jobs-response");
const request = (etag, admin = true) => new Request("http://localhost/api/jobs", { headers: { ...(etag ? { "If-None-Match": etag } : {}), ...(admin ? { cookie: "dwsm_admin=jobs-test-only" } : {}) } });

function clientHarness() {
  const requests = [], timers = new Map();
  let timerId = 0;
  const document = new EventTarget(); document.visibilityState = "visible";
  const window = new EventTarget();
  const code = fs.readFileSync(path.join(__dirname, "../components/jobsClient.jsx"), "utf8")
    .split("function subscribeDisabled")[0].replace(/^import .*\r?\n/gm, "").replaceAll("export function ", "function ");
  const module = { exports: {} };
  vm.runInNewContext(`${code}\nmodule.exports = { pollJobs, subscribeJobs, getJobsSnapshot, pollDelay };`, {
    module, document, window, AbortController,
    setTimeout(callback, ms) { const id = ++timerId; timers.set(id, { callback, ms }); return id; },
    clearTimeout(id) { timers.delete(id); },
    fetch(url, options) { return new Promise((resolve, reject) => {
      requests.push({ url, ...options, resolve, reject });
      options.signal.addEventListener("abort", () => reject(new DOMException("cancelled", "AbortError")), { once: true });
    }); },
  });
  return { ...module.exports, requests, timers, document, window };
}

(async () => {
  try {
    dbm.setSetting("remoteAccess.enabled", true);
    const id = jobs.createJob({ type: "update", worldName: "Fixture" });
    for (let line = 0; line < 10000; line++) jobs.logJob(id, `${line}: synthetic SteamCMD output ${"x".repeat(90)}`);
    const first = jobsResponse(request());
    assert.equal(first.status, 200);
    assert(first.headers.get("cache-control").includes("private"));
    const tag = first.headers.get("etag");
    const initialBody = await first.text();
    assert.equal(JSON.parse(initialBody).jobs[0].lines.length, 10000, "Full SteamCMD output must not be truncated");
    const unchanged = jobsResponse(request(tag));
    assert.equal(unchanged.status, 304);
    assert.equal((await unchanged.arrayBuffer()).byteLength, 0);
    assert.equal(jobsResponse(request(`W/${tag}`)).status, 304);
    assert.equal(jobsResponse(request(tag, false)).status, 403, "Authorize before conditional responses");
    jobs.setProgress(id, 45, "Working");
    const progress = jobsResponse(request(tag));
    assert.equal(progress.status, 200);
    assert.notEqual(progress.headers.get("etag"), tag);
    const progressTag = progress.headers.get("etag");
    jobs.getJob(id).sync = { transfer: { acceptedBytes: 5 } };
    assert.notEqual(jobsResponse(request(progressTag)).headers.get("etag"), progressTag, "Direct mutations must invalidate the actual payload tag");
    jobs.logJob(id, "Last line stays available");
    assert.equal((await jobsResponse(request()).json()).jobs[0].lines.at(-1), "Last line stays available");
    const beforePrune = jobsResponse(request()).headers.get("etag");
    jobs.getJob(id).status = "success"; jobs.getJob(id).endedAt = Date.now() - 11 * 60 * 1000;
    assert.notEqual(jobsResponse(request(beforePrune)).headers.get("etag"), beforePrune);

    const h = clientHarness();
    let renders = 0;
    const offA = h.subscribeJobs(() => renders++), offB = h.subscribeJobs(() => renders++);
    const p = h.pollJobs(), concurrent = h.pollJobs();
    assert.equal(h.requests.length, 1, "Sidebar and Downloads share one HTTP poll");
    let parses = 0;
    const response = new Response(JSON.stringify({ ok: true, jobs: [{ id: "one", status: "running", lines: ["full output"] }] }), { headers: { etag: '"one"' } });
    const json = response.json.bind(response); response.json = () => { parses++; return json(); };
    h.requests[0].resolve(response);
    await Promise.all([p, concurrent]);
    const snapshot = h.getJobsSnapshot();
    assert.equal(parses, 1); assert.equal(renders, 2);
    assert.equal(h.pollDelay(), 1000);
    const next = h.pollJobs();
    assert.equal(h.requests[1].headers["If-None-Match"], '"one"');
    const noChange = new Response(null, { status: 304 }); noChange.json = () => { throw new Error("Never parse a 304 response"); };
    h.requests[1].resolve(noChange); await next;
    assert.strictEqual(h.getJobsSnapshot(), snapshot); assert.equal(renders, 2, "Unchanged logs must not trigger React renders");
    h.document.visibilityState = "hidden"; assert.equal(h.pollDelay(), 4000);
    const denied = h.pollJobs(); h.requests[2].resolve(new Response("{}", { status: 403 })); await denied;
    assert.equal(h.getJobsSnapshot().length, 0); assert.equal(h.pollDelay(), 60000);
    const stuck = h.pollJobs();
    assert(!h.requests[3].headers["If-None-Match"], "An authorization failure must clear the previous data tag");
    const watchdog = [...h.timers.values()].find((entry) => entry.ms === 10000);
    assert(watchdog, "A stuck poll needs an abort timeout"); watchdog.callback(); await stuck;
    assert(h.requests[3].signal.aborted);
    const retry = h.pollJobs(); h.requests[4].resolve(new Response('{"ok":true,"jobs":[]}')); await retry;
    const pending = h.pollJobs(); offA(); assert(!h.requests[5].signal.aborted); offB();
    assert(h.requests[5].signal.aborted, "The last consumer must cancel outstanding polling"); await pending;
    assert.equal(h.timers.size, 0, "Unsubscribing must clean up poll and timeout timers");
    const bytes = Buffer.byteLength(initialBody);
    console.log(`Conditional Downloads polling: ${bytes} log-body bytes -> 0 on unchanged polls; full logs/progress/pruning, authorization, shared snapshots, 304 no-parse/no-render, timeout recovery and cancellation: OK`);
  } finally {
    try { dbm.db().close(); } catch {}
    assert(path.dirname(sandbox).toLowerCase() === path.resolve(os.tmpdir()).toLowerCase() && path.basename(sandbox).startsWith("rsdw-job-polling-"));
    fs.rmSync(sandbox, { recursive: true, force: true });
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
