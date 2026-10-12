// lib/metrics.js
// Cross-platform CPU / RAM usage sampler for running world processes.
//
// Dragonwilds' launcher (RSDragonwildsServer.exe on Windows, RSDragonwildsServer.sh on Linux) spawns
// the real shipping binary as a child, so the interesting CPU/RAM lives in the
// process *subtree* rooted at the pid we track — not the launcher itself. This
// module snapshots every process on the machine, sums usage across each world's
// subtree, and keeps a rolling history so the Usage page can graph it.
//
// Author: Prakash Mandal <prakashmandal.iv@gmail.com>
const fs = require("fs");
const os = require("os");
const { execFile } = require("child_process");
const dbm = require("./db");
const sup = require("./supervisor");

const NCPU = Math.max(1, os.cpus().length || 1);
const SAMPLE_MS = 4000;   // how often we sample
const HISTORY = 180;      // points kept per world (~12 min at 4s)

const g = globalThis;
if (!g.__APP_METRICS) {
  g.__APP_METRICS = {
    timer: null,
    prev: null,               // { at, cpu: Map(pid -> cpuSeconds) }
    current: new Map(),       // world_id -> { cpu, rssMB, pids, at }
    history: new Map(),       // world_id -> [{ t, cpu, rssMB }]
    sampling: false,
  };
}
const M = g.__APP_METRICS;

// ---- platform process snapshot ------------------------------------------------
// Returns Map(pid -> { ppid, cpu(seconds), rss(bytes) }) for every process.

function snapshotWindows() {
  return new Promise((resolve) => {
    // KernelModeTime + UserModeTime are in 100-nanosecond units; WorkingSetSize is bytes.
    const ps =
      "Get-CimInstance Win32_Process | ForEach-Object { " +
      "'{0} {1} {2} {3}' -f $_.ProcessId, $_.ParentProcessId, " +
      "([int64]$_.KernelModeTime + [int64]$_.UserModeTime), [int64]$_.WorkingSetSize }";
    execFile(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", ps],
      { windowsHide: true, maxBuffer: 8 * 1024 * 1024 },
      (err, stdout) => {
        const map = new Map();
        if (err || !stdout) return resolve(map);
        for (const line of stdout.split(/\r?\n/)) {
          const p = line.trim().split(/\s+/);
          if (p.length < 4) continue;
          const pid = +p[0], ppid = +p[1], time100ns = +p[2], rss = +p[3];
          if (!pid) continue;
          map.set(pid, { ppid, cpu: time100ns / 1e7, rss });
        }
        resolve(map);
      }
    );
  });
}

function snapshotLinux() {
  return new Promise((resolve) => {
    const map = new Map();
    const CLK = 100;                    // sysconf(_SC_CLK_TCK), 100 on virtually all Linux
    const PAGE = 4096;                  // sysconf(_SC_PAGESIZE)
    let names;
    try { names = fs.readdirSync("/proc"); } catch { return resolve(map); }
    for (const name of names) {
      if (!/^\d+$/.test(name)) continue;
      const pid = +name;
      let stat;
      try { stat = fs.readFileSync(`/proc/${name}/stat`, "utf8"); } catch { continue; }
      // comm (field 2) can contain spaces/parens — split on the last ')'.
      const close = stat.lastIndexOf(")");
      if (close === -1) continue;
      const rest = stat.slice(close + 2).split(/\s+/);
      // rest[0]=state, rest[1]=ppid, ... rest[11]=utime, rest[12]=stime, rest[21]=rss(pages)
      const ppid = +rest[1];
      const utime = +rest[11], stime = +rest[12], rssPages = +rest[21];
      if (Number.isNaN(utime)) continue;
      map.set(pid, { ppid, cpu: (utime + stime) / CLK, rss: rssPages * PAGE });
    }
    resolve(map);
  });
}

function snapshot() {
  return os.platform() === "win32" ? snapshotWindows() : snapshotLinux();
}

// Collect a pid and all of its descendants from the snapshot.
function subtreePids(rootPid, snap) {
  // children index
  const children = new Map();
  for (const [pid, info] of snap) {
    if (!children.has(info.ppid)) children.set(info.ppid, []);
    children.get(info.ppid).push(pid);
  }
  const out = new Set();
  const stack = [rootPid];
  while (stack.length) {
    const pid = stack.pop();
    if (out.has(pid) || !snap.has(pid)) continue;
    out.add(pid);
    for (const c of children.get(pid) || []) stack.push(c);
  }
  return out;
}

// ---- sampling -----------------------------------------------------------------

async function sampleOnce() {
  if (M.sampling) return;
  M.sampling = true;
  try {
    // Which worlds are actually running, and by which root pid?
    const roots = [];
    for (const w of dbm.listWorlds()) {
      const pid = w.process_id;
      const running = sup.isRunning(w.world_id) || sup.pidAlive(pid);
      if (running && pid) roots.push({ world_id: w.world_id, pid });
    }
    if (roots.length === 0) {
      M.current = new Map();
      M.prev = null;   // reset baseline so CPU deltas don't span an idle gap
      return;
    }

    const snap = await snapshot();
    const now = Date.now();
    const dt = M.prev ? (now - M.prev.at) / 1000 : 0;

    const next = new Map();
    for (const { world_id, pid } of roots) {
      const pids = subtreePids(pid, snap);
      let rss = 0, cpuNow = 0, cpuPrev = 0;
      for (const p of pids) {
        const info = snap.get(p);
        if (!info) continue;
        rss += info.rss;
        cpuNow += info.cpu;
        if (M.prev) cpuPrev += M.prev.cpu.get(p) || 0;
      }
      // CPU as a percentage of the whole machine (0-100 across all cores).
      let cpuPct = 0;
      if (dt > 0.2) cpuPct = Math.max(0, ((cpuNow - cpuPrev) / dt / NCPU) * 100);
      const rec = {
        cpu: Math.round(cpuPct * 10) / 10,
        rssMB: Math.round(rss / (1024 * 1024)),
        pids: pids.size,
        at: now,
      };
      next.set(world_id, rec);

      let hist = M.history.get(world_id);
      if (!hist) { hist = []; M.history.set(world_id, hist); }
      hist.push({ t: now, cpu: rec.cpu, rssMB: rec.rssMB });
      if (hist.length > HISTORY) hist.shift();
    }

    // Build the per-pid cpu map for the next delta.
    const cpuMap = new Map();
    for (const [pid, info] of snap) cpuMap.set(pid, info.cpu);
    M.prev = { at: now, cpu: cpuMap };
    M.current = next;
  } catch {
    /* transient — try again next tick */
  } finally {
    M.sampling = false;
  }
}

function ensureSampler() {
  if (M.timer) return;
  M.timer = setInterval(() => { sampleOnce().catch(() => {}); }, SAMPLE_MS);
  // kick off an immediate first sample so the first delta is available sooner
  sampleOnce().catch(() => {});
}

// ---- read API -----------------------------------------------------------------

function getSnapshot() {
  const worlds = dbm.listWorlds();
  const nameById = new Map(worlds.map((w) => [w.world_id, w.display_name]));
  const accentById = new Map(worlds.map((w) => [w.world_id, w.accent_color || null]));

  const items = [];
  for (const [world_id, cur] of M.current) {
    items.push({
      world_id,
      name: nameById.get(world_id) || world_id,
      accent: accentById.get(world_id) || null,
      cpu: cur.cpu,
      rssMB: cur.rssMB,
      pids: cur.pids,
      history: M.history.get(world_id) || [],
    });
  }
  items.sort((a, b) => a.name.localeCompare(b.name));

  const totalCpu = Math.round(items.reduce((s, i) => s + i.cpu, 0) * 10) / 10;
  const totalRssMB = items.reduce((s, i) => s + i.rssMB, 0);

  return {
    ncpu: NCPU,
    totalMemMB: Math.round(os.totalmem() / (1024 * 1024)),
    sampleMs: SAMPLE_MS,
    items,
    total: { cpu: totalCpu, rssMB: totalRssMB, worlds: items.length },
  };
}

module.exports = { ensureSampler, sampleOnce, getSnapshot, SAMPLE_MS };
