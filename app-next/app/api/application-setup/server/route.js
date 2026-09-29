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
  };
}

export async function GET() {
  return NextResponse.json({ ok: true, server: current() });
}

export async function POST(req) {
  try {
    const body = await req.json();
    const installDir = path.resolve(String(body.installDir || "").trim());
    if (!installDir) throw new Error("Choose a dedicated-server installation folder.");
    const platform = body.platform === "linux" ? "linux" : "windows";
    fs.mkdirSync(installDir, { recursive: true });

    const job = jobs.createJob({ type: "install", worldId: null, worldName: "Application Setup · Server" });
    (async () => {
      const log = (line) => jobs.logJob(job.id, line);
      try {
        jobs.setPhase(job.id, "starting", "Preparing dedicated server");
        await steam.ensureSteamCmd(log);
        jobs.setPhase(job.id, "steamcmd", "Installing Dragonwilds dedicated server…");
        const result = await steam.installOrUpdate(installDir, log, platform);
        if (!result.ok) throw new Error(`SteamCMD failed (code ${result.code})${result.detail ? `: ${result.detail}` : ""}`);
        const check = detect.inspect(installDir);
        if (!check.valid) throw new Error(check.reason || "Dedicated-server installation could not be verified.");
        dbm.setSetting(DIR_KEY, check.installDir);
        dbm.setSetting(PLATFORM_KEY, platform);
        jobs.finishJob(job.id, true, { installDir: check.installDir, buildId: check.buildId || result.buildId || null });
      } catch (e) {
        log(`ERROR: ${e.message}`);
        jobs.finishJob(job.id, false, { error: e.message });
      }
    })();

    return NextResponse.json({ ok: true, jobId: job.id });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
