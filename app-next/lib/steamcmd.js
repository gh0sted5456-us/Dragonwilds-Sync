// lib/steamcmd.js  (spec §2 provisioning, §8 update checking)
const fs = require("fs");
const path = require("path");
const os = require("os");
const https = require("https");
const { spawn } = require("child_process");
const { P } = require("./paths");

const DRAGONWILDS_APPID = "4019830";

function steamcmdBinary() {
  const dir = P.steamcmd();
  return os.platform() === "win32"
    ? path.join(dir, "steamcmd.exe")
    : path.join(dir, "steamcmd.sh");
}

function steamcmdInstalled() {
  return fs.existsSync(steamcmdBinary());
}

// Download + unpack the shared SteamCMD once (spec §2 step 2).
async function ensureSteamCmd(onLog = () => {}) {
  if (steamcmdInstalled()) return steamcmdBinary();
  const dir = P.steamcmd();
  const plat = os.platform();
  const url =
    plat === "win32"
      ? "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
      : "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz";
  onLog(`Downloading SteamCMD from ${url}`);
  const archive = path.join(dir, plat === "win32" ? "steamcmd.zip" : "steamcmd.tar.gz");
  await download(url, archive);
  onLog("Extracting SteamCMD...");
  if (plat === "win32") {
    const AdmZip = require("adm-zip");
    new AdmZip(archive).extractAllTo(dir, true);
  } else {
    await run("tar", ["-xzf", archive, "-C", dir]);
    try { fs.chmodSync(steamcmdBinary(), 0o755); } catch {}
  }
  onLog("SteamCMD ready.");
  return steamcmdBinary();
}

// Verify a Palworld server install on disk, independent of SteamCMD's exit code.
// A completed `app_update ... validate` leaves the server binary in place and a
// readable build id in the app manifest — that, not the exit code, is the truth.
function verifyInstall(installDir, targetPlatform) {
  if (!installDir) return { ok: false, buildId: null };
  const plat = targetPlatform || (os.platform() === "win32" ? "windows" : "linux");
  // Check the binary that matches the platform we actually asked for, not
  // "either" — otherwise a stale binary from a previous install on the other
  // platform could make a cross-platform provision look verified when it isn't.
  const expected = plat === "windows"
  ? path.join(installDir, "RSDragonwildsServer.exe")
  : path.join(installDir, "RSDragonwildsServer.sh");
  const hasBinary = fs.existsSync(expected);
  const buildId = readInstalledBuildId(installDir);
  return { ok: hasBinary && !!buildId, buildId, hasBinary };
}

// SteamCMD prints the *reason* a run failed on its own line, then exits non-zero.
// The app's install/update line ("Error! App '2394010' state is 0x… after update
// job: … (Disk write failure)") is the telling one; a generic "Error!/Failed" line
// is the fallback. Keeping the last match of each lets a failure say why, not just a
// number.
// Build regexes dynamically so the app id can be configured via env.
const APP_ERR_RE = new RegExp(`(Error!\\s*App\\s*'?${DRAGONWILDS_APPID}|Failed to install app\\s*'?${DRAGONWILDS_APPID}|state is 0x[0-9a-f]+ after)`, "i");
const ANY_ERR_RE = /(Error!|Failed to install|Disk write failure|No space left|rate limit|Timeout downloading|Invalid Password|No subscription)/i;

// Known SteamCMD exit codes → a short plain-language `name` (used only when SteamCMD
// didn't print its own error line) and an actionable `fix`. The fix is appended after
// whichever "what" we have, so it always reads as a next step rather than restating the
// error. Only the codes users actually hit are mapped; anything else falls back to the
// raw line alone.
const CODE_INFO = {
  8: { name: "disk write failure", fix: "check the install drive has enough free space, and that antivirus or folder permissions aren't blocking SteamCMD from writing" },
  2: { name: "connection or login failure", fix: "check your internet connection and that the install folder isn't locked, then try again" },
  6: { name: "interrupted run", fix: "run the update again" },
};

// Build the human-readable detail for a failed run. Prefer SteamCMD's own error line
// as the "what" (it's the ground truth, e.g. "(Disk write failure)"); fall back to the
// code's name. Append the code's fix as a next step. Avoids restating the same phrase
// twice by never putting the name and the raw line together.
function failDetail(code, errorLine) {
  const line = (errorLine || "").trim();
  const info = CODE_INFO[code];
  const what = line || (info ? `SteamCMD reported a ${info.name}` : "");
  const fix = info ? info.fix : "";
  if (what && fix) return `${what} — ${fix}`;
  return what || fix || "";
}

// Run SteamCMD once. Streams stdout/stderr lines to onLog. Resolves with
// { code, sawSuccess, errorLine } where sawSuccess is true if SteamCMD printed a
// positive completion marker (its own line, regardless of the final exit code) and
// errorLine is the most telling error line seen, or "" if none.
// targetPlatform: "windows" | "linux" (defaults to whatever this host is, so
// existing callers that don't pass it behave exactly as before).
function runSteamCmdOnce(installDir, onLog, targetPlatform) {
  const plat = targetPlatform || (os.platform() === "win32" ? "windows" : "linux");
  return new Promise((resolve, reject) => {
    const bin = steamcmdBinary();
    const args = [
      // Forces which depot SteamCMD fetches, independent of the OS SteamCMD
      // itself runs on — e.g. steamcmd.sh on Linux can pull the Windows build.
      "+@sSteamCmdForcePlatformType", plat,
      "+@sSteamCmdForcePlatformBitness", "64",
      "+force_install_dir", installDir,
      "+login", "anonymous",
      "+app_update", DRAGONWILDS_APPID, "validate",
      "+quit",
    ];
    onLog(`> steamcmd ${args.join(" ")}`);
    let sawSuccess = false;
    let appErr = "";
    let genErr = "";
    const scan = (line) => {
      // Only the app's own success marker counts. The bootstrapper prints
      // "Update complete, launching..." when it finishes updating *itself* — that
      // is not the Palworld install completing, so it must not be treated as one.
    // Success markers for the app install/update use the configured app id.
    if (new RegExp(`Success!\\s*App\\s*'?${DRAGONWILDS_APPID}`, "i").test(line) || new RegExp(`App\\s*'?${DRAGONWILDS_APPID}'?\\s*fully installed`, "i").test(line)) sawSuccess = true;
      else if (APP_ERR_RE.test(line)) appErr = line.trim();
      else if (ANY_ERR_RE.test(line)) genErr = line.trim();
      onLog(line);
    };
    const child = spawn(bin, args, { cwd: P.steamcmd() });
    child.stdout.on("data", (d) => splitLines(d).forEach(scan));
    child.stderr.on("data", (d) => splitLines(d).forEach(scan));
    child.on("error", reject);
    child.on("close", (code) => {
      onLog(`SteamCMD exited with code ${code}`);
      resolve({ code, sawSuccess, errorLine: appErr || genErr || "" });
    });
  });
}

// Install or update a world into its install_dir (spec §2 step 3, §8 step 5).
// Resolves with { ok, code, verified, buildId }. Success is judged by the
// install on disk, not the exit code alone: SteamCMD frequently exits 7 (or 8)
// after a fully successful run — most often when it self-updates mid-run and
// re-execs. In that case we retry once, then trust the verified install.
async function installOrUpdate(installDir, onLog = () => {}, targetPlatform) {
  let last = await runSteamCmdOnce(installDir, onLog, targetPlatform);
  let verified = verifyInstall(installDir, targetPlatform);

  // Benign non-zero exit (self-update re-exec, clean-shutdown quirk): if the run
  // didn't clearly succeed and isn't verified on disk yet, give it one more pass.
  const benign = last.code === 7 || last.code === 8;
  if (last.code !== 0 && !verified.ok && (benign || last.sawSuccess)) {
    onLog(`SteamCMD returned code ${last.code}; retrying once to confirm...`);
    last = await runSteamCmdOnce(installDir, onLog, targetPlatform);
    verified = verifyInstall(installDir, targetPlatform);
  }

  const ok = last.code === 0 || verified.ok || last.sawSuccess;
  if (ok && last.code !== 0) {
    onLog(`Note: SteamCMD exited with code ${last.code}, but the install verified OK — treating as success.`);
  }
  // Only worth a detail string when we're actually reporting a failure.
  const detail = ok ? "" : failDetail(last.code, last.errorLine);
  return { ok, code: last.code, verified: verified.ok, buildId: verified.buildId, detail };
}

// Read the installed build id from the app manifest (spec §2 step 5).
// The manifest lives in different places depending on how the server was
// installed, so we check the known layouts:
//   • app-provisioned (+force_install_dir): <installDir>/steamapps/appmanifest_*.acf
//   • Steam client / SteamCMD default:      <installDir>/../../appmanifest_*.acf
//     (install dir is .../steamapps/common/RSDragonwilds)
function readInstalledBuildId(installDir) {
  if (!installDir) return null;
  const name = `appmanifest_${DRAGONWILDS_APPID}.acf`;
  const candidates = [
    path.join(installDir, "steamapps", name),
    path.join(installDir, "..", "..", name),
    path.join(installDir, "..", name),
  ];
  for (const acf of candidates) {
    try {
      if (!fs.existsSync(acf)) continue;
      const text = fs.readFileSync(acf, "utf8");
      const m = text.match(/"buildid"\s+"(\d+)"/);
      if (m) return m[1];
    } catch {}
  }
  return null;
}

// Query the latest public build id via Steam's public web API (spec §8 step 1).
async function fetchLatestBuildId() {
  const url = `https://api.steamcmd.net/v1/info/${DRAGONWILDS_APPID}`;
  try {
    const json = await getJson(url);
    const bid = json?.data?.[DRAGONWILDS_APPID]?.depots?.branches?.public?.buildid;
    return bid ? String(bid) : null;
  } catch {
    return null;
  }
}

// Where a world stands against the latest public build. Tri-state on purpose: we
// only know a world is current once we've *seen* both build ids, and "unknown"
// (never checked, or Steam unreachable) must not masquerade as up to date — the UI
// still offers Update in that case rather than stranding someone with no way to run it.
//   available -> a newer public build exists
//   current   -> installed build matches the latest public build
//   unknown   -> we can't tell yet
function updateStateOf(w) {
  if (!w || !w.build_id || !w.latest_known_build_id) return "unknown";
  return w.build_id === w.latest_known_build_id ? "current" : "available";
}

// ---- helpers ----
function splitLines(buf) {
  return buf.toString("utf8").split(/\r?\n/).filter((l) => l.length);
}
function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const c = spawn(cmd, args);
    c.on("error", reject);
    c.on("close", (code) => (code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`))));
  });
}
function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        file.close();
        return download(res.headers.location, dest).then(resolve, reject);
      }
      res.pipe(file);
      file.on("finish", () => file.close(resolve));
    }).on("error", (e) => { try { fs.unlinkSync(dest); } catch {} reject(e); });
  });
}
function getJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => { try { resolve(JSON.parse(data)); } catch (e) { reject(e); } });
    }).on("error", reject);
  });
}

module.exports = {
  DRAGONWILDS_APPID, steamcmdBinary, steamcmdInstalled, ensureSteamCmd,
  installOrUpdate, verifyInstall, readInstalledBuildId, fetchLatestBuildId, updateStateOf,
};
