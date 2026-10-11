const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-mod-source-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");

const dbm = require("../lib/db");
const lanes = require("../lib/mod-lanes");
const steamlib = require("../lib/steamlibrary");
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
  fs.writeFileSync(path.join(pakFolder, "ID.txt"), "# Dragonwilds Sync ID v1\nSchema: DragonwildsSync.ID.v1\nModID: DwarfCannon\nName: Dwarf Cannon\nAuthor: Maxxfilth\nRuntimeRole: both\nHOTLOAD = NO\n");
  const ue4ssFolder = path.join(source, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "Mods", "ExampleUE4SS");
  const runeFolder = path.join(source, "RSDragonwilds", "Binaries", "Win64", "ue4ss", "Mods", "RuneSchema", "mods", "ExampleSchema");
  fs.mkdirSync(ue4ssFolder, { recursive: true }); fs.mkdirSync(runeFolder, { recursive: true });
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
  assert.equal(inventory.find((item) => item.modId === "UEExample")?.identity?.hotload, true, "UE4SS ID.txt was not read");
  assert.equal(inventory.find((item) => item.modId === "RuneExample")?.identity?.runtimeRole, "client", "RuneSchema ID.txt was not read");

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
