const assert = require("assert");
const fs = require("fs");
const path = require("path");
const os = require("os");
const postcss = require("postcss");
const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-appearance-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
process.env.DWSM_ADMIN_TOKEN = "appearance-test-only";
const dbm = require("../lib/db");
const store = require("../lib/appearance");
const { handleAppearance } = require("../lib/appearance-api");
const { DEFAULT_APPEARANCE, normalizeAppearance, validBackgroundName } = require("../lib/appearance-preferences");
const root = path.resolve(__dirname, "..");
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZ1kAAAAASUVORK5CYII=", "base64");
const request = (body, headers = {}, admin = true) => new Request("http://localhost/api/appearance", {
  method: body === undefined ? "GET" : "POST", headers: { ...(admin ? { cookie: "dwsm_admin=appearance-test-only" } : {}), ...headers },
  ...(body !== undefined ? { body, ...(body instanceof ReadableStream ? { duplex: "half" } : {}) } : {}),
});
const save = (value) => handleAppearance(request(JSON.stringify(value)), "save");

(async () => {
  try {
    dbm.setSetting("remoteAccess.enabled", true);
    for (const action of ["read", "save", "import", "image"]) {
      const denied = await handleAppearance(request(undefined, {}, false), action, "woodland.webp");
      assert.equal(denied.status, 403, `${action} must authorize before reading appearance files`);
      assert(denied.headers.get("cache-control").includes("no-store"));
      assert(!(await denied.text()).includes(sandbox));
    }
    assert(!fs.existsSync(path.join(process.env.APP_MANAGER_DATA_DIR, "appearance")));
    for (const invalid of ["../secret.png", "C:\\secret.png", "a/b.jpg", ".hidden.webp", "file.svg", "file.html", "a.png:stream", "a\0.png"]) assert(!validBackgroundName(invalid));
    assert(validBackgroundName("My image.png"));
    assert.deepEqual(normalizeAppearance(null), DEFAULT_APPEARANCE);
    assert.deepEqual(normalizeAppearance({ background: "../no.png", backgroundOpacity: Infinity, surfaceOpacity: "0.2", fit: "stretch" }), DEFAULT_APPEARANCE);
    assert.deepEqual(normalizeAppearance({ background: "none", backgroundOpacity: 100, surfaceOpacity: 0, fit: "contain", extra: true }), { version: 1, background: "none", backgroundOpacity: .6, surfaceOpacity: .72, fit: "contain" });

    const initial = await store.getAppearance(true), directory = initial.directory, config = path.join(path.dirname(directory), "preferences.json");
    assert.equal(initial.backgrounds.length, 5);
    assert.deepEqual(initial.preferences, DEFAULT_APPEARANCE);
    const original = fs.readFileSync(path.join(root, "public/rsdw/placards/5.webp"));
    assert(original.equals(fs.readFileSync(path.join(directory, "woodland.webp"))));
    assert(initial.backgrounds.every((item) => item.width > 0 && item.height > 0 && item.url.startsWith("/api/appearance/background/")));
    const modified = fs.readFileSync(path.join(root, "public/rsdw/placards/6.webp"));
    fs.writeFileSync(path.join(directory, "woodland.webp"), modified);
    delete require.cache[require.resolve("../lib/appearance")];
    await require("../lib/appearance").getAppearance();
    assert(modified.equals(fs.readFileSync(path.join(directory, "woodland.webp"))), "Seeding after an update must never overwrite user-owned images");
    fs.writeFileSync(path.join(directory, "woodland.webp"), original);

    const saved = await save({ background: "coast.webp", surfaceOpacity: .81, backgroundOpacity: .43, fit: "contain" });
    assert.equal(saved.status, 200);
    const expected = (await saved.json()).preferences;
    assert.deepEqual(JSON.parse(fs.readFileSync(config, "utf8")), expected);
    assert.deepEqual((await store.getAppearance()).preferences, expected);
    assert(!Object.hasOwn(await store.getAppearance(), "backgrounds"), "Startup must not scan every gallery image");
    assert.equal((await handleAppearance(request("{invalid"), "save")).status, 400);
    assert.equal((await handleAppearance(request("x".repeat(32769)), "save")).status, 413);
    const rename = fs.promises.rename;
    fs.promises.rename = async (from, to) => { if (to === config) throw Object.assign(new Error("fixture lock"), { code: "EPERM" }); return rename(from, to); };
    try { await assert.rejects(store.saveAppearance({ background: "none" }), /fixture lock/); }
    finally { fs.promises.rename = rename; }
    assert.deepEqual(JSON.parse(fs.readFileSync(config, "utf8")), expected, "A failed atomic replace keeps the previous preferences");
    assert(!fs.readdirSync(path.dirname(directory)).some((name) => name.endsWith(".tmp")));

    const uploaded = await handleAppearance(request(png, { "x-rsdw-image-name": encodeURIComponent("My custom image.png") }), "import");
    assert.equal(uploaded.status, 200);
    const imported = await uploaded.json();
    assert.match(imported.asset.id, /^custom-My-custom-image-[a-f0-9]{16}\.png$/);
    assert(png.equals(fs.readFileSync(path.join(directory, imported.asset.id))));
    assert.equal((await store.importBackground(png, "My custom image.png")).backgrounds.length, 6, "Importing the same file is idempotent");
    assert.equal((await store.getAppearance()).preferences.background, "coast.webp", "Import previews must not persist a selection before Save");
    await store.saveAppearance({ background: imported.asset.id });
    assert.equal((await store.getAppearance()).preferences.background, imported.asset.id);
    const image = await handleAppearance(request(), "image", imported.asset.id), etag = image.headers.get("etag");
    assert.equal(image.status, 200); assert.equal(image.headers.get("content-type"), "image/png");
    assert.equal(image.headers.get("x-content-type-options"), "nosniff");
    assert.equal(image.headers.get("vary"), "Cookie"); assert(image.headers.get("cache-control").includes("private"));
    assert(png.equals(Buffer.from(await image.arrayBuffer())));
    const cached = await handleAppearance(request(undefined, { "if-none-match": etag }), "image", imported.asset.id);
    assert.equal(cached.status, 304); assert.equal((await cached.arrayBuffer()).byteLength, 0);
    for (const id of ["../preferences.json", "missing.webp", "C:\\other.png", ".hidden.png"]) assert.equal((await handleAppearance(request(), "image", id)).status, 404);

    const giant = Buffer.from(png); giant.writeUInt32BE(8193, 16);
    assert.throws(() => store.imageInfo(giant, ".png"), /8192/);
    const animation = Buffer.alloc(20); animation.writeUInt32BE(8); animation.write("acTL", 4);
    const apng = Buffer.concat([png.subarray(0, 33), animation, png.subarray(33)]);
    assert.throws(() => store.imageInfo(apng, ".png"), /still image/);
    const animatedWebP = Buffer.alloc(30); animatedWebP.write("RIFF", 0); animatedWebP.write("WEBP", 8); animatedWebP.write("VP8X", 12); animatedWebP[20] = 2;
    assert.throws(() => store.imageInfo(animatedWebP, ".webp"), /still image/);
    // A minimal SOF header exercises JPEG dimension parsing without a decoder dependency.
    const jpegHeader = Buffer.from([255,216,255,192,0,11,8,0,16,0,32,1,1,17,0,255,217]);
    assert.deepEqual(store.imageInfo(jpegHeader, ".jpeg"), { width: 32, height: 16, mime: "image/jpeg" });
    for (const [bytes, name] of [[png, "wrong.jpg"], [Buffer.from("<svg/>"), "test.svg"], [Buffer.from("<html>oops</html>"), "test.png"], [Buffer.from("GIF89a"), "test.gif"], [Buffer.alloc(0), "empty.png"], [Buffer.alloc(store.MAX_IMAGE_BYTES + 1), "large.png"]]) await assert.rejects(store.importBackground(bytes, name));
    assert.equal((await handleAppearance(request(png, { "content-length": String(store.MAX_IMAGE_BYTES + 1) }), "import")).status, 413);
    const stream = new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(store.MAX_IMAGE_BYTES)); controller.enqueue(new Uint8Array(1)); controller.close(); } });
    assert.equal((await handleAppearance(request(stream), "import")).status, 413, "Chunked uploads must enforce the limit even without Content-Length");
    assert.equal((await handleAppearance(request(png, { "x-rsdw-image-name": "%invalid" }), "import")).status, 400);

    fs.unlinkSync(path.join(directory, imported.asset.id));
    const missing = await store.getAppearance();
    assert.equal(missing.preferences.background, "none"); assert.match(missing.warning, /unavailable/);
    assert.equal(JSON.parse(fs.readFileSync(config, "utf8")).background, imported.asset.id, "A missing image must not silently rewrite a user's selection");
    await store.saveAppearance({ background: "none" });
    assert.equal((await store.getAppearance()).preferences.background, "none");
    fs.writeFileSync(config, "{broken");
    assert.match((await store.getAppearance()).warning, /defaults/);
    assert.equal(fs.readFileSync(config, "utf8"), "{broken");
    assert.equal((await store.getAppearance(true)).backgrounds.length, 5);
    await store.saveAppearance(DEFAULT_APPEARANCE);

    const outside = path.join(sandbox, "external"); fs.mkdirSync(outside);
    fs.writeFileSync(path.join(outside, "private.png"), png);
    const linked = path.join(directory, "linked.png");
    try {
      fs.symlinkSync(path.join(outside, "private.png"), linked, "file");
      assert.equal((await handleAppearance(request(), "image", "linked.png")).status, 404);
      assert(!(await store.getAppearance(true)).backgrounds.some((item) => item.id === "linked.png"));
      await assert.rejects(store.saveAppearance({ background: "linked.png" }));
      fs.unlinkSync(linked);
    } catch (error) { if (!["EPERM", "EACCES"].includes(error.code)) throw error; console.log("File-symlink fixture unavailable on this Windows account; junction checks remain required."); }
    const held = `${directory}-held`; fs.renameSync(directory, held);
    fs.symlinkSync(outside, directory, process.platform === "win32" ? "junction" : "dir");
    await assert.rejects(store.getAppearance(), /linked folders/);
    assert.deepEqual(fs.readdirSync(outside), ["private.png"], "Linked directories must be rejected before writing default assets");
    fs.unlinkSync(directory); fs.renameSync(held, directory);
    const appearanceRoot = path.dirname(directory), heldRoot = `${appearanceRoot}-held`;
    fs.renameSync(appearanceRoot, heldRoot); fs.symlinkSync(outside, appearanceRoot, process.platform === "win32" ? "junction" : "dir");
    await assert.rejects(store.getAppearance(), /linked folders/);
    assert.deepEqual(fs.readdirSync(outside), ["private.png"]);
    fs.unlinkSync(appearanceRoot); fs.renameSync(heldRoot, appearanceRoot);

    const source = (file) => fs.readFileSync(path.join(root, file), "utf8");
    const css = source("app/globals.css"); postcss.parse(css);
    assert(css.includes("--bg: #050505") && css.includes("--accent: #c7a45b"));
    assert(css.includes("prefers-reduced-transparency:reduce"));
    const backdrop = css.match(/\.workspace-backdrop\s*\{([^}]+)\}/)[1];
    assert(!/filter|animation|transition/.test(backdrop), "Workspace wallpaper should not introduce continuous compositing work");
    assert(source("components/ThemeProvider.jsx").includes('if (guest) return;'));
    assert(source("components/ThemeProvider.jsx").includes('name: "Obsidian Gold"'));
    assert(source("components/AppearancePanel.jsx").includes("previewAppearance(null)"));
    assert(source("app/settings/page.jsx").includes('dynamic(() => import("@/components/AppearancePanel")'));
    assert(source("app/layout.js").includes("rsdw-appearance"), "Cached opacity must be applied before first paint");
    assert(source("electron/startup-screen.js").includes("background:#050505"));
    console.log("Appearance: AppData seed/preservation, persisted previews, safe image imports and limits, private cache, atomic failure recovery, corrupt/missing files, symlink/junction guards, black/gold and reduced-transparency contracts: OK");
  } finally {
    try { dbm.db().close(); } catch {}
    assert(path.dirname(sandbox).toLowerCase() === path.resolve(os.tmpdir()).toLowerCase() && path.basename(sandbox).startsWith("rsdw-appearance-"));
    fs.rmSync(sandbox, { recursive: true, force: true });
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
