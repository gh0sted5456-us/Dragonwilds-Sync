import { NextResponse } from "next/server";
const fs = require("fs");
const path = require("path");
const os = require("os");
const dbm = require("@/lib/db");
const steam = require("@/lib/steamcmd");
const jobs = require("@/lib/jobs");
const detect = require("@/lib/detect");
const forks = require("@/lib/server-forks");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DIR_KEY = "applicationSetup:serverDir";
const PLATFORM_KEY = "applicationSetup:serverPlatform";
const OWNER_KEY = "applicationSetup:ownerId";

function current() {
  const installDir = dbm.getSetting(DIR_KEY, null);
  const platform = dbm.getSetting(PLATFORM_KEY, os.platform() === "win32" ? "windows" : "linux");
  let info = null;
  if (installDir) {
    try { info = detect.inspect(installDir); } catch {}
  }
  return {
    installDir,
    platform,
    defaultOwnerId: String(dbm.getSetting(OWNER_KEY, "") || "").trim(),
    profileRoot: installDir ? forks.profileRoot(installDir) : String(dbm.getSetting(forks.ROOT_KEY, "") || ""),
    ready: !!(installDir && info?.valid),
    buildId: info?.buildId || null,
    binary: info?.binary || null,
    steamcmdInstalled: steam.steamcmdInstalled(),
    steamcmdPath: steam.steamcmdBinary(),
  };
}

export async function PATCH(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Admin access required." }, { status: 403 });
  try {
    const body = await req.json();
    if (typeof body?.defaultOwnerId !== "string" && typeof body?.profileRoot !== "string") {
      throw new Error("Choose a default Owner ID or Server profiles folder to save.");
    }
    if (typeof body.profileRoot === "string") {
      const template = dbm.getSetting(DIR_KEY, null);
      if (!template) throw new Error("Link or install the shared dedicated server before choosing a profiles folder.");
      dbm.setSetting(forks.ROOT_KEY, forks.validateRoot(body.profileRoot.trim(), template));
    }
    if (typeof body.defaultOwnerId === "string") dbm.setSetting(OWNER_KEY, body.defaultOwnerId.trim());
    return NextResponse.json({ ok: true, server: current() });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}

export async function GET(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Admin access required." }, { status: 403 });
  return NextResponse.json({ ok: true, server: current() });
}

export async function POST(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Admin access required." }, { status: 403 });
  try {
    const body = await req.json();
    if (jobs.listJobs().some((job) => job.status === "running" && job.phase === "copy")) {
      return NextResponse.json({ ok: false, error: "Wait for the private Server files copy to finish before changing the shared installation." }, { status: 409 });
    }
    const rawPath = String(body.executablePath || body.installDir || "").trim();
    if (!rawPath) throw new Error(body.mode === "adopt" ? "Choose RSDragonwildsServer.exe or RSDragonwildsServer.sh." : "Choose a dedicated-server installation folder.");

    if (body.mode === "adopt") {
      const check = detect.inspect(rawPath);
      if (!check.valid) throw new Error(check.reason || "That executable is not a usable Dragonwilds dedicated server.");
      dbm.setSetting(DIR_KEY, check.installDir);
      dbm.setSetting(PLATFORM_KEY, check.platform);
      // Existing Server profiles own their install folders. Relinking the
      // template must never redirect them into the shared SteamCMD tree.
      return NextResponse.json({ ok: true, adopted: true, server: current() });
    }

    const installDir = path.resolve(rawPath);
    const platform = body.platform === "linux" ? "linux" : "windows";
    fs.mkdirSync(installDir, { recursive: true });

    const active = jobs.listJobs().find((job) => job.status === "running" && job.worldName === "Application Setup · Server");
    if (active) return NextResponse.json({ ok: true, jobId: active.id, alreadyRunning: true });

    const jobId = jobs.createJob({ type: "install", worldId: null, worldName: "Application Setup · Server" });
    (async () => {
      const log = (line) => jobs.logJob(jobId, line);
      try {
        jobs.setPhase(jobId, "starting", "Preparing SteamCMD");
        jobs.setPhase(jobId, "steamcmd", "Installing/updating the shared Server Core…");
        const result = await forks.updateCore(installDir, platform, { onLog: log });
        const check = detect.inspect(installDir);
        if (!check.valid) throw new Error(check.reason || "Dedicated-server installation could not be verified.");
        dbm.setSetting(DIR_KEY, check.installDir);
        dbm.setSetting(PLATFORM_KEY, platform);
        jobs.setPhase(jobId, "copy", "Refreshing stopped RSDW Server profiles…");
        jobs.setProgress(jobId, 0, "RSDW: staging profile core files…");
        const refreshed = await forks.refreshStoppedProfiles(check.installDir, {
          onLog: log,
          onProgress: ({ worldName, completed, total, file }) => jobs.setProgress(jobId, Math.round(100 * completed / Math.max(1, total)), `RSDW: ${worldName} · ${completed}/${total} files · ${file}`),
        });
        log(`RSDW: ${refreshed.filter((item) => item.updated).length} profile(s) refreshed; ${refreshed.filter((item) => item.pending).length} running profile(s) pending; ${refreshed.filter((item) => item.error).length} need review.`);
        log(`Verified dedicated server: ${check.binary}`);
        log(`Installed build: ${check.buildId || result.buildId || "unknown"}`);
        jobs.finishJob(jobId, true, { installDir: check.installDir, buildId: check.buildId || result.buildId || null });
      } catch (e) {
        log(`ERROR: ${e.message}`);
        jobs.finishJob(jobId, false, { error: e.message });
      }
    })();

    return NextResponse.json({ ok: true, jobId });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
