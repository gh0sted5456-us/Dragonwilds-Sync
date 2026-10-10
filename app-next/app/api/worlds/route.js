import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const rest = require("@/lib/restclient");
const sup = require("@/lib/supervisor");
const steam = require("@/lib/steamcmd");
const ra = require("@/lib/remoteauth");
const runtimePackages = require("@/lib/runtime-packages");
const modLanes = require("@/lib/mod-lanes");
const scheduler = require("@/lib/scheduler");

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
  return {
    host: world.platform === "windows" ? "WINDOWS SERVER" : "LINUX SERVER",
    platforms: platforms.length ? platforms : ["VANILLA CLIENTS"],
    loaders,
  };
}

export async function GET(req) {
  const gate = ra.authorize(req, {});
  if (!gate.ok) return NextResponse.json({ ok: false, error: gate.reason }, { status: gate.status });
  // Start the lightweight update/schedule monitor only once the authenticated UI
  // actually opens the server list. Opted-in profiles may then update themselves.
  scheduler.ensureScheduler();
  let worlds = dbm.listWorlds().map(ensureBuildId);
  // A per-world code only ever sees its own world in the list.
  if (!gate.admin && gate.code && gate.code.scope === "world") {
    worlds = worlds.filter((w) => w.world_id === gate.code.world_id);
  }
  const enriched = await Promise.all(
    worlds.map(async (w) => {
      const running = sup.isRunning(w.world_id) || sup.pidAlive(w.process_id);
      let live = null, apiUp = false;
      if (running && w.rest_api_enabled) {
        try {
          const [metrics, players] = await Promise.all([
            rest.metrics(w).catch(() => null),
            rest.players(w).catch(() => null),
          ]);
          apiUp = !!(metrics || players);
          live = {
            uptime: metrics?.uptime ?? null,
            fps: metrics?.serverfps ?? metrics?.fps ?? null,
            days: metrics?.days ?? null,
            currentPlayers: players?.players?.length ?? metrics?.currentplayernum ?? 0,
            maxPlayers: metrics?.maxplayernum ?? null,
          };
        } catch {}
      }
      const updateState = steam.updateStateOf(w);
      return { ...w, running, apiUp, live, profileBadges: profileBadges(w), updateState, updateAvailable: updateState === "available" };
    })
  );
  return NextResponse.json({ ok: true, worlds: enriched });
}
