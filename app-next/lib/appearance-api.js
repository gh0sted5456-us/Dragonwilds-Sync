const { NextResponse } = require("next/server");
const auth = require("./remoteauth");
const appearance = require("./appearance");
const privateHeaders = { "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff", Vary: "Cookie" };
async function readBody(req, limit, message) {
  if (Number(req.headers.get("content-length")) > limit) throw new appearance.AppearanceError(message, 413);
  const reader = req.body?.getReader();
  if (!reader) throw new appearance.AppearanceError("The request body is empty.");
  const chunks = []; let size = 0;
  try {
    while (true) {
      const part = await reader.read(); if (part.done) break;
      size += part.value.byteLength;
      if (size > limit) { await reader.cancel(); throw new appearance.AppearanceError(message, 413); }
      chunks.push(Buffer.from(part.value));
    }
  } finally { reader.releaseLock(); }
  return Buffer.concat(chunks, size);
}
async function handleAppearance(req, action, id) {
  try {
    if (!auth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403, headers: privateHeaders });
    if (action === "read") return NextResponse.json(await appearance.getAppearance(new URL(req.url).searchParams.get("catalog") === "1"), { headers: privateHeaders });
    if (action === "save") {
      const bytes = await readBody(req, 32768, "Appearance preferences are too large.");
      let input;
      try { input = JSON.parse(bytes.toString("utf8")); } catch { throw new appearance.AppearanceError("Invalid appearance preferences."); }
      return NextResponse.json(await appearance.saveAppearance(input), { headers: privateHeaders });
    }
    if (action === "image") {
      const asset = await appearance.getBackground(id);
      const headers = { ...privateHeaders, "Content-Type": asset.mime, "Cache-Control": "private, max-age=3600", ETag: asset.etag };
      if (req.headers.get("if-none-match") === asset.etag) return new NextResponse(null, { status: 304, headers });
      return new NextResponse(asset.bytes, { headers });
    }
    if (action === "import") {
      const bytes = await readBody(req, appearance.MAX_IMAGE_BYTES, "Backgrounds must be at most 12 MiB.");
      let name;
      try { name = decodeURIComponent(req.headers.get("x-rsdw-image-name") || "background"); } catch { throw new appearance.AppearanceError("Invalid image filename."); }
      return NextResponse.json(await appearance.importBackground(bytes, name), { headers: privateHeaders });
    }
    throw new appearance.AppearanceError("Unknown appearance action.");
  } catch (error) {
    return NextResponse.json({ ok: false, error: error instanceof appearance.AppearanceError ? error.message : "Appearance files are unavailable. Check the application data folder permissions and retry." }, { status: error instanceof appearance.AppearanceError ? error.status : 500, headers: privateHeaders });
  }
}
module.exports = { handleAppearance };
