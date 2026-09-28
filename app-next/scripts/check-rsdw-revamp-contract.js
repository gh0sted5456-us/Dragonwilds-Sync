const fs = require("fs");
const path = require("path");
const assert = require("assert");
const ini = require("../lib/ini");

const root = path.resolve(__dirname, "..");
const read = (rel) => fs.readFileSync(path.join(root, rel), "utf8");

function contains(rel, needle, message) {
  const source = read(rel);
  assert(source.includes(needle), message || `${rel} missing ${needle}`);
  return source;
}

// Profile-safe INI patching must preserve unrelated text while updating values.
{
  const raw = [
    "[/Script/Dominion.DedicatedServerSettings]",
    "; keep this comment",
    "PublicPort=9999",
    "CustomThing=\"leave me alone\"",
    "",
  ].join("\r\n");
  const patched = ini.patchRawSettings(raw, {
    PublicPort: "7777",
    WorldPassword: "two words",
  });
  assert(patched.includes("; keep this comment"), "INI comments were discarded");
  assert(patched.includes('CustomThing="leave me alone"'), "Unknown INI settings were discarded");
  assert(patched.includes("PublicPort=7777"), "Managed INI value was not patched");
  assert(patched.includes('WorldPassword="two words"'), "New INI value was not appended/quoted");
}

// Server startup must be explicit; the app only owns processes it launches.
{
  const bootstrap = read("lib/bootstrap.js");
  assert(!bootstrap.includes("sup.startWorld("), "bootstrap must not implicitly launch a Server");
  const supervisor = contains("lib/supervisor.js", "owned: new Set()", "supervisor ownership registry missing");
  assert(!supervisor.includes("spawnOpts.detached"), "Server subprocess must not be detached");
  assert(supervisor.includes("stopManagedWorlds"), "owned subprocess shutdown path missing");
  assert(supervisor.includes("3 restart attempts in 10 minutes"), "crash-loop guard missing");
}

// Dedicated settings must be profile-scoped and launch materialization must exist.
{
  contains("lib/active-server-profile.js", 'const PROFILE_PREFIX = "serverProfileIni:"');
  contains("lib/active-server-profile.js", "function materialize(");
  const settingsRoute = contains("app/api/worlds/[id]/settings/route.js", "active.settingsFor(");
  assert(settingsRoute.includes("worldUpdates.owner_id"), "OwnerId is not persisted to the World profile");
  assert(settingsRoute.includes("worldUpdates.display_name"), "ServerName is not persisted to the World profile");
  assert(settingsRoute.includes("worldUpdates.default_world_name"), "DefaultWorldName is not persisted to the World profile");
  contains("app/api/worlds/[id]/ini/route.js", "active.saveRawSettings(");

  const worldRoute = contains("app/api/worlds/[id]/route.js", "serverProfiles.settingsFor(updated)");
  assert(!worldRoute.includes("ini.applyWorldNetworkSettings(updated.install_dir"), "inactive profile edits still write directly into the live INI");
}

// UX contract: explicit Connect action, live Helpy, dark shell and update tracking.
{
  contains("app/page.jsx", "Connect to World");
  contains("app/info/page.jsx", "/api/helpy/helpy.html?embed=1&theme=dark");
  contains("app/globals.css", "--accent: #a9823f");
  const modsPanel = contains("components/ModsPanel.jsx", "Install lanes");
  assert(!/workshop/i.test(modsPanel), "Mods UI must not expose Steam Workshop controls");
  const lanes = contains("lib/mod-lanes.js", 'const LANES = ["server", "steam", "gamepass"]');
  assert(lanes.includes("Steam Player") && lanes.includes("PC Game Pass Player"), "player mod lanes missing");
  contains("lib/component-updates.js", "latestNexusVersions");
  contains("lib/component-updates.js", "Xbox");
  contains("lib/component-updates.js", "Steam");
}

// Desktop autostart is opt-in and owned Servers receive a graceful quit request.
{
  const main = contains("electron/main.js", "requestManagedServerShutdown");
  assert(main.includes("enabled = false;"), "desktop autostart must default off");
  assert(main.includes('path: "/api/app/shutdown"'), "desktop shutdown bridge missing");
  const admin = read("components/AdminPanel.jsx");
  assert(!admin.includes("setAutostart"), "Server profile UI still exposes an automatic launch switch");
}

console.log("RSDW revamp contract: OK");
