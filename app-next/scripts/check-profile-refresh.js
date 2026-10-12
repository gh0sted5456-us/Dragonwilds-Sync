const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-profile-refresh-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const refresh = require("../lib/sync/profile-refresh");

(async () => {
  try {
    dbm.upsertProfile({ profile_id: "connected", display_name: "Old Name", server_world_id: "world-1", connection: { address: "127.0.0.1", syncPort: 4318, password: "secret", service: "steam", cachedModProfile: { revision: "rev-1", files: 1 } }, last_manifest_revision: "rev-1" });
    const profile = dbm.getProfile("connected");
    const result = await refresh.refreshProfile(profile, { fetchImpl: async (_url, request) => {
      assert.equal(request.headers["X-RSDW-World-Password"], "secret");
      return { ok: true, status: 200, json: async () => ({ manifest: { revision: "rev-2", world: { name: "Updated World", type: "Dedicated", rules: { access: "Friends" }, identity: { accentColor: "#7450b8" } }, units: [{ type: "pak" }, { type: "ue4ss" }] } }) };
    } });
    assert(result.changed && result.updateAvailable, "Remote manifest revision was not marked as an update");
    const updated = dbm.getProfile("connected");
    const connection = JSON.parse(updated.connection_json);
    assert.equal(updated.display_name, "Updated World");
    assert.equal(updated.last_manifest_revision, "rev-2");
    assert.equal(connection.modCount, 2);
    assert(connection.manifestUpdate.available, "Profile update indicator was not retained");

    const local = dbm.upsertProfile({ profile_id: "local", display_name: "Local", connection: { localWorld: true, service: "steam" } });
    assert((await refresh.refreshProfile(local, { fetchImpl: async () => { throw new Error("Local profile performed network I/O"); } })).skipped);
    console.log("Connected World manifest refresh: OK");
  } finally {
    try { dbm.db().close(); } catch {}
    fs.rmSync(sandbox, { recursive: true, force: true });
  }
})().catch((error) => { console.error(error); process.exit(1); });
