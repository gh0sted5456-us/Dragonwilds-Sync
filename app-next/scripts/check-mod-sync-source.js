const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-mod-source-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");

const dbm = require("../lib/db");
const lanes = require("../lib/mod-lanes");
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

  lanes.setSelections(worldId, [{ key: mod.selectionKey, clientRequired: false }]);
  assert(fs.existsSync(path.join(server, "RSDragonwilds", "Content", "Paks", "~mods", "RequiredExample.pak")), "Required mod was not materialized into the server");
  const serverOnly = manifest.buildWorldManifest(worldId);
  assert(!serverOnly.units.some((unit) => unit.name === "RequiredExample"), "Server-only mod leaked into player Sync");

  lanes.setSelections(worldId, [{ key: mod.selectionKey, clientRequired: true }]);
  const published = manifest.buildWorldManifest(worldId);
  assert(published.units.some((unit) => unit.name === "RequiredExample" && unit.files.some((file) => file.target.endsWith("RequiredExample.pak"))), "Required mod was not published to player Sync");
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
