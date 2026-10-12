import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const sup = require("@/lib/supervisor");
const steam = require("@/lib/steamcmd");
const ra = require("@/lib/remoteauth");
const runtimePackages = require("@/lib/runtime-packages");
const modLanes = require("@/lib/mod-lanes");
const scheduler = require("@/lib/scheduler");
const cloudStorage = require("@/lib/sync/cloud-storage");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Back-fill a missing build id from the on-disk Steam manifest so worlds that
// were adopted (or missed capture at install time) still show their build.
function ensureBuildId(w) {
  if (w.build_id) return w;
  try {
    const bid = steam.readInstalledBuildId(w.install_dir);
    if (bid) {
      dbm.updateWorld(w.world_id, { build_id: bid });
      return { ...w, build_id: bid };
    }
  } catch {}
  return w;
}

function profileBadges(world) {
  let runtime = {};
  let selections = [];
  try { runtime = runtimePackages.status(world.world_id); } catch {}
  try { selections = modLanes.readSelections(world.world_id); } catch {}
  const keys = selections.map((item) => String(item.key || "").toLowerCase());
  const has = (value) => keys.some((key) => key.includes(value));
  const platforms = [];
  if (runtime.ue4ssSteam?.installed || keys.some((key) => key.startsWith("steam|"))) platforms.push("STEAM CLIENT");
  if (runtime.ue4ssGamepass?.installed || keys.some((key) => key.startsWith("gamepass|"))) platforms.push("GAME PASS CLIENT");
  const loaders = [];
  if (runtime.ue4ssServer?.installed || runtime.ue4ssSteam?.installed || runtime.ue4ssGamepass?.installed || has("ue4ss")) loaders.push("UE4SS");
  if (runtime.runeschema?.installed || has("runeschema")) loaders.push("RUNESCHEMA");
  if (has("pak")) loaders.push("PAK MODS");
  let distribution = {};
  try { distribution = cloudStorage.publicStatus(world.world_id); } catch {}
  const hosting = distribution.hostType === "managed" ? "MANAGED HOST" : distribution.hostType === "remote" ? "REMOTE / VPS" : "THIS COMPUTER";
  const delivery = distribution.mode === "cloud" ? `${String(distribution.providerLabel || "CLOUD").toUpperCase()} DELIVERY` : distribution.mode === "hybrid" ? "HYBRID DELIVERY" : "DIRECT DELIVERY";
  return {
    host: world.platform === "windows" ? "WINDOWS SERVER" : "LINUX SERVER",
    hosting,
    delivery,
    platforms: platforms.length ? platforms : ["VANILLA CLIENTS"],
    loaders,
  };
}

export async function GET(req) {
  const gate = ra.authorize(req, {});
  if (!gate.ok) return NextResponse.json({ ok: false, error: gate.reason }, { status: gate.status });
  // Player-only installs never start the dedicated-server scheduler. Remote guests
  // retain access to explicitly shared server records when the host has remote access on.
  const serverModeEnabled = !gate.admin || dbm.getSetting("serverModeEnabled", false) === true;
  if (serverModeEnabled) scheduler.ensureScheduler();
  let worlds = dbm.listWorlds().map(ensureBuildId);
  if (gate.admin) {
    if (!serverModeEnabled) worlds = [];
    else {
      const allowed = new Set(dbm.listLauncherProfileWorldIds(dbm.getActiveLauncherProfileId(), "server"));
      worlds = worlds.filter((world) => allowed.has(world.world_id));
    }
  }
  // A per-world code only ever sees its own world in the list.
  if (!gate.admin && gate.code && gate.code.scope === "world") {
    worlds = worlds.filter((w) => w.world_id === gate.code.world_id);
  }
  const enriched = worlds.map((w) => {
      const running = sup.isRunning(w.world_id) || sup.pidAlive(w.process_id);
      const updateState = steam.updateStateOf(w);
      return { ...w, running, apiUp: false, live: null, profileBadges: profileBadges(w), updateState, updateAvailable: updateState === "available" };
    });
  return NextResponse.json({ ok: true, worlds: enriched });
}
