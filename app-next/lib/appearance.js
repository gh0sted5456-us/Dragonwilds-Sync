const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { P } = require("./paths");
const { DEFAULT_APPEARANCE, normalizeAppearance, validBackgroundName } = require("./appearance-preferences");
const MAX_IMAGE_BYTES = 12 * 1024 * 1024;
const MAX_IMAGES = 32;
const HEADER_BYTES = 256 * 1024;
const ready = new Map();
const builtins = [{ id: "woodland.webp", name: "Woodland", file: "5.webp" }, { id: "coast.webp", name: "Coast", file: "6.webp" }, { id: "landscape.webp", name: "Distant horizons", file: "7.webp" }, { id: "ruins.webp", name: "Sunlit ruins", file: "8.webp" }, { id: "highlands.webp", name: "Highlands", file: "9.webp" }];
class AppearanceError extends Error { constructor(message, status = 400) { super(message); this.status = status; } }
const inside = (root, file) => { const r = path.relative(root, file); return !path.isAbsolute(r) && r !== ".." && !r.startsWith(`..${path.sep}`); };

async function folders() {
  const base = path.resolve(P.data()), anchor = await fs.promises.realpath(base);
  const root = path.join(base, "appearance"), backgrounds = path.join(root, "backgrounds");
  for (const dir of [root, backgrounds]) {
    await fs.promises.mkdir(dir, { recursive: true });
    const stat = await fs.promises.lstat(dir);
    if (!stat.isDirectory() || stat.isSymbolicLink() || !inside(anchor, await fs.promises.realpath(dir))) throw new AppearanceError("Appearance storage cannot use linked folders.");
  }
  const locations = { root, backgrounds, config: path.join(root, "preferences.json"), anchor };
  if (!ready.has(root)) {
    const seed = (async () => {
      for (const item of builtins) {
        try { await fs.promises.copyFile(path.join(process.cwd(), "public/rsdw/placards", item.file), path.join(backgrounds, item.id), fs.constants.COPYFILE_EXCL); }
        catch (error) { if (!["EEXIST", "ENOENT"].includes(error.code)) throw error; }
      }
      try { await fs.promises.writeFile(locations.config, JSON.stringify(DEFAULT_APPEARANCE, null, 2), { flag: "wx" }); }
      catch (error) { if (error.code !== "EEXIST") throw error; }
    })().catch((error) => { ready.delete(root); throw error; });
    ready.set(root, seed);
  }
  await ready.get(root);
  return locations;
}

async function readOwned(locations, file, cap) {
  const stat = await fs.promises.lstat(file);
  if (!stat.isFile() || stat.isSymbolicLink() || !inside(locations.anchor, await fs.promises.realpath(file))) throw new AppearanceError("Linked appearance files are not supported.");
  const handle = await fs.promises.open(file, fs.constants.O_RDONLY | (process.platform === "win32" ? 0 : fs.constants.O_NOFOLLOW || 0));
  try {
    const current = await handle.stat();
    if (current.ino !== stat.ino || current.dev !== stat.dev || !inside(locations.anchor, await fs.promises.realpath(file))) throw new AppearanceError("Appearance file changed. Refresh and try again.");
    const bytes = Buffer.alloc(Math.min(current.size, cap));
    let offset = 0;
    while (offset < bytes.length) { const read = await handle.read(bytes, offset, bytes.length - offset, offset); if (!read.bytesRead) break; offset += read.bytesRead; }
    return { bytes: bytes.subarray(0, offset), stat: current };
  } finally { await handle.close(); }
}

function imageInfo(bytes, extension) {
  let width = 0, height = 0, mime = "";
  if (bytes.length >= 24 && bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10])) && bytes.toString("ascii", 12, 16) === "IHDR") {
    width = bytes.readUInt32BE(16); height = bytes.readUInt32BE(20); mime = "image/png";
    let offset = 8;
    while (offset + 8 <= bytes.length) {
      const size = bytes.readUInt32BE(offset), kind = bytes.toString("ascii", offset + 4, offset + 8);
      if (kind === "acTL") throw new AppearanceError("Use a still image, not an animated background.");
      if (kind === "IDAT" || offset + 12 + size > bytes.length) break;
      offset += size + 12;
    }
  } else if (bytes.length >= 30 && bytes.toString("ascii", 0, 4) === "RIFF" && bytes.toString("ascii", 8, 12) === "WEBP") {
    const chunk = bytes.toString("ascii", 12, 16); mime = "image/webp";
    if (chunk === "VP8X") { if (bytes[20] & 2) throw new AppearanceError("Use a still image, not an animated background."); width = 1 + bytes.readUIntLE(24, 3); height = 1 + bytes.readUIntLE(27, 3); }
    else if (chunk === "VP8 " && bytes[23] === 0x9d && bytes[24] === 1 && bytes[25] === 0x2a) { width = bytes.readUInt16LE(26) & 0x3fff; height = bytes.readUInt16LE(28) & 0x3fff; }
    else if (chunk === "VP8L" && bytes[20] === 0x2f) { const bits = bytes.readUInt32LE(21); width = (bits & 0x3fff) + 1; height = ((bits >>> 14) & 0x3fff) + 1; }
  } else if (bytes.length >= 4 && bytes[0] === 0xff && bytes[1] === 0xd8) {
    mime = "image/jpeg";
    for (let offset = 2; offset + 4 < bytes.length;) {
      if (bytes[offset++] !== 0xff) break;
      while (bytes[offset] === 0xff) offset++;
      const marker = bytes[offset++];
      if (marker === 0xda || marker === 0xd9) break;
      if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
      if (offset + 2 > bytes.length) break;
      const length = bytes.readUInt16BE(offset);
      if (length < 2 || offset + length > bytes.length) break;
      if ([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker) && length >= 7) { height = bytes.readUInt16BE(offset + 3); width = bytes.readUInt16BE(offset + 5); break; }
      offset += length;
    }
  }
  const ext = String(extension || "").toLowerCase();
  const expected = mime === "image/jpeg" ? [".jpg", ".jpeg"] : mime === "image/png" ? [".png"] : [".webp"];
  if (!mime || !width || !height || !expected.includes(ext)) throw new AppearanceError("Choose a valid PNG, JPEG or WebP still image.");
  if (width > 8192 || height > 8192 || width * height > 32 * 1024 * 1024) throw new AppearanceError("Backgrounds must be at most 8192 pixels per side and 32 megapixels.");
  return { width, height, mime };
}

async function preferences(locations) {
  try {
    const { bytes, stat } = await readOwned(locations, locations.config, 32768);
    if (stat.size > 32768) throw new Error("oversized config");
    const saved = JSON.parse(bytes.toString("utf8"));
    return { preferences: normalizeAppearance(saved) };
  } catch { return { preferences: { ...DEFAULT_APPEARANCE }, warning: "Appearance preferences could not be read; defaults are in use. Background files are unchanged." }; }
}
async function catalog(locations) {
  const list = [];
  const entries = await fs.promises.readdir(locations.backgrounds, { withFileTypes: true });
  for (const entry of entries) {
    if (list.length >= MAX_IMAGES) break;
    if (!entry.isFile() || !validBackgroundName(entry.name)) continue;
    try {
      const read = await readOwned(locations, path.join(locations.backgrounds, entry.name), HEADER_BYTES);
      if (read.stat.size > MAX_IMAGE_BYTES) continue;
      const details = imageInfo(read.bytes, path.extname(entry.name));
      list.push({ id: entry.name, name: builtins.find((item) => item.id === entry.name)?.name || path.parse(entry.name).name.replace(/^custom-/, "").replace(/-[a-f0-9]{16}$/, ""), ...details,
        url: `/api/appearance/background/${encodeURIComponent(entry.name)}?v=${read.stat.size}-${Math.floor(read.stat.mtimeMs)}` });
    } catch { /* An invalid or linked image never blocks appearance or startup. */ }
  }
  return list.sort((a, b) => a.name.localeCompare(b.name));
}
async function getAppearance(includeCatalog = false) {
  const locations = await folders();
  const state = await preferences(locations);
  if (state.preferences.background !== "none") {
    const file = await fs.promises.lstat(path.join(locations.backgrounds, state.preferences.background)).catch(() => null);
    if (!file?.isFile() || file.isSymbolicLink() || file.size > MAX_IMAGE_BYTES) {
      state.preferences = { ...state.preferences, background: "none" };
      state.warning = "The selected background is unavailable. Choose another image or restore it to the backgrounds folder.";
    }
  }
  return { ok: true, ...state, directory: locations.backgrounds, ...(includeCatalog ? { backgrounds: await catalog(locations) } : {}) };
}
async function saveAppearance(input) {
  const locations = await folders(), previous = (await preferences(locations)).preferences;
  const next = normalizeAppearance(input, previous);
  if (next.background !== "none") {
    if (!validBackgroundName(next.background)) throw new AppearanceError("Unknown background.");
    const read = await readOwned(locations, path.join(locations.backgrounds, next.background), HEADER_BYTES).catch(() => { throw new AppearanceError("That background is unavailable. Refresh the gallery."); });
    if (read.stat.size > MAX_IMAGE_BYTES) throw new AppearanceError("The background is too large.");
    imageInfo(read.bytes, path.extname(next.background));
  }
  // Atomic replacement avoids partially written settings after interruption.
  const temp = path.join(locations.root, `.preferences-${crypto.randomUUID()}.tmp`);
  try {
    await fs.promises.writeFile(temp, JSON.stringify(next, null, 2), { flag: "wx" });
    const current = await fs.promises.lstat(locations.config).catch(() => null);
    if (current?.isSymbolicLink()) throw new AppearanceError("Linked preference files cannot be replaced.");
    await fs.promises.rename(temp, locations.config);
  } finally { await fs.promises.unlink(temp).catch(() => {}); }
  return { ok: true, preferences: next, directory: locations.backgrounds };
}
async function importBackground(bytes, name) {
  if (!bytes.length || bytes.length > MAX_IMAGE_BYTES) throw new AppearanceError("Choose a background no larger than 12 MiB.", 413);
  const raw = String(name || "background");
  const ext = path.extname(raw).toLowerCase();
  const details = imageInfo(bytes.subarray(0, HEADER_BYTES), ext);
  const locations = await folders();
  const stem = path.basename(raw, path.extname(raw)).replace(/[^a-zA-Z0-9_-]/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "background";
  const id = `custom-${stem}-${crypto.createHash("sha256").update(bytes).digest("hex").slice(0, 16)}${ext}`;
  const file = path.join(locations.backgrounds, id);
  const existing = await fs.promises.lstat(file).catch(() => null);
  if (existing) {
    const old = await readOwned(locations, file, MAX_IMAGE_BYTES);
    if (!old.bytes.equals(bytes)) throw new AppearanceError("An existing background with this name is different. Rename the image and retry.");
  } else {
    if ((await catalog(locations)).length >= MAX_IMAGES) throw new AppearanceError("The gallery is full (32 images). Move an unused custom image out of the backgrounds folder, then refresh.");
    await fs.promises.writeFile(file, bytes, { flag: "wx" });
  }
  return { ok: true, asset: { id, name: stem, ...details }, backgrounds: await catalog(locations) };
}
async function getBackground(id) {
  if (!validBackgroundName(id)) throw new AppearanceError("Background not found.", 404);
  const locations = await folders();
  const read = await readOwned(locations, path.join(locations.backgrounds, id), MAX_IMAGE_BYTES).catch(() => { throw new AppearanceError("Background not found.", 404); });
  if (read.stat.size > MAX_IMAGE_BYTES) throw new AppearanceError("Background exceeds the size limit.", 413);
  const details = imageInfo(read.bytes.subarray(0, HEADER_BYTES), path.extname(id));
  return { bytes: read.bytes, mime: details.mime, etag: `"${crypto.createHash("sha256").update(read.bytes).digest("hex")}"` };
}
module.exports = { getAppearance, saveAppearance, importBackground, getBackground, imageInfo, AppearanceError, MAX_IMAGE_BYTES };
