const fs = require("fs");
const path = require("path");
const https = require("https");
const crypto = require("crypto");
const { spawn } = require("child_process");

const MAX_DOWNLOAD_BYTES = 750 * 1024 * 1024;
const MIN_PORTABLE_BYTES = 10 * 1024 * 1024;
const ALLOWED_HOSTS = new Set(["github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"]);

function allowedDownloadUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return url.protocol === "https:" && (ALLOWED_HOSTS.has(url.hostname) || url.hostname.endsWith(".githubusercontent.com"));
  } catch {
    return false;
  }
}

function download(url, destination, onProgress, redirects = 0) {
  if (!allowedDownloadUrl(url)) return Promise.reject(new Error("The update URL is not an approved GitHub download"));
  if (redirects > 6) return Promise.reject(new Error("The update download redirected too many times"));
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { "User-Agent": "RSDW-Sync-Updater", Accept: "application/octet-stream" }, timeout: 30000 }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        const next = new URL(res.headers.location, url).toString();
        return download(next, destination, onProgress, redirects + 1).then(resolve, reject);
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`GitHub download failed (${res.statusCode})`));
      }
      const total = Number(res.headers["content-length"] || 0);
      if (total > MAX_DOWNLOAD_BYTES) {
        res.resume();
        return reject(new Error("The update is larger than the allowed portable-app limit"));
      }
      let received = 0;
      const output = fs.createWriteStream(destination, { flags: "w" });
      const fail = (error) => {
        output.destroy();
        try { fs.unlinkSync(destination); } catch {}
        reject(error);
      };
      output.on("error", fail);
      res.on("error", fail);
      res.on("data", (chunk) => {
        received += chunk.length;
        if (received > MAX_DOWNLOAD_BYTES) {
          req.destroy(new Error("The update exceeded the allowed portable-app limit"));
          return;
        }
        onProgress?.({ stage: "downloading", received, total, percent: total ? Math.min(99, Math.round((received / total) * 100)) : null });
      });
      res.pipe(output);
      output.on("finish", () => output.close(() => resolve({ received, total })));
    });
    req.on("error", reject);
    req.on("timeout", () => req.destroy(new Error("The update download timed out")));
  });
}

function sha256(file) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256");
    const input = fs.createReadStream(file);
    input.on("error", reject);
    input.on("data", (chunk) => hash.update(chunk));
    input.on("end", () => resolve(hash.digest("hex")));
  });
}

async function verifyPortable(file, expected = {}) {
  const stat = fs.statSync(file);
  if (stat.size < MIN_PORTABLE_BYTES) throw new Error("The downloaded file is too small to be the RSDW portable app");
  if (expected.size && Number(expected.size) !== stat.size) throw new Error("The downloaded update size does not match GitHub");
  const fd = fs.openSync(file, "r");
  try {
    const magic = Buffer.alloc(2);
    fs.readSync(fd, magic, 0, 2, 0);
    if (magic.toString("ascii") !== "MZ") throw new Error("The downloaded update is not a Windows executable");
  } finally {
    fs.closeSync(fd);
  }
  const expectedDigest = String(expected.digest || "").match(/^sha256:([a-f0-9]{64})$/i)?.[1];
  if (expectedDigest) {
    const actual = await sha256(file);
    if (actual.toLowerCase() !== expectedDigest.toLowerCase()) throw new Error("The downloaded update failed its SHA-256 check");
  }
}

function writeApplyScript(workDir) {
  const script = path.join(workDir, "apply-portable-update.ps1");
  const body = `param([int]$LauncherPid,[string]$Source,[string]$Target,[string]$LogFile)
$ErrorActionPreference = 'Stop'
function Write-UpdateLog([string]$Message) { Add-Content -LiteralPath $LogFile -Value (('[{0:o}] ' -f [DateTime]::UtcNow) + $Message) }
$backup = $Target + '.previous'
$deadline = [DateTime]::UtcNow.AddMinutes(2)
try {
  Write-UpdateLog 'Waiting for the current portable launcher to exit.'
  while (Get-Process -Id $LauncherPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 250 }
  while ([DateTime]::UtcNow -lt $deadline) {
    try {
      if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
      Move-Item -LiteralPath $Target -Destination $backup -Force
      try { Move-Item -LiteralPath $Source -Destination $Target -Force }
      catch { Move-Item -LiteralPath $backup -Destination $Target -Force; throw }
      Write-UpdateLog 'Portable executable replaced; launching the new version.'
      Start-Process -FilePath $Target -WorkingDirectory (Split-Path -LiteralPath $Target -Parent)
      Start-Sleep -Seconds 2
      if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
      exit 0
    } catch {
      Write-UpdateLog ('Replacement attempt is waiting: ' + $_.Exception.Message)
      if (-not (Test-Path -LiteralPath $Target) -and (Test-Path -LiteralPath $backup)) { Move-Item -LiteralPath $backup -Destination $Target -Force }
      Start-Sleep -Milliseconds 500
    }
  }
  throw 'Timed out waiting for the portable executable to become replaceable.'
} catch { Write-UpdateLog ('Update failed: ' + $_.Exception.Message); exit 1 }
`;
  fs.mkdirSync(workDir, { recursive: true });
  fs.writeFileSync(script, body, "utf8");
  return script;
}

async function preparePortableUpdate({ url, size, digest, target, parentPid, workDir, onProgress }) {
  if (process.platform !== "win32") throw new Error("Automatic replacement is currently available for the Windows portable app only");
  if (!allowedDownloadUrl(url)) throw new Error("The update URL is not an approved GitHub download");
  if (!target || path.extname(target).toLowerCase() !== ".exe" || !fs.existsSync(target)) throw new Error("The running portable executable could not be located");
  const targetDir = path.dirname(target);
  const probe = path.join(targetDir, `.rsdw-update-write-test-${process.pid}`);
  try { fs.writeFileSync(probe, "ok", { flag: "wx" }); } finally { try { fs.unlinkSync(probe); } catch {} }
  const destination = path.join(targetDir, `.${path.basename(target)}.update-download.exe`);
  try { fs.unlinkSync(destination); } catch {}
  onProgress?.({ stage: "downloading", received: 0, total: Number(size) || 0, percent: 0 });
  await download(url, destination, onProgress);
  onProgress?.({ stage: "verifying", percent: 100 });
  await verifyPortable(destination, { size, digest });
  const script = writeApplyScript(workDir);
  const log = path.join(workDir, "portable-update.log");
  const helper = spawn("powershell.exe", ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script, "-LauncherPid", String(parentPid), "-Source", destination, "-Target", target, "-LogFile", log], {
    detached: true,
    windowsHide: true,
    stdio: "ignore",
  });
  helper.unref();
  onProgress?.({ stage: "restarting", percent: 100 });
  return { ok: true };
}

module.exports = { allowedDownloadUrl, verifyPortable, preparePortableUpdate, MAX_DOWNLOAD_BYTES, MIN_PORTABLE_BYTES };
