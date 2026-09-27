// lib/prereqs.js
// Windows runtime prerequisites for the Palworld dedicated server. A fresh Windows box
// often lacks the MSVC++ and DirectX runtimes the game server executable needs, and without them the
// process dies at launch with a "The following component(s) are required" dialog — which
// the app otherwise only sees as a generic "exited unexpectedly".
//
// Detection is best-effort file presence in System32 (the 64-bit runtimes the 64-bit
// server loads). Installation downloads Microsoft's official VC++ redistributable and
// runs Epic's own prerequisite installer (shipped in the Palworld depot by SteamCMD),
// both elevated via a UAC prompt. Non-Windows hosts always report OK.
const fs = require("fs");
const path = require("path");
const os = require("os");
const https = require("https");
const { spawn } = require("child_process");
const { P } = require("./paths");

const VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe";

function system32() {
  return path.join(process.env.SystemRoot || process.env.windir || "C:\\Windows", "System32");
}
function anyExists(dir, names) {
  return names.every((n) => {
    try { return fs.existsSync(path.join(dir, n)); } catch { return false; }
  });
}

// Presence check for the two runtime families. Windows-only; elsewhere → ok.
function check() {
  if (os.platform() !== "win32") return { supported: false, vcredist: true, directx: true, ok: true };
  const sys = system32();
  // MSVC++ 2015-2022 x64 runtime.
  const vcredist = anyExists(sys, ["vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"]);
  // Legacy DirectX runtime DLLs Unreal Engine games load (the June 2010 redist / UE prereq).
  const directx = anyExists(sys, ["XINPUT1_3.dll", "X3DAudio1_7.dll", "D3DCompiler_43.dll"]);
  return { supported: true, vcredist, directx, ok: vcredist && directx };
}

// Epic's prerequisite installer, shipped inside the Palworld depot by SteamCMD. Installs
// exactly what the UE build needs (VC++ + DirectX). Returns its path if present.
function bundledPrereqPath(installDir) {
  if (!installDir) return null;
  const p = path.join(installDir, "Engine", "Extras", "Redist", "en-us", "UEPrereqSetup_x64.exe");
  try { return fs.existsSync(p) ? p : null; } catch { return null; }
}

function downloadFile(url, dest, onLog = () => {}) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        file.close();
        return downloadFile(res.headers.location, dest, onLog).then(resolve, reject);
      }
      if (res.statusCode !== 200) { file.close(); return reject(new Error(`HTTP ${res.statusCode} downloading ${url}`)); }
      res.pipe(file);
      file.on("finish", () => file.close(resolve));
    }).on("error", (e) => { try { fs.unlinkSync(dest); } catch {} reject(e); });
  });
}

// Run an installer elevated. Start-Process -Verb RunAs raises the UAC prompt; -Wait blocks
// until it finishes; -PassThru + $p.ExitCode surfaces the result. A declined UAC prompt
// makes Start-Process throw, which we surface as a clear message.
function runElevated(exe, args, onLog = () => {}) {
  return new Promise((resolve, reject) => {
    const argList = args.map((a) => `'${String(a).replace(/'/g, "''")}'`).join(",");
    const ps =
      `$ErrorActionPreference='Stop';` +
      `try { $p = Start-Process -FilePath '${exe.replace(/'/g, "''")}'` +
      (argList ? ` -ArgumentList ${argList}` : "") +
      ` -Verb RunAs -Wait -PassThru; exit $p.ExitCode } ` +
      `catch { Write-Error $_; exit 1223 }`; // 1223 = ERROR_CANCELLED (UAC declined)
    onLog(`> ${path.basename(exe)} ${args.join(" ")} (elevated)`);
    const child = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", ps]);
    child.stdout.on("data", (d) => String(d).split(/\r?\n/).filter(Boolean).forEach(onLog));
    child.stderr.on("data", (d) => String(d).split(/\r?\n/).filter(Boolean).forEach(onLog));
    child.on("error", reject);
    child.on("close", (code) => resolve(code));
  });
}

// Install the missing prerequisites. onLog streams to the job log; onProgress(phase,pct)
// updates the download bar. Throws on hard failure; a declined UAC is reported per-step.
async function installPrereqs(installDir, { onLog = () => {}, onProgress = () => {} } = {}) {
  if (os.platform() !== "win32") throw new Error("Prerequisite install is only needed on Windows.");
  const before = check();
  const staging = P.staging();
  try { fs.mkdirSync(staging, { recursive: true }); } catch {}
  const results = [];

  // 1) MSVC++ redistributable — download from Microsoft, run silent + elevated.
  if (!before.vcredist) {
    onProgress("download", null);
    onLog("Downloading Microsoft Visual C++ redistributable…");
    const dest = path.join(staging, "vc_redist.x64.exe");
    await downloadFile(VC_REDIST_URL, dest, onLog);
    onProgress("install", null);
    onLog("Installing Visual C++ runtime (accept the Windows prompt)…");
    const code = await runElevated(dest, ["/install", "/quiet", "/norestart"], onLog);
    results.push({ name: "Visual C++", code });
    try { fs.unlinkSync(dest); } catch {}
  }

  // 2) DirectX — run Epic's bundled prerequisite installer (also covers VC++). It's the
  //    canonical "install what this UE build needs", already on disk from SteamCMD.
  if (!before.directx) {
    const bundled = bundledPrereqPath(installDir);
    if (bundled) {
      onProgress("install", null);
      onLog("Installing DirectX runtime via the bundled Unreal prerequisites (accept the Windows prompt)…");
      const code = await runElevated(bundled, ["/quiet"], onLog);
      results.push({ name: "DirectX (UE prereq)", code });
    } else {
      onLog("Bundled UEPrereqSetup_x64.exe not found — open the world's install folder and run it, or install the DirectX End-User Runtime from Microsoft.");
      results.push({ name: "DirectX", code: -1, note: "bundled installer missing" });
    }
  }

  const after = check();
  for (const r of results) onLog(`${r.name}: exit ${r.code}${r.note ? ` (${r.note})` : ""}`);
  onLog(after.ok ? "All required runtimes are now present." : "Some runtimes still appear missing — a reboot may be required, or run the installers manually.");
  return { ok: after.ok, before, after, results, vcRedistUrl: VC_REDIST_URL };
}

module.exports = { check, bundledPrereqPath, installPrereqs, VC_REDIST_URL };
