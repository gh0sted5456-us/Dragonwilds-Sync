import { NextResponse } from "next/server";
const fs = require("fs");
const path = require("path");
const os = require("os");
const dbm = require("@/lib/db");
const steam = require("@/lib/steamcmd");
const jobs = require("@/lib/jobs");
const detect = require("@/lib/detect");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DIR_KEY = "applicationSetup:serverDir";
const PLATFORM_KEY = "applicationSetup:serverPlatform";

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
    ready: !!(installDir && info?.valid),
    buildId: info?.buildId || null,
    binary: info?.binary || null,
    steamcmdInstalled: steam.steamcmdInstalled(),
    steamcmdPath: steam.steamcmdBinary(),
  };
}

export async function GET() {
  return NextResponse.json({ ok: true, server: current() });
}

export async function POST(req) {
  try {
    const body = await req.json();
    const rawPath = String(body.executablePath || body.installDir || "").trim();
    if (!rawPath) throw new Error(body.mode === "adopt" ? "Choose RSDragonwildsServer.exe or RSDragonwildsServer.sh." : "Choose a dedicated-server installation folder.");

    if (body.mode === "adopt") {
      const check = detect.inspect(rawPath);
      if (!check.valid) throw new Error(check.reason || "That executable is not a usable Dragonwilds dedicated server.");
      dbm.setSetting(DIR_KEY, check.installDir);
      dbm.setSetting(PLATFORM_KEY, check.platform);
      for (const world of dbm.listWorlds()) {
        dbm.updateWorld(world.world_id, { install_dir: check.installDir, platform: check.platform, build_id: check.buildId || world.build_id });
      }
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
        await steam.ensureSteamCmd(log);
        jobs.setPhase(jobId, "steamcmd", "Installing Dragonwilds dedicated server…");
        const result = await steam.installOrUpdate(installDir, log, platform);
        if (!result.ok) throw new Error(`SteamCMD failed (code ${result.code})${result.detail ? `: ${result.detail}` : ""}`);
        const check = detect.inspect(installDir);
        if (!check.valid) throw new Error(check.reason || "Dedicated-server installation could not be verified.");
        dbm.setSetting(DIR_KEY, check.installDir);
        dbm.setSetting(PLATFORM_KEY, platform);
        for (const world of dbm.listWorlds()) {
          dbm.updateWorld(world.world_id, { install_dir: check.installDir, platform });
        }
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
