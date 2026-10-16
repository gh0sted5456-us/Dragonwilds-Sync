const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { CloudPublisher, authorizeUrl, validateExport, safeTarget } = require("../electron/cloud-publisher");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-cloud-publisher-"));
const storage = { isEncryptionAvailable: () => true, getSelectedStorageBackend: () => "dpapi",
  encryptString: (value) => Buffer.from(value), decryptString: (value) => value.toString("utf8") };

async function run(provider) {
  const dataDir = path.join(sandbox, provider);
  const worldId = "server-test";
  const folder = path.join(dataDir, "delivery-exports", worldId, "export-1");
  const target = "RSDragonwilds/Content/Paks/~mods/Example.pak";
  const source = path.join(folder, ...target.split("/"));
  fs.mkdirSync(path.dirname(source), { recursive: true });
  fs.writeFileSync(source, "verified cloud mod");
  const bytes = fs.readFileSync(source);
  const file = { target, size: bytes.length, sha256: crypto.createHash("sha256").update(bytes).digest("hex"), url: "PASTE_PUBLIC_FILE_LINK" };
  fs.writeFileSync(path.join(folder, "rsdw-manifest.json"), JSON.stringify({ schema: "RSDWSync.CloudManifest.v1", revision: "release-1", files: [file] }));
  assert.equal(validateExport(dataDir, worldId, folder).files.length, 1);
  let nextId = 0;
  const requests = [];
  const fetchImpl = async (url, options) => {
    requests.push({ url, method: options.method, authorization: options.headers?.Authorization });
    if (provider === "google") {
      if (url.includes("uploadType=resumable")) return new Response(null, { status: 200, headers: { location: "https://www.googleapis.com/upload/session" } });
      if (url.endsWith("/upload/session")) return new Response(JSON.stringify({ id: `file-${++nextId}` }), { status: 200 });
      if (url.endsWith("/permissions")) return new Response("{}", { status: 200 });
      if (url.includes("drive/v3/files?fields=")) return new Response(JSON.stringify({ id: "folder-1" }), { status: 200 });
    } else {
      if (url.endsWith("/root/children")) return new Response(JSON.stringify({ id: "folder-1" }), { status: 201 });
      if (url.endsWith("/createUploadSession")) return new Response(JSON.stringify({ uploadUrl: "https://up.1drv.com/session" }), { status: 200 });
      if (url.endsWith("up.1drv.com/session")) return new Response(JSON.stringify({ id: `file-${++nextId}` }), { status: 201 });
      if (url.endsWith("/createLink")) return new Response(JSON.stringify({ link: { webUrl: "https://1drv.ms/u/test" } }), { status: 201 });
    }
    throw new Error(`Unexpected ${provider} request: ${url}`);
  };
  const publisher = new CloudPublisher({ dataDir, safeStorage: storage, openExternal: async () => {}, fetchImpl });
  publisher.write({ [provider]: { clientId: "client-id-test", refreshToken: "private-refresh", accessToken: "private-access",
    expiresAt: Date.now() + 3600_000, folders: {}, uploaded: {} } });
  assert.equal(publisher.status().providers[provider].connected, true);
  assert(!JSON.stringify(publisher.status()).includes("private-refresh"));
  await assert.rejects(() => publisher.publish(provider, worldId, folder, false), /Confirm public read-only/);
  const published = await publisher.publish(provider, worldId, folder, true);
  assert.equal(published.fileCount, 1);
  assert(published.manifestUrl.startsWith(provider === "google" ? "https://drive.google.com/" : "https://1drv.ms/"));
  assert.equal(nextId, 2, "mod file and manifest must both be uploaded");
  assert.throws(() => publisher.setAutoPublish(provider, worldId, true, "steam", false, published.revision), /explicitly approve/);
  assert.throws(() => publisher.setAutoPublish(provider, worldId, true, "steam", true, "unverified"), /Publish and verify/);
  const optedIn = publisher.setAutoPublish(provider, worldId, true, "steam", true, published.revision);
  assert.equal(optedIn.providers[provider].auto[worldId].enabled, true);
  assert.equal(publisher.autoTasks()[0].lastVerifiedRevision, published.revision);
  publisher.autoResult(provider, worldId, null, new Error("https://private.example/link failed"));
  assert(!publisher.status().providers[provider].auto[worldId].lastError.includes("private.example"));
  publisher.autoResult(provider, worldId, published.revision);
  assert.equal(publisher.status().providers[provider].auto[worldId].lastError, null);
  publisher.setAutoPublish(provider, worldId, false);
  assert.equal(publisher.autoTasks().length, 0);
  assert(requests.filter((entry) => entry.url.includes("/session")).every((entry) => !entry.authorization), "session upload must not leak the bearer token");
  assert(requests.filter((entry) => !entry.url.includes("/session")).every((entry) => entry.authorization === "Bearer private-access"));
  assert.equal(publisher.disconnect(provider).providers[provider].connected, false);
}

(async () => {
  const auth = new URL(authorizeUrl("google", "test-client-id", "http://127.0.0.1:50000", "state-test", "verifier".repeat(10)));
  assert.equal(auth.searchParams.get("code_challenge_method"), "S256");
  assert.equal(auth.searchParams.get("state"), "state-test");
  assert.throws(() => safeTarget("RSDragonwilds/../secret.sav"), /Invalid exported mod path/);
  await run("google");
  await run("onedrive");
  console.log("Opt-in encrypted cloud publisher: OK");
})().catch((error) => { console.error(error); process.exitCode = 1; }).finally(() => fs.rmSync(sandbox, { recursive: true, force: true }));
