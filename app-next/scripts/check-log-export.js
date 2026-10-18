const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const AdmZip = require("adm-zip");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-log-export-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
process.env.LOCALAPPDATA = path.join(sandbox, "local");
const dbm = require("../lib/db");
const { buildLogExport, readLogView, downloadHeaders } = require("../lib/log-export");
const { handleRequest } = require("../lib/log-api");
const write = (file, bytes) => { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, bytes); return file; };
const game = (name) => {
  const root = path.join(sandbox, name);
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Binaries", "Win64"), { recursive: true });
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Content"), { recursive: true });
  return root;
};
const nativeFile = (root, name = "RSDragonwilds.log") => path.join(root, "RSDragonwilds", "Saved", "Logs", name);
const ue4ssFile = (root, platform = "Win64") => path.join(root, "RSDragonwilds", "Binaries", platform, "ue4ss", "UE4SS.log");
const zipInfo = (result) => { const zip = new AdmZip(result.buffer); return { zip, info: JSON.parse(zip.readAsText("export-info.json")) }; };
const source = (file) => fs.readFileSync(path.join(__dirname, "..", file), "utf8");

(async () => {
  try {
    const install = game("server");
    const record = { world_id: "log-test", display_name: 'Test\r\n"World', install_dir: install, status: "running", admin_password: "PRIVATE_INI_SECRET" };
    const native = "Native startup\nLogEOSSDK: LogEOSAuth: account connection\nLogOnlineSubsystemRedpointEOS: session ready\nLogEOSP2P: peer connected\nUnrelated line\n<script>text only</script>\n";
    write(nativeFile(install), native);
    write(ue4ssFile(install), "UE4SS started\n");
    write(path.join(install, "RSDragonwilds", "Saved", "Config", "Server.ini"), "PRIVATE_INI_SECRET");
    write(path.join(install, "RSDragonwilds", "Saved", "SaveGames", "World.sav"), "PRIVATE_SAVE_SECRET");
    const result = await buildLogExport({ kind: "server", record });
    const { zip, info } = zipInfo(result);
    assert.equal(zip.readAsText("native/RSDragonwilds.log"), native);
    assert.equal(zip.readAsText("ue4ss/UE4SS.log"), "UE4SS started\n");
    assert.equal(info.eos.lines, 3);
    assert(zip.readAsText("eos/EOS.log").includes("LogEOSP2P"));
    assert(!zip.readAsText("eos/EOS.log").includes("Unrelated"));
    assert.deepEqual(info.missing, []);
    assert(!/[\r\n"/\\]/.test(result.filename));
    assert(zip.getEntries().every((entry) => !/\.(ini|sav)$/i.test(entry.entryName)));
    assert(!JSON.stringify(info).includes("PRIVATE_"));
    assert.equal(fs.readFileSync(nativeFile(install), "utf8"), native, "Export must not change live logs");
    assert.equal(downloadHeaders(result)["Cache-Control"], "no-store, private");
    const eos = await readLogView({ kind: "server", record });
    assert.equal(eos.lines.length, 3);
    assert(!eos.missing);
    const raw = await readLogView({ kind: "server", record, channel: "native" });
    assert(raw.lines.includes("<script>text only</script>"), "UI must render untrusted log lines as text");
    await assert.rejects(readLogView({ kind: "server", record, channel: "../../Server.ini" }), (error) => error.status === 400);

    // Unreal can use numbered active sessions even when the plain log remains.
    const numbered = write(nativeFile(install, "RSDragonwilds_2.log"), "LogEOSAuth: newer active session\n");
    const future = new Date(Date.now() + 10000);
    fs.utimesSync(numbered, future, future);
    assert(zipInfo(await buildLogExport({ kind: "server", record })).zip.getEntry("native/RSDragonwilds_2.log"));
    fs.unlinkSync(numbered);
    const backupRoot = game("backup");
    write(nativeFile(backupRoot, "RSDragonwilds-backup-2026.10.16.log"), "LogEOS: backup\n");
    const backupRecord = { ...record, world_id: "backup", install_dir: backupRoot };
    const backup = zipInfo(await buildLogExport({ kind: "server", record: backupRecord })).info;
    assert.deepEqual(backup.missing, ["ue4ss"]);
    assert(backup.warnings.some((item) => item.includes("backup")));
    assert((await readLogView({ kind: "server", record: backupRecord })).backup);

    const xbox = game("gamepass");
    write(ue4ssFile(xbox), "Wrong Steam loader");
    write(ue4ssFile(xbox, "WinGDK"), "Game Pass loader\n");
    const saveGames = path.join(sandbox, "custom-saves", "Saved", "SaveGames");
    write(path.join(saveGames, "..", "Logs", "RSDragonwilds.log"), "LogEOSConnect: local player\n");
    const player = { profile_id: "player", display_name: "Client", client_install: xbox, connection_json: JSON.stringify({ service: "gamepass", savePath: saveGames, password: "PRIVATE_CONNECTION_SECRET" }) };
    const playerZip = zipInfo(await buildLogExport({ kind: "player", record: player }));
    assert.equal(playerZip.zip.readAsText("ue4ss/UE4SS.log"), "Game Pass loader\n");
    assert(playerZip.info.note.includes("local client"));
    assert(!JSON.stringify(playerZip.info).includes("PRIVATE_CONNECTION_SECRET"));
    write(path.join(process.env.LOCALAPPDATA, "RSDragonwilds", "Saved", "Logs", "RSDragonwilds.log"), "LogEOS: app-local fallback\n");
    const localView = await readLogView({ kind: "player", record: { ...player, client_install: null, connection_json: "{}" } });
    assert.equal(localView.lines[0], "LogEOS: app-local fallback");

    const capped = zipInfo(await buildLogExport({ kind: "server", record, maxLogBytes: 32 }));
    assert.equal(capped.zip.readFile("native/RSDragonwilds.log").length, 32);
    assert.equal(capped.info.files[0].originalBytes, Buffer.byteLength(native));
    assert(capped.info.files[0].truncated);
    assert(capped.info.warnings.length);
    const unicodeRoot = game("unicode");
    write(nativeFile(unicodeRoot), Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from("Start\r\nLogEOSAuth: Unicode ✓\r\n", "utf16le")]));
    const unicode = { ...record, world_id: "unicode", install_dir: unicodeRoot };
    assert.equal((await readLogView({ kind: "server", record: unicode })).lines[0], "LogEOSAuth: Unicode ✓");
    const manyRoot = game("many");
    write(nativeFile(manyRoot), Array.from({ length: 12000 }, (_, index) => `LogEOS: message ${index}\n`).join(""));
    const many = { ...record, world_id: "many", install_dir: manyRoot };
    const recent = await readLogView({ kind: "server", record: many });
    assert.equal(recent.lines.length, 800);
    assert.equal(recent.lines[0], "LogEOS: message 11200");
    assert.equal(recent.lines.at(-1), "LogEOS: message 11999");
    assert(recent.truncated);
    const manyExport = zipInfo(await buildLogExport({ kind: "server", record: many })).info;
    assert.equal(manyExport.eos.lines, 10000);
    assert.equal(manyExport.eos.messagesInCapturedNativeLog, 12000);
    assert(manyExport.eos.truncated);

    const emptyRoot = game("empty");
    const empty = { ...record, world_id: "empty", install_dir: emptyRoot };
    await assert.rejects(buildLogExport({ kind: "server", record: empty }), (error) => error.status === 404);
    assert((await readLogView({ kind: "server", record: empty })).missing);
    write(ue4ssFile(emptyRoot), "Loader only\n");
    const partial = zipInfo(await buildLogExport({ kind: "server", record: empty }));
    assert.deepEqual(partial.info.missing, ["native"]);
    assert(!partial.zip.getEntry("eos/EOS.log"));

    const linkedRoot = game("linked"), outside = path.join(sandbox, "outside");
    write(path.join(outside, "RSDragonwilds.log"), "SECRET outside installation");
    const junction = path.join(linkedRoot, "RSDragonwilds", "Saved", "Logs");
    fs.mkdirSync(path.dirname(junction), { recursive: true });
    fs.symlinkSync(outside, junction, process.platform === "win32" ? "junction" : "dir");
    try {
      await assert.rejects(buildLogExport({ kind: "server", record: { ...record, world_id: "linked", install_dir: linkedRoot } }), (error) => error.status === 404);
    } finally { fs.unlinkSync(junction); }

    const first = buildLogExport({ kind: "server", record });
    await assert.rejects(buildLogExport({ kind: "server", record }), (error) => error.status === 409);
    await first;
    const abort = new AbortController();
    abort.abort();
    await assert.rejects(buildLogExport({ kind: "server", record, signal: abort.signal }), (error) => error.status === 499);
    await buildLogExport({ kind: "server", record });

    dbm.insertWorld({ world_id: record.world_id, display_name: "Server", install_dir: install, platform: "windows", env_vars: "{}", wine_binary: "wine", wine_prefix: null, wine_launch_flags: "", game_port: 7777, query_port: 27015, rest_api_port: 7778, rcon_port: 25575, admin_password: "secret", rest_api_enabled: 1, owner_id: null, default_world_name: null, status: "running", autostart: 0, crash_guard: 1, build_id: null, extra_args: "", created_at: Date.now() });
    dbm.upsertProfile(player);
    dbm.setSetting("remoteAccess.enabled", true);
    process.env.DWSM_ADMIN_TOKEN = "log-export-test-token";
    const request = (admin = true, channel = "eos") => new Request(`http://localhost:4317/logs?channel=${encodeURIComponent(channel)}`, { headers: admin ? { cookie: "dwsm_admin=log-export-test-token" } : { "x-forwarded-for": "127.0.0.1" } });
    for (const [kind, id] of [["server", record.world_id], ["player", player.profile_id]]) {
      for (const action of ["export", "view"]) {
        const denied = await handleRequest(request(false), "unknown", kind, action);
        assert.equal(denied.status, 403, "Admin guard must run before profile lookup, including loopback guests");
        const allowed = await handleRequest(request(), id, kind, action);
        assert.equal(allowed.status, 200);
        assert(allowed.headers.get("cache-control").includes("no-store"));
        if (action === "export") assert(new AdmZip(Buffer.from(await allowed.arrayBuffer())).getEntry("export-info.json"));
        else assert.equal((await allowed.json()).channel, "eos");
        assert.equal((await handleRequest(request(), "unknown", kind, action)).status, 404);
      }
    }
    assert.equal((await handleRequest(request(true, "bogus"), record.world_id, "server", "view")).status, 400);
    for (const file of ["components/PlayerWorldLibrary.jsx", "components/HostLibrary.jsx"]) {
      const code = source(file);
      assert(code.includes("<WorldActionsMenu") && code.includes("Export Logs"));
      assert.equal((code.match(/onContextMenu=\{onContext\}/g) || []).length, 2, "Rows and placards both need the right-click action");
    }
    const panel = source("components/NativeLogPanel.jsx");
    assert(panel.includes("controller.current?.abort()") && panel.includes('document.visibilityState === "hidden"'));
    assert(panel.includes("{line}</div>") && !panel.includes("dangerouslySetInnerHTML"));
    assert(source("components/LogsPanel.jsx").includes('["eos", "EOS"]'));
    assert(/logsOpen && <div[^>]*><NativeLogPanel/.test(source("app/profiles/[id]/player/page.jsx")));
    for (const scope of ["worlds", "profiles"]) for (const action of ["files", "export"]) assert(source(`app/api/${scope}/[id]/logs/${action}/route.js`).includes('@/lib/log-api'));
    console.log("Native/UE4SS/EOS log snapshots, ZIP exports, limits, log rotation, path confinement, admin routes and row/placard contracts passed.");
  } finally {
    try { dbm.db().close(); } catch {}
    const resolved = path.resolve(sandbox), temp = path.resolve(os.tmpdir());
    assert(path.dirname(resolved).toLowerCase() === temp.toLowerCase() && path.basename(resolved).startsWith("rsdw-log-export-"));
    fs.rmSync(resolved, { recursive: true, force: true });
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
