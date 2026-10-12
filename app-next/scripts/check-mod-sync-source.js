const assert = require("assert");
const fs = require("fs");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(path.resolve(__dirname, ".."), ".rsdw-mod-source-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");

const dbm = require("../lib/db");
const lanes = require("../lib/mod-lanes");
const steamlib = require("../lib/steamlibrary");
const providers = require("../lib/mod-providers");
const manifest = require("../lib/sync/manifest");
const syncAuth = require("../lib/sync/auth");

const makeInstall = (name) => {
  const root = path.join(sandbox, name);
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Binaries", "Win64"), { recursive: true });
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Content", "Paks", "~mods"), { recursive: true });
  return root;
};

try {
  const worldId = "required-mod-source-test";
  const server = makeInstall("server");
  const source = makeInstall("required-source");
  fs.writeFileSync(path.join(source, "RSDragonwilds", "Content", "Paks", "~mods", "RequiredExample.pak"), "required-mod", "utf8");
  const pakFolder = path.join(source, "RSDragonwilds", "Content", "Paks", "~mods", "DwarfCannon");
  fs.mkdirSync(pakFolder, { recursive: true });
  for (const extension of ["pak", "utoc", "ucas"]) fs.writeFileSync(path.join(pakFolder, `DwarfCannon.${extension}`), extension);
  fs.writeFileSync(path.join(pakFolder, "ID.txt"), "# RSDW Sync unified mod identity v2\nSchema: DragonwildsSync.ID.v2\nModID: DwarfCannon\nName: Dwarf Cannon\nAuthor: Maxxfilth\nVersion: 1.2.3\nProvider: nexus\nProjectURL: https://www.nexusmods.com/runescapedragonwilds/mods/123\nProjectID: 123\nFileID: 456\nRuntimeRole: both\nHOTLOAD = NO\n");
  const ue4ssFolder = path.join(source, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "Mods", "ExampleUE4SS");
  const runeFolder = path.join(source, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "Mods", "RuneSchema", "mods", "ExampleSchema");
  fs.mkdirSync(ue4ssFolder, { recursive: true }); fs.mkdirSync(runeFolder, { recursive: true });
  const ue4ssList = path.join(source, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "Mods", "mods.txt");
  const runeList = path.join(source, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "Mods", "RuneSchema", "runeschema.txt");
  fs.writeFileSync(ue4ssList, "; Keep custom entries and load order\r\nExampleUE4SS : 0\r\n\r\n; Built-in keybinds, do not move up!\r\nKeybinds : 1\r\n");
  fs.writeFileSync(runeList, "# RuneSchema addon list\nExampleSchema : 1\n");
  fs.writeFileSync(path.join(ue4ssFolder, "enabled.txt"), "");
  fs.writeFileSync(path.join(ue4ssFolder, "ID.txt"), "ModID: UEExample\nName: UE Example\nRuntimeRole: server\nHOTLOAD=YES\n");
  fs.writeFileSync(path.join(runeFolder, "ID.txt"), "ModID: RuneExample\nName: Rune Example\nRuntimeRole: client\nHOTLOAD=NO\n");
  fs.writeFileSync(path.join(ue4ssFolder, "config.json"), '{"enabled":true}\n');
  fs.writeFileSync(path.join(ue4ssFolder, "settings.jsonc"), '{\n  // editable comments\n  "speed": 1\n}\n');
  fs.writeFileSync(path.join(ue4ssFolder, "main.lua"), "return { enabled = true }\n");

  dbm.insertWorld({
    world_id: worldId,
    display_name: "Required Mod Source",
    install_dir: server,
    platform: "windows",
    env_vars: "{}",
    wine_binary: "wine",
    wine_prefix: null,
    wine_launch_flags: "",
    game_port: 7777,
    query_port: 27015,
    rest_api_port: 7778,
    rcon_port: 25575,
    admin_password: "admin",
    server_password: "friends",
    rest_api_enabled: 1,
    owner_id: "owner",
    default_world_name: "Required Mod World",
    status: "stopped",
    autostart: 0,
    crash_guard: 1,
    build_id: null,
    extra_args: "",
    created_at: Date.now(),
  });
  dbm.updateWorld(worldId, { server_password: "friends" });

  const routed = lanes.setRequiredSource(worldId, source);
  const required = routed.modLanes.find((lane) => lane.id === "required");
  assert(required?.ready, "Required Player Mods source was not routed");
  const mod = required.mods.find((item) => item.name === "RequiredExample");
  assert(mod?.syncEligible, "Required PAK was not detected");
  const inventory = steamlib.scanGameMods(source).mods;
  const identifiedPak = inventory.find((item) => item.modId === "DwarfCannon");
  assert.equal(identifiedPak?.name, "Dwarf Cannon", "PAK ID.txt was not read");
  assert.equal(identifiedPak?.identity?.author, "Maxxfilth", "PAK author was not read");
  assert.equal(identifiedPak?.identity?.version, "1.2.3", "Unified installed version was not read");
  assert.equal(identifiedPak?.identity?.provider, "nexus", "Unified provider was not read");
  assert.equal(identifiedPak?.identity?.projectId, "123", "Unified project id was not read");
  assert.equal(identifiedPak?.identity?.fileId, "456", "Unified file id was not read");
  assert.equal(providers.normalizeProvider(identifiedPak.identity), "nexus", "Nexus provider was not normalized");
  assert(providers.compareVersions("1.2.3", "1.3.0") < 0, "Version comparison did not identify an update");
  assert.equal(inventory.find((item) => item.modId === "UEExample")?.identity?.hotload, true, "UE4SS ID.txt was not read");
  assert.equal(inventory.find((item) => item.modId === "RuneExample")?.identity?.runtimeRole, "client", "RuneSchema ID.txt was not read");
  const ue4ssMod = required.mods.find((item) => item.folderName === "ExampleUE4SS");
  const runeMod = required.mods.find((item) => item.folderName === "ExampleSchema");
  const runeFramework = required.mods.find((item) => item.type === "framework" && item.folderName === "RuneSchema");
  assert.equal(ue4ssMod?.loaderEnabled, true, "UE4SS enabled.txt marker was not detected");
  assert.equal(runeMod?.loaderEnabled, true, "RuneSchema list state was not detected");
  lanes.setLoaderEnabled(worldId, "required", ue4ssMod.selectionKey, false);
  assert.equal(fs.existsSync(path.join(ue4ssFolder, "enabled.txt")), false, "UE4SS marker still bypasses the disabled list entry");
  assert(fs.existsSync(path.join(ue4ssFolder, "enabled.txt.rsdw-disabled")), "UE4SS marker was not preserved for re-enabling");
  assert.match(fs.readFileSync(ue4ssList, "utf8"), /ExampleUE4SS : 0/);
  assert.match(fs.readFileSync(ue4ssList, "utf8"), /; Built-in keybinds, do not move up!\r\nKeybinds : 1/);
  lanes.setLoaderEnabled(worldId, "required", ue4ssMod.selectionKey, true);
  assert(fs.existsSync(path.join(ue4ssFolder, "enabled.txt")), "UE4SS marker was not restored");
  assert.match(fs.readFileSync(ue4ssList, "utf8"), /ExampleUE4SS : 1/);
  lanes.setLoaderEnabled(worldId, "required", runeMod.selectionKey, false);
  assert.match(fs.readFileSync(runeList, "utf8"), /ExampleSchema : 0/);
  lanes.setLoaderEnabled(worldId, "required", runeMod.selectionKey, true);
  assert.match(fs.readFileSync(runeList, "utf8"), /ExampleSchema : 1/);
  lanes.setLoaderEnabled(worldId, "required", runeFramework.selectionKey, true);
  assert.match(fs.readFileSync(ue4ssList, "utf8"), /RuneSchema : 1\r\n(?:\r\n)?; Built-in keybinds/, "RuneSchema framework was not inserted before UE4SS keybinds");
  assert.throws(() => lanes.setLoaderEnabled(worldId, "required", mod.selectionKey, true), /not a detected loader-managed mod/, "PAK was accepted as a loader-controlled mod");

  lanes.setSelections(worldId, [{ key: ue4ssMod.selectionKey, scope: "both" }]);
  const serverUe4ssList = path.join(server, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "Mods", "mods.txt");
  assert.match(fs.readFileSync(serverUe4ssList, "utf8"), /ExampleUE4SS : 1/, "Managed UE4SS state was not applied to the server");
  lanes.setLoaderEnabled(worldId, "required", ue4ssMod.selectionKey, false);
  assert.match(fs.readFileSync(serverUe4ssList, "utf8"), /ExampleUE4SS : 0/, "UE4SS disable was not applied to the server copy");
  assert(!manifest.buildWorldManifest(worldId).units.some((unit) => unit.name === "UE Example"), "Disabled UE4SS mod was published to player Sync");
  lanes.setLoaderEnabled(worldId, "required", ue4ssMod.selectionKey, true);
  assert(manifest.buildWorldManifest(worldId).units.some((unit) => unit.name === "UE Example"), "Enabled UE4SS mod was not published to player Sync");
  lanes.setSelections(worldId, [{ key: runeMod.selectionKey, scope: "both" }]);
  const serverRuneList = path.join(server, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "Mods", "RuneSchema", "runeschema.txt");
  assert.match(fs.readFileSync(serverRuneList, "utf8"), /ExampleSchema : 1/, "Managed RuneSchema state was not applied to the server");
  lanes.setLoaderEnabled(worldId, "required", runeMod.selectionKey, false);
  assert.match(fs.readFileSync(serverRuneList, "utf8"), /ExampleSchema : 0/, "RuneSchema disable was not applied to the server copy");
  assert(!manifest.buildWorldManifest(worldId).units.some((unit) => unit.name === "Rune Example"), "Disabled RuneSchema mod was published to player Sync");
  lanes.setLoaderEnabled(worldId, "required", runeMod.selectionKey, true);
  lanes.setLoaderEnabled(worldId, "required", runeFramework.selectionKey, false);
  assert(lanes.status(worldId).modLanes.find((item) => item.id === "required").mods.find((item) => item.selectionKey === runeMod.selectionKey).loaderBlockedByFramework, "Disabled RuneSchema framework was not reflected on its addons");
  assert(!manifest.buildWorldManifest(worldId).units.some((unit) => unit.name === "Rune Example"), "RuneSchema addon was published while its framework was disabled");
  lanes.setLoaderEnabled(worldId, "required", runeFramework.selectionKey, true);

  const editorFolder = "RSDragonwilds/Binaries/Win64/ue4ss/Mods/ExampleUE4SS";
  const editorBrowser = lanes.browse(worldId, "required", editorFolder);
  assert.deepEqual(editorBrowser.files.map((file) => file.name).sort(), ["config.json", "main.lua", "settings.jsonc"], "Editable mod files were not exposed by the explorer");
  assert(editorBrowser.files.every((file) => file.hotload), "HOTLOAD identity did not reach editable files");
  const luaFile = lanes.readEditableFile(worldId, "required", `${editorFolder}/main.lua`);
  assert.equal(luaFile.language, "lua");
  const savedLua = lanes.writeEditableFile(worldId, "required", luaFile.relative, "return { enabled = false }\n", luaFile.etag);
  assert(savedLua.content.includes("false"), "Lua edit was not saved");
  assert.throws(() => lanes.writeEditableFile(worldId, "required", luaFile.relative, "return {}\n", luaFile.etag), /changed on disk/, "Stale editor save was not rejected");
  const jsonFile = lanes.readEditableFile(worldId, "required", `${editorFolder}/config.json`);
  assert.throws(() => lanes.writeEditableFile(worldId, "required", jsonFile.relative, "{broken", jsonFile.etag), /JSON is not valid/, "Invalid JSON was accepted");

  lanes.setSelections(worldId, [{ key: mod.selectionKey, scope: "client" }]);
  assert(!fs.existsSync(path.join(server, "RSDragonwilds", "Content", "Paks", "~mods", "RequiredExample.pak")), "Client-only mod was copied to the server");
  assert(manifest.buildWorldManifest(worldId).units.some((unit) => unit.name === "RequiredExample"), "Client-only mod was not published to player Sync");

  lanes.setSelections(worldId, [{ key: mod.selectionKey, scope: "server" }]);
  assert(fs.existsSync(path.join(server, "RSDragonwilds", "Content", "Paks", "~mods", "RequiredExample.pak")), "Required mod was not materialized into the server");
  const serverOnly = manifest.buildWorldManifest(worldId);
  assert(!serverOnly.units.some((unit) => unit.name === "RequiredExample"), "Server-only mod leaked into player Sync");

  lanes.setSelections(worldId, [{ key: mod.selectionKey, scope: "both" }]);
  const published = manifest.buildWorldManifest(worldId);
  assert(published.units.some((unit) => unit.name === "RequiredExample" && unit.files.some((file) => file.target.endsWith("RequiredExample.pak"))), "Required mod was not published to player Sync");
  const runeRouted = lanes.setPakInstallMode(worldId, "runeschema");
  assert.equal(runeRouted.pakInstallMode, "runeschema");
  const runePak = path.join(server, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "Mods", "RuneSchema", "mods", "RequiredExample", "paks", "RequiredExample.pak");
  assert(fs.existsSync(runePak), "PAK was not moved into its RuneSchema paks folder");
  assert(!fs.existsSync(path.join(server, "RSDragonwilds", "Content", "Paks", "~mods", "RequiredExample.pak")), "Classic PAK copy remained after changing destination");
  assert(manifest.buildWorldManifest(worldId).units.some((unit) => unit.installMode === "runeschema" && unit.files.some((file) => file.target.includes("/RuneSchema/mods/RequiredExample/paks/"))), "RuneSchema PAK destination was not published in the manifest");
  const linked = manifest.withDownloadUrls(worldId, published, "http://127.0.0.1:4317/api/sync/public/required-mod-source-test");
  assert(linked.transport?.supportsDirectDownloads, "Manifest does not advertise direct downloads");
  assert(linked.units[0].files[0].downloadUrl.includes("token="), "Manifest file does not have a signed direct-download link");
  const linkedFile = linked.units[0].files[0];
  assert(syncAuth.authorizeWorldDownload(worldId, linkedFile, { url: linkedFile.downloadUrl, headers: new Headers() }).ok, "Signed direct-download link was rejected");
  const tampered = new URL(linkedFile.downloadUrl); tampered.searchParams.set("token", "0".repeat(64));
  assert(!syncAuth.authorizeWorldDownload(worldId, linkedFile, { url: tampered.toString(), headers: new Headers() }).ok, "Tampered direct-download link was accepted");

  const comparison = manifest.compareManifest(linked, source);
  assert(Array.isArray(comparison.units) && comparison.units[0].name === "RequiredExample", "Client comparison does not report per-mod units");

  console.log("Required mod source: OK");
} finally {
  try { dbm.db().close(); } catch {}
  fs.rmSync(sandbox, { recursive: true, force: true });
}
