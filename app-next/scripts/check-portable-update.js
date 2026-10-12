const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { allowedDownloadUrl, verifyPortable, MIN_PORTABLE_BYTES } = require("../electron/portable-update");
const version = require("../lib/appversion");

(async () => {
  assert.equal(version.BRANCHES.experimental, "main");
  const priorVersion = process.env.APP_MANAGER_APP_VERSION;
  const priorBranch = process.env.APP_MANAGER_BUILD_BRANCH;
  try {
    process.env.APP_MANAGER_BUILD_BRANCH = "main";
    process.env.APP_MANAGER_APP_VERSION = "0.1.3-super-experimental";
    assert.equal(version.currentBuildInfo().channel, "experimental");
    process.env.APP_MANAGER_APP_VERSION = "1.0.0";
    assert.equal(version.currentBuildInfo().channel, "stable");
  } finally {
    if (priorVersion === undefined) delete process.env.APP_MANAGER_APP_VERSION;
    else process.env.APP_MANAGER_APP_VERSION = priorVersion;
    if (priorBranch === undefined) delete process.env.APP_MANAGER_BUILD_BRANCH;
    else process.env.APP_MANAGER_BUILD_BRANCH = priorBranch;
  }
  assert(allowedDownloadUrl("https://github.com/gh0sted5456-us/Dragonwilds-Sync/releases/download/test/RSDW.exe"));
  assert(allowedDownloadUrl("https://release-assets.githubusercontent.com/github-production-release-asset/test"));
  assert(!allowedDownloadUrl("http://github.com/gh0sted5456-us/Dragonwilds-Sync/releases/download/test/RSDW.exe"));
  assert(!allowedDownloadUrl("https://github.com.evil.invalid/RSDW.exe"));
  assert(!allowedDownloadUrl("file:///C:/RSDW.exe"));

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-portable-update-"));
  try {
    const valid = path.join(dir, "valid.exe");
    const buffer = Buffer.alloc(MIN_PORTABLE_BYTES, 0);
    buffer.write("MZ", 0, "ascii");
    fs.writeFileSync(valid, buffer);
    const digest = crypto.createHash("sha256").update(buffer).digest("hex");
    await verifyPortable(valid, { size: buffer.length, digest: `sha256:${digest}` });
    await assert.rejects(() => verifyPortable(valid, { digest: `sha256:${"0".repeat(64)}` }), /SHA-256/);

    const invalid = path.join(dir, "invalid.exe");
    fs.writeFileSync(invalid, Buffer.alloc(MIN_PORTABLE_BYTES, 0));
    await assert.rejects(() => verifyPortable(invalid), /Windows executable/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  console.log("portable update checks passed");
})().catch((error) => { console.error(error); process.exit(1); });
