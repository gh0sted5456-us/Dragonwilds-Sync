// RSDW Save Converter remains a separate GPL-3.0 program. RSDW Sync downloads
// the unmodified upstream portable executable on demand, verifies its published
// SHA-256 manifest, and launches it as an external tool; it is not bundled here.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { P } = require("./paths");
const jobs = require("./jobs");

const REPOSITORY = "RSDWArchive/RSDWSaveConverter";
const RELEASES_URL = `https://api.github.com/repos/${REPOSITORY}/releases/latest`;
const MAX_TOOL_BYTES = 120 * 1024 * 1024;

async function checkedFetch(url) {
  const response = await fetch(url, { redirect: "follow", headers: { "user-agent": "RSDW-Sync", accept: "application/vnd.github+json" } });
  if (!response.ok) throw new Error(`RSDW Save Converter download failed (${response.status})`);
  return response;
}

function safeTag(value) {
  return String(value || "latest").replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 80) || "latest";
}

async function latestRelease() {
  const release = await (await checkedFetch(RELEASES_URL)).json();
  const assets = Array.isArray(release.assets) ? release.assets : [];
  const executable = assets.find((asset) => /RSDWSaveConverter-.+-win-x64\.exe$/i.test(asset.name));
  const manifest = assets.find((asset) => /RSDWSaveConverter-.+-win-x64\.sha256$/i.test(asset.name));
  if (!executable || !manifest) throw new Error("The upstream converter release is missing its Windows executable or SHA-256 manifest");
  return { tag: release.tag_name, releaseUrl: release.html_url, executable, manifest };
}

function expectedDigest(manifestText, filename) {
  for (const line of String(manifestText || "").split(/\r?\n/)) {
    const match = line.trim().match(/^([a-f0-9]{64})\s+\*?(.+)$/i);
    if (match && path.basename(match[2].trim()).toLowerCase() === filename.toLowerCase()) return match[1].toLowerCase();
  }
  throw new Error("The upstream SHA-256 manifest does not contain the converter executable");
}

function digestFile(file) {
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const chunk = Buffer.allocUnsafe(1024 * 1024);
  try {
    let count;
    while ((count = fs.readSync(fd, chunk, 0, chunk.length, null)) > 0) hash.update(chunk.subarray(0, count));
  } finally { fs.closeSync(fd); }
  return hash.digest("hex");
}

async function downloadExecutable(asset, destination, expected, jobId) {
  const response = await checkedFetch(asset.browser_download_url);
  const declared = Number(response.headers.get("content-length") || asset.size || 0);
  if (declared > MAX_TOOL_BYTES) throw new Error("The upstream converter executable is unexpectedly large");
  const temporary = `${destination}.incoming-${crypto.randomBytes(4).toString("hex")}`;
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  const fd = fs.openSync(temporary, "wx");
  const hash = crypto.createHash("sha256");
  let received = 0;
  try {
    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > MAX_TOOL_BYTES) throw new Error("The converter download exceeded its safety limit");
      const chunk = Buffer.from(value);
      let offset = 0;
      while (offset < chunk.length) offset += fs.writeSync(fd, chunk, offset, chunk.length - offset);
      hash.update(chunk);
      jobs.setProgress(jobId, declared > 0 ? Math.round((received / declared) * 100) : null, "Downloading RSDW Save Converter…");
    }
    fs.fsyncSync(fd);
  } catch (error) {
    fs.closeSync(fd);
    fs.rmSync(temporary, { force: true });
    throw error;
  }
  fs.closeSync(fd);
  if (hash.digest("hex").toLowerCase() !== expected) {
    fs.rmSync(temporary, { force: true });
    throw new Error("RSDW Save Converter failed SHA-256 verification");
  }
  fs.rmSync(destination, { force: true });
  try { fs.renameSync(temporary, destination); }
  catch (error) {
    if (!['EPERM', 'EXDEV'].includes(error.code)) throw error;
    fs.copyFileSync(temporary, destination);
    fs.rmSync(temporary, { force: true });
  }
  return destination;
}

async function ensureConverter() {
  if (process.platform !== "win32") throw new Error("RSDW Save Converter currently supports Windows x64 only");
  const jobId = jobs.createJob({ type: "install", worldName: "RSDW Save Converter" });
  try {
    jobs.setPhase(jobId, "prepare", "Checking the upstream converter release…");
    const release = await latestRelease();
    const manifestText = await (await checkedFetch(release.manifest.browser_download_url)).text();
    const expected = expectedDigest(manifestText, release.executable.name);
    const destination = path.join(P.tools(), "rsdw-save-converter", safeTag(release.tag), release.executable.name);
    if (!fs.existsSync(destination) || digestFile(destination).toLowerCase() !== expected) {
      await downloadExecutable(release.executable, destination, expected, jobId);
    }
    jobs.logJob(jobId, `Verified ${release.executable.name}`);
    jobs.finishJob(jobId, true);
    return { path: destination, version: release.tag, releaseUrl: release.releaseUrl, digest: expected };
  } catch (error) {
    jobs.finishJob(jobId, false, { error: error.message });
    throw error;
  }
}

module.exports = { ensureConverter, latestRelease, expectedDigest };
