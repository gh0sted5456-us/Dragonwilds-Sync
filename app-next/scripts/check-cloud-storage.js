const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-cloud-storage-"));
process.env.APP_MANAGER_DATA_DIR = path.join(sandbox, "data");
const dbm = require("../lib/db");
const cloud = require("../lib/sync/cloud-storage");

const file = { target: "RSDragonwilds/Content/Paks/~mods/Example.pak", size: 12, sha256: "a".repeat(64) };
const localManifest = { revision: "local-revision", units: [{ files: [file] }] };

async function run() {
  try {
    const dropbox = cloud.normalizePublicUrl("https://www.dropbox.com/scl/fi/token/rsdw-manifest.json?rlkey=key&dl=0", "dropbox");
    assert.equal(new URL(dropbox).searchParams.get("dl"), "1", "Dropbox links must force file download");
    assert(cloud.normalizePublicUrl("https://drive.google.com/file/d/abc123/view", "google").startsWith("https://drive.usercontent.google.com/download?"), "Google Drive file share was not converted to a download URL");
    assert.throws(() => cloud.normalizePublicUrl("http://127.0.0.1/manifest.json", "generic"), /HTTPS/, "Non-HTTPS/private manifest was accepted");
    assert.throws(() => cloud.normalizePublicUrl("https://example.com/manifest.json", "dropbox"), /supported Dropbox/, "Provider host allowlist was bypassed");

    const worldId = "cloud-storage-test";
    cloud.save(worldId, { mode: "hybrid", hostType: "managed", provider: "dropbox", manifestUrl: "https://www.dropbox.com/scl/fi/token/rsdw-manifest.json?rlkey=key" });
    const mockFetch = async () => new Response(JSON.stringify({ schema: cloud.SCHEMA, revision: "cloud-release-1", files: [{ ...file, url: "https://www.dropbox.com/scl/fi/token/Example.pak?rlkey=key" }] }), { status: 200, headers: { "content-type": "application/json" } });
    const status = await cloud.refresh(worldId, localManifest, mockFetch);
    assert.equal(status.mode, "hybrid");
    assert.equal(status.hostType, "managed", "Hosting category must remain independent from delivery mode");
    assert.equal(status.fileCount, 1);
    assert(!JSON.stringify(status).includes("dropbox.com"), "Public status leaked a provider URL");
    const remote = cloud.resolveRemoteFile(worldId, file);
    assert.equal(remote.mode, "hybrid");
    assert(remote.url.includes("dl=1"), "Remote file URL was not normalized for download");
    assert.throws(() => cloud.validateCloudManifest({ schema: cloud.SCHEMA, files: [{ ...file, sha256: "b".repeat(64), url: remote.url }] }, localManifest, "dropbox"), /does not match/, "Mismatched cloud content was trusted");
    const clientSource = fs.readFileSync(path.join(__dirname, "..", "lib", "sync", "client.js"), "utf8");
    assert(clientSource.includes('redirect: "manual"'), "Client does not isolate authenticated server requests from cloud redirects");
    assert(clientSource.includes('fallback.searchParams.set("source", "local")'), "Hybrid mode does not retry through the local server");

    cloud.save(worldId, { mode: "local", hostType: "managed" });
    assert.equal(cloud.resolveRemoteFile(worldId, file).url, null, "Local mode attempted cloud delivery");
    assert.equal(cloud.publicStatus(worldId).hostType, "managed", "Switching to direct delivery must not recategorize a paid host");
    console.log("Cloud storage delivery: OK");
  } finally {
    try { dbm.db().close(); } catch {}
    fs.rmSync(sandbox, { recursive: true, force: true });
  }
}

run().catch((error) => { console.error(error); process.exitCode = 1; });
