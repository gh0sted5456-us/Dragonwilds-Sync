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
  assert(main.includes("startupPortsPromise = Promise.all"), "port selection must overlap Electron initialization");
  assert(main.includes("utilityProcess.fork(serverPath"), "packaged interface must use Electron's Node utility process");
  assert(!main.includes("spawn(process.execPath, [serverPath]"), "packaged interface must not relaunch the portable GUI executable for server.js");
  assert(main.includes("waitForServer(base, 30000)"), "window navigation must wait for authenticated local readiness");
  assert(main.includes("if (!mainWindow || !serverReady) return"), "window must not navigate before the local server is ready");
  assert(!main.includes("DWSM-Data"), "portable EXE must not bind userData beside itself");
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
  contains("electron/main.js", "utilityProcess.fork(serverPath");
}

// Dedicated settings must be profile-scoped and launch materialization must exist.
{
  contains("lib/active-server-profile.js", 'const PROFILE_PREFIX = "serverProfileIni:"');
  contains("lib/active-server-profile.js", "function materialize(");
  contains("lib/active-server-profile.js", "function materializeActiveBestEffort(");
  const activeProfiles = contains("lib/active-server-profile.js", "function updateWorldFromSettings(");
  assert(activeProfiles.includes('["OwnerId", "owner_id"]'), "OwnerId is not persisted to the World profile");
  assert(activeProfiles.includes('["ServerName", "display_name"]'), "ServerName is not persisted to the World profile");
  assert(activeProfiles.includes('["DefaultWorldName", "default_world_name"]'), "DefaultWorldName is not persisted to the World profile");
  contains("lib/db.js", "owner_id=@owner_id, default_world_name=@default_world_name");
  const settingsRoute = contains("app/api/worlds/[id]/settings/route.js", "active.settingsFor(");
  assert(settingsRoute.includes("active.updateWorldFromSettings"), "Settings route must persist DB-owned fields before normalization");
  contains("app/api/worlds/[id]/ini/route.js", "active.saveRawSettings(");
  contains("app/api/worlds/[id]/ini/route.js", "active.updateWorldFromSettings(");

  const worldRoute = contains("app/api/worlds/[id]/route.js", "serverProfiles.settingsFor(updated)");
  assert(!worldRoute.includes("ini.applyWorldNetworkSettings(updated.install_dir"), "inactive profile edits still write directly into the live INI");
}

// UX contract: explicit Connect action, live Helpy, dark shell and update tracking.
{
  contains("app/page.jsx", "Connect to World");
  contains("app/info/page.jsx", "https://gh0sted5456-us.github.io/Dragonwilds-Sync/helpy.html?embed=1&theme=dark");
  contains("app/globals.css", "--accent: #c1a56d");
  const modsPanel = contains("components/ModsPanel.jsx", "Managed mods");
  assert(!/workshop/i.test(modsPanel), "Mods UI must not expose Steam Workshop controls");
  assert(modsPanel.includes("Required for players") && modsPanel.includes("Server only"), "managed mod client requirement controls missing");
  const lanes = contains("lib/mod-lanes.js", 'const LANES = ["server", "required", "steam", "gamepass"]');
  assert(lanes.includes("Required Player Mods") && lanes.includes("Steam Player") && lanes.includes("PC Game Pass Player"), "player mod lanes missing");
  assert(lanes.includes("function setRequiredSource"), "per-World required mod source is missing");
  contains("app/api/worlds/[id]/mods/source/route.js", "mods.setRequiredSource");
  contains("lib/component-updates.js", "latestNexusVersions");
  contains("lib/component-updates.js", "Xbox");
  contains("lib/component-updates.js", "Steam");
  contains("lib/runtime-packages.js", 'const COMPONENTS = new Set(["ue4ss-server", "ue4ss-steam", "ue4ss-gamepass", "runeschema"])');
  contains("lib/runtime-packages.js", 'component === "ue4ss-server" && filename === "dwmapi.dll"');
  contains("lib/runtime-packages.js", 'component !== "ue4ss-server" && filename === "version.dll"');
  contains("lib/runtime-packages.js", 'Dedicated-server UE4SS requires version.dll');
  contains("lib/runtime-packages.js", 'Steam UE4SS requires dwmapi.dll');
  contains("lib/runtime-packages.js", "function materializeHost(worldId)");
  contains("lib/supervisor.js", 'require("./runtime-packages").materializeHost(worldId)');
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
  contains("components/ModsPanel.jsx", "UE4SS · Dedicated Server");
  contains("components/ModsPanel.jsx", "UE4SS · Steam");
  contains("components/ModsPanel.jsx", "UE4SS · PC Game Pass");
  contains("components/ModsPanel.jsx", "server uses version.dll");
  contains("components/ModsPanel.jsx", "Steam uses dwmapi.dll");
  const worldPage = read("app/worlds/[id]/page.jsx");
  assert(!worldPage.includes("Ue4ssPanel"), "stale UE4SS-only panel must not remain mounted");
  assert(worldPage.includes("mountedTabs") && worldPage.includes("TabPanelBoundary"), "World tabs must retain and isolate visited panels");
  const shell = read("components/Shell.jsx");
  assert(!shell.includes('fetch("/api/component-updates")'), "desktop shell must not probe UE4SS/RuneSchema during GUI startup");
  contains("electron/main.js", "loadingPage(");
  contains("electron/main.js", "startShareServer()");
  contains("electron/main.js", 'path.join(__dirname, "share-proxy.js")');
  contains("electron/share-proxy.js", 'http.createServer');
  contains("electron/share-proxy.js", 'RSDW_UI_PORT');
  contains("electron/share-proxy.js", 'RSDW_SHARE_PORT');
  contains("electron/main.js", 'HOSTNAME: "127.0.0.1"');
  assert(!read("electron/main.js").includes('HOSTNAME: "0.0.0.0"'), "Main UI process must remain loopback-only");
  contains("electron/share-proxy.js", 'const listenHost = "0.0.0.0"');
  contains("electron/main.js", "APP_MANAGER_SHARE_PORT");
  contains("lib/sync/discovery.js", "APP_MANAGER_SHARE_PORT");
  contains("electron/main.js", '"icon.ico"');
  contains("package.json", '"icon": "public/icon.ico"');
  assert(JSON.parse(read("package.json")).build.compression !== "store", "portable build must compress the Electron runtime");
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


// Application Setup owns machine-level Server / Steam / Game Pass lanes.
// Profiles may select/use a lane but must not provision or cache independent installs.
{
  contains("app/setup/page.jsx", "Application Setup");
  contains("app/setup/page.jsx", "Dedicated Server lane");
  contains("app/setup/page.jsx", 'label="Steam"');
  contains("app/setup/page.jsx", 'label="PC Game Pass"');
  contains("app/setup/page.jsx", "<PlayLane");
  contains("app/api/application-setup/server/route.js", 'const DIR_KEY = "applicationSetup:serverDir"');
  contains("app/api/application-setup/play/route.js", "clientInstall:");
  const provisionRoute = read("app/api/provision/route.js");
  assert(provisionRoute.includes("World creation is profile-only"), "World creation must remain profile-only");
  assert(!provisionRoute.includes("installOrUpdate"), "World creation must not run SteamCMD");
  const createWorld = read("components/CreateWorldModal.jsx");
  assert(!createWorld.includes("installFolder"), "Server profile creation must not own an install folder");
  assert(createWorld.includes("Application Setup"), "Server profile creation must point to Application Setup");
  const syncClient = read("lib/sync/client.js");
  assert(syncClient.includes("clientInstall:${platform}"), "Client sync must resolve the application Play lane");
  assert(syncClient.includes("Promise.allSettled(workers)"), "Client sync must use bounded, settled parallel downloads");
  assert(syncClient.includes("sync-recovery"), "Client sync must retain recoverable receipts and prior files");
  assert(syncClient.includes('receipt.status = "rolled-back"'), "Client sync rollback path missing");
  assert(syncClient.indexOf("await mapLimit(comparison.changes") < syncClient.indexOf("await fs.promises.rm(item.local"), "Client sync must stage every download before replacing live files");
  const publicFileRoute = read("app/api/sync/public/[id]/file/route.js");
  assert(publicFileRoute.includes("fs.createReadStream(file.source)"), "Host file delivery must stream instead of buffering whole mods in memory");
  const verifyRoute = read("app/api/profiles/[id]/verify/route.js");
  assert(verifyRoute.includes("clientInstall:${platform}"), "Profile verify must resolve the application Play lane");
  assert(!fs.existsSync(path.join(root, "app", "api", "provision", "status", "route.js")), "obsolete per-World provision status API must stay deleted");

  const setupPage = read("app/setup/page.jsx");
  assert(setupPage.includes('useState("play")'), "Application Setup must open on Play by default");
  assert(!setupPage.includes('useState(typeof window'), "Application Setup must not derive initial state from window during SSR");
  const settingsPage = read("app/settings/page.jsx");
  assert(settingsPage.includes("window.desktop?.[method]") && settingsPage.includes('typeof fn === "function"'), "Settings must guard optional desktop bridges");
  assert(!settingsPage.includes("loadComponentUpdates(false);\n    if (isElectron)"), "Settings must not probe framework updates just by mounting");

}

function walkSource(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkSource(full));
    else if (/\.(js|jsx)$/.test(entry.name)) out.push(full);
  }
  return out;
}

// Deleted legacy modules must have zero live imports anywhere in app-next.
{
  const legacyRefs = ["@/lib/bootstrap", "@/lib/ue4ss", "Ue4ssPanel"];
  for (const file of [
    ...walkSource(path.join(root, "app")),
    ...walkSource(path.join(root, "components")),
    ...walkSource(path.join(root, "lib")),
  ]) {
    const source = fs.readFileSync(file, "utf8");
    for (const needle of legacyRefs) {
      assert(!source.includes(needle), `${path.relative(root, file)} still references deleted legacy module ${needle}`);
    }
  }
}

console.log("RSDW revamp contract: OK");
