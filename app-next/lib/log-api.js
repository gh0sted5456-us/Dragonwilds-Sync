const { NextResponse } = require("next/server");
const dbm = require("./db");
const auth = require("./remoteauth");
const clientService = require("./client-service");
const logs = require("./log-export");
const noStore = { "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff" };

async function handleRequest(req, id, kind, action) {
  try {
    if (!auth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403, headers: noStore });
    if (!["server", "player"].includes(kind) || !["export", "view"].includes(action)) throw new logs.LogExportError("Unknown log request.");
    let record = kind === "server" ? dbm.getWorld(id) : dbm.getProfile(id);
    if (!record) throw new logs.LogExportError("World/server profile not found.", 404);
    if (kind === "player") {
      record = clientService.resolveProfileService(record, { persist: false }).profile;
      const service = clientService.legacyService(clientService.parseConnection(record));
      record = { ...record, client_install: record.client_install || dbm.getSetting(`clientInstall:${service}`, null) };
    }
    if (action === "view") {
      const channel = new URL(req.url).searchParams.get("channel") || "eos";
      return NextResponse.json(await logs.readLogView({ kind, record, channel, signal: req.signal }), { headers: noStore });
    }
    const result = await logs.buildLogExport({ kind, record, signal: req.signal });
    return new NextResponse(result.buffer, { headers: logs.downloadHeaders(result) });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error instanceof logs.LogExportError ? error.message : "Logs could not be read. Please try again." }, { status: error instanceof logs.LogExportError ? error.status : 500, headers: noStore });
  }
}
module.exports = { handleRequest };
