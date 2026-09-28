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

// Desktop startup must be GUI-only. Background/server engines begin only from
// explicit feature actions, never because Electron opened or the Worlds list loaded.
{
  const main = read("electron/main.js");
  assert(!main.includes("triggerBoot("), "desktop startup must not trigger background engines");
  assert(!main.includes("/api/boot"), "desktop startup must not call a boot endpoint");
  const worldsRoute = read("app/api/worlds/route.js");
  assert(!worldsRoute.includes("boot()"), "listing Worlds must remain observational");
  assert(!fs.existsSync(path.join(root, "lib", "bootstrap.js")), "obsolete bootstrap engine must stay deleted");
  assert(!fs.existsSync(path.join(root, "app", "api", "boot", "route.js")), "obsolete boot API must stay deleted");
  assert(!fs.existsSync(path.join(root, "lib", "ue4ss.js")), "legacy Palworld UE4SS manager must stay deleted");
  assert(!fs.existsSync(path.join(root, "components", "Ue4ssPanel.jsx")), "legacy UE4SS panel must stay deleted");

  const supervisor = contains("lib/supervisor.js", "owned: new Set()", "supervisor ownership registry missing");
  assert(!supervisor.includes("spawnOpts.detached"), "Server subprocess must not be detached");
  assert(supervisor.includes("spawn(bin, args, spawnOpts)"), "Server must launch as an explicit subprocess");
  assert(supervisor.includes("stopManagedWorlds"), "owned subprocess shutdown path missing");
  assert(supervisor.includes("3 restart attempts in 10 minutes"), "crash-loop guard missing");
  contains("lib/steamcmd.js", "spawn(bin, args");
  contains("electron/main.js", "spawn(process.execPath, [serverPath]");
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
  contains("app/globals.css", "--accent: #c1a56d");
  const modsPanel = contains("components/ModsPanel.jsx", "Install lanes");
  assert(!/workshop/i.test(modsPanel), "Mods UI must not expose Steam Workshop controls");
  const lanes = contains("lib/mod-lanes.js", 'const LANES = ["server", "steam", "gamepass"]');
  assert(lanes.includes("Steam Player") && lanes.includes("PC Game Pass Player"), "player mod lanes missing");
  contains("lib/component-updates.js", "latestNexusVersions");
  contains("lib/component-updates.js", "Xbox");
  contains("lib/component-updates.js", "Steam");
  contains("lib/runtime-packages.js", 'const COMPONENTS = new Set(["ue4ss-steam", "ue4ss-gamepass", "runeschema"])');
  contains("lib/runtime-packages.js", 'component === "ue4ss-gamepass" ? "WinGDK" : "Win64"');
  contains("lib/runtime-packages.js", 'clientEligible');
  contains("lib/sync/client.js", '"X-RSDW-Client-Platform"');
  contains("lib/sync/manifest.js", "iconData: world.icon_data || null");
  contains("lib/sync/manifest.js", "bannerData: world.banner_data || null");
  contains("app/page.jsx", "Send to Desktop");
  contains("app/page.jsx", "worldIdentity");
  contains("app/profiles/[id]/player/page.jsx", 'searchParams.get("autoplay") === "1"');
  contains("app/profiles/[id]/player/page.jsx", "Confirm &amp; Launch Dragonwilds");
  contains("app/profiles/[id]/player/page.jsx", "World Name");
  contains("app/profiles/[id]/player/page.jsx", "IP Address");
  contains("app/profiles/[id]/player/page.jsx", "World Password");
  contains("app/profiles/[id]/player/page.jsx", "World Type");
  contains("app/profiles/[id]/player/page.jsx", "navigator.clipboard.writeText");
  contains("electron/main.js", '" --autoplay"');
  contains("electron/main.js", "writeShortcutIcon");
  contains("components/ModsPanel.jsx", "UE4SS · Steam/server");
  contains("components/ModsPanel.jsx", "UE4SS · PC Game Pass");
  contains("components/ModsPanel.jsx", "Routed to Win64 or WinGDK automatically");
  const worldPage = read("app/worlds/[id]/page.jsx");
  assert(!worldPage.includes("Ue4ssPanel"), "stale UE4SS-only panel must not remain mounted");
  const shell = read("components/Shell.jsx");
  assert(!shell.includes('fetch("/api/component-updates")'), "desktop shell must not probe UE4SS/RuneSchema during GUI startup");
  contains("electron/main.js", '"icon.png"');
  contains("package.json", '"icon": "public/icon.png"');
  contains("app/globals.css", "--radius: 12px");
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
