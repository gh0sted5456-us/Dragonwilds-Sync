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
  assert(!fs.existsSync(path.join(root, "app", "language-packs", "page.jsx")), "language-pack page must stay deleted");
  assert(!fs.existsSync(path.join(root, "app", "api", "i18n", "languages", "route.js")), "language-pack APIs must stay deleted");
  assert(!fs.existsSync(path.join(root, "registry", "index.json")), "language-pack registry must stay deleted");
  assert(!fs.existsSync(path.join(root, "lib", "i18n", "client.js")), "runtime language switching must stay deleted");

  const supervisor = contains("lib/supervisor.js", "owned: new Set()", "supervisor ownership registry missing");
  assert(!supervisor.includes("spawnOpts.detached"), "Server subprocess must not be detached");
  assert(supervisor.includes("spawn(bin, args, spawnOpts)"), "Server must launch as an explicit subprocess");
  assert(supervisor.includes("stopManagedWorlds"), "owned subprocess shutdown path missing");
  assert(supervisor.includes("3 restart attempts in 10 minutes"), "crash-loop guard missing");
  assert(!supervisor.includes("-publiclobby"), "Palworld public-lobby launch flag must stay removed");
  assert(!supervisor.includes("-useperfthreads") && !supervisor.includes("-NoAsyncLoadingThread") && !supervisor.includes("-UseMultithreadForDS"), "Palworld legacy performance flags must stay removed");
  assert(supervisor.includes('if (!graceful) killTreeNow();'), "manual stop must immediately kill the server process tree");
  const actionRoute = read("app/api/worlds/[id]/action/route.js");
  assert(
    actionRoute.includes('action === "stop"') && actionRoute.includes('{ graceful: false }'),
    "primary Stop action must be immediate",
  );
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
  assert(modsPanel.includes('["client", "server", "both"]'), "managed mod Client / Server / Both controls missing");
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
  assert(!worldPage.includes("mountedTabs"), "inactive world tabs must be unmounted to avoid overlapping requests and stale effects");
  assert(worldPage.includes("TabPanelBoundary"), "active world tabs must remain isolated by an error boundary");
  assert(worldPage.includes('<TabSlot key="overview"') && worldPage.includes('<TabSlot key="admin"'), "World tabs must use distinct keys so failed panels cannot leak error state");
  contains("components/ApplicationBoundary.jsx", "Application view failed");
  contains("app/error.js", "Retry page");
  assert(!worldPage.includes("MapPanel") && !worldPage.includes('id: "broadcasts"'), "removed map and broadcast tabs must not return");
  const shell = read("components/Shell.jsx");
  assert(shell.includes('setTimeout(loadUpdates, 4000)'), "deferred game/framework update notification monitor missing");
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
  contains("electron/main.js", 'path.join(base, "icon.png")');
  contains("package.json", '"icon": "public/icon.ico"');
  contains("package.json", '"signAndEditExecutable": false');
  contains("components/Shell.jsx", 'className="app-watermark"');
  contains("components/Shell.jsx", '/rsdw/app-icon.webp');
  contains("components/ModsPanel.jsx", '/rsdw/platforms/runeschema.png');
  contains("app/page.jsx", '/rsdw/dragonwilds-wordmark.png');
  assert(fs.existsSync(path.join(root, "public", "rsdw", "platforms", "runeschema.png")), "RuneSchema logo asset missing");
  assert(fs.existsSync(path.join(root, "public", "rsdw", "dragonwilds-mark.png")), "Dragonwilds mark missing");
  assert(fs.existsSync(path.join(root, "public", "rsdw", "dragonwilds-wordmark.png")), "Dragonwilds wordmark missing");
  assert(JSON.parse(read("package.json")).build.compression !== "store", "portable build must compress the Electron runtime");
  contains("app/globals.css", "--radius: 12px");
}

// World replacement must use Dragonwilds' flat SaveGames layout without erasing
// server configuration or allowing an ambiguous newest-save choice.
{
  const provision = contains("lib/provision.js", "function validateSaveSource(");
  assert(provision.includes('saves.length !== 1'), "save ZIP must contain exactly one .sav");
  assert(provision.includes('"Saved", "SaveGames"'), "world import must target only Saved/SaveGames");
  assert(!provision.includes('path.join(world.install_dir, "RSDragonwilds", "Saved");'), "world import must not replace the entire Saved directory");
  assert(provision.includes("createBackup(worldId, \"pre-import-safety\")"), "world import safety backup missing");
  assert(provision.includes("isAlive(worldId)"), "world import persisted-process guard missing");
  assert(provision.includes("function listSaveSlots("), "reusable world save slots missing");
  assert(provision.includes("function activateSaveSlot("), "offline world save activation missing");
  contains("app/api/worlds/[id]/save-slots/route.js", "provision.activateSaveSlot");
  contains("electron/preload.js", "pickWorldSave");
  contains("electron/main.js", 'ipcMain.handle("pick-world-save"');
  contains("components/BackupsPanel.jsx", "check.activeSave");
}

// Packaged builds identify their Git branch/commit so stable and experimental
// channels can independently report when GitHub has a newer build.
{
  contains("lib/appversion.js", 'stable: "main"');
  contains("lib/appversion.js", 'experimental: "codex/super-experimental"');
  contains("scripts/prepare-standalone.js", '"build-info.json"');
}

// Desktop autostart is opt-in and owned Servers receive a graceful quit request.
{
  const main = contains("electron/main.js", "requestManagedServerShutdown");
  assert(main.includes("enabled = false;"), "desktop autostart must default off");
  assert(main.includes('path: "/api/app/shutdown"'), "desktop shutdown bridge missing");
  const admin = read("components/AdminPanel.jsx");
  assert(!admin.includes("setAutostart"), "Server profile UI still exposes an automatic launch switch");
  assert(!admin.includes("community_server") && !admin.includes("legacy_perf_flags"), "Palworld-only profile controls must stay removed");
  assert(!read("app/page.jsx").includes("community_server"), "Palworld public/private badge must stay removed");
}


// Application Setup owns machine-level Server / Steam / Game Pass lanes.
// Profiles may select/use a lane but must not provision or cache independent installs.
{
  contains("app/setup/page.jsx", "Application Setup");
  contains("app/setup/page.jsx", "SteamCMD · Dedicated Server");
  contains("app/setup/page.jsx", 'label="Steam"');
  contains("app/setup/page.jsx", 'label="PC Game Pass"');
  contains("app/setup/page.jsx", "<PlayLane");
  assert(!read("app/setup/page.jsx").includes("useEffect(load"), "React effects must not return API promises during tab unmount");
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
  assert(setupPage.includes('useState("server")'), "Application Setup must open on SteamCMD Server setup by default");
  assert(!setupPage.includes('useState(typeof window'), "Application Setup must not derive initial state from window during SSR");
  const settingsPage = read("app/settings/page.jsx");
  assert(settingsPage.includes("window.desktop?.[method]") && settingsPage.includes('typeof fn === "function"'), "Settings must guard optional desktop bridges");
  assert(!settingsPage.includes("loadComponentUpdates(false);\n    if (isElectron)"), "Settings must not probe framework updates just by mounting");
  assert(setupPage.includes("pickServerExecutable"), "Application Setup must allow selecting an existing server executable");
  assert(setupPage.includes("defaultShowLog"), "Application Setup must show the complete SteamCMD log inline");
  const setupRoute = read("app/api/application-setup/server/route.js");
  assert(setupRoute.includes('body.mode === "adopt"'), "existing server executable adoption route missing");
  assert(!setupRoute.includes("job.id"), "SteamCMD setup job still writes logs to an undefined job id");
  const updates = read("lib/component-updates.js");
  assert(updates.includes("dragonwilds-server") && updates.includes("dragonwilds-steam-client") && updates.includes("dragonwilds-gamepass-client"), "game/server version notifications are incomplete");

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
