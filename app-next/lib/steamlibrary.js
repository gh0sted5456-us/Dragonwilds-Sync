// lib/steamlibrary.js
// Locate Steam Workshop content across every Steam library on the machine, so
// Workshop mods resolve no matter which drive Steam lives on.
//
// RuneScape: Dragonwilds' Steam client app id. Dragonwilds does not use the
// Palworld-style Info.json Workshop layout that this project was forked with;
// mods are installed directly into the game tree instead.
// Steam can spread libraries across several drives; they're enumerated in
//   <steamRoot>/steamapps/libraryfolders.vdf   (current format)
//   <steamRoot>/config/libraryfolders.vdf      (legacy format)
// We discover the Steam root(s) from the Windows registry and the common install
// locations, parse those vdf files for every library path, and fold in any
// user-supplied override. The result is the union of places to look — no more
// hardcoding C:.
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const DRAGONWILDS_STEAM_APPID = "1374490";
const DRAGONWILDS_INSTALL_NAMES = ["RuneScape Dragonwilds", "RSDragonwilds"];

// Read a single string value out of the Windows registry, or null on any failure
// (wrong OS, missing key, no reg.exe). Never throws.
function regValue(hive, key, name) {
  try {
    const out = execFileSync("reg", ["query", `${hive}\\${key}`, "/v", name], {
      encoding: "utf8",
      windowsHide: true,
      stdio: ["ignore", "pipe", "ignore"],
    });
    // A value line looks like:  "    SteamPath    REG_SZ    c:/program files (x86)/steam"
    const m = out.match(new RegExp(name + "\\s+REG_\\w+\\s+(.+)", "i"));
    return m ? m[1].trim() : null;
  } catch {
    return null;
  }
}

// Steam install roots reported by the registry (Windows only).
function registrySteamRoots() {
  const roots = [];
  const hkcu = regValue("HKCU", "Software\\Valve\\Steam", "SteamPath");
  const hklm = regValue("HKLM", "SOFTWARE\\Wow6432Node\\Valve\\Steam", "InstallPath");
  for (const r of [hkcu, hklm]) if (r) roots.push(path.normalize(r));
  return roots;
}

// Every Steam install root we can find: registry first, then the well-known
// default locations. Only directories that actually exist are returned.
function discoverSteamRoots() {
  const guesses = [
    ...registrySteamRoots(),
    path.join("C:", "Program Files (x86)", "Steam"),
    path.join("C:", "Program Files", "Steam"),
  ];
  return uniqueExistingDirs(guesses);
}

// Pull every library path out of a libraryfolders.vdf. Handles both the current
// format (`"path"  "D:\\SteamLibrary"`) and the legacy one (`"1"  "D:\\..."`).
function parseLibraryFoldersVdf(vdfPath) {
  let raw;
  try { raw = fs.readFileSync(vdfPath, "utf8"); } catch { return []; }
  const out = [];
  const unescape = (s) => s.replace(/\\\\/g, "\\");
  let m;
  const pathRe = /"path"\s+"([^"]+)"/gi;          // current format
  while ((m = pathRe.exec(raw))) out.push(unescape(m[1]));
  const legacyRe = /^\s*"\d+"\s+"([^"]+)"/gim;     // legacy numeric keys
  while ((m = legacyRe.exec(raw))) out.push(unescape(m[1]));
  return out;
}

// The union of Steam library folders on the machine, plus any user override.
// Each returned entry is a directory that (usually) contains a `steamapps` folder.
function discoverLibraries(override) {
  const libs = [];
  if (override) libs.push(path.normalize(override));
  for (const root of discoverSteamRoots()) {
    libs.push(root);
    for (const vdf of [
      path.join(root, "steamapps", "libraryfolders.vdf"),
      path.join(root, "config", "libraryfolders.vdf"),
    ]) {
      for (const lib of parseLibraryFoldersVdf(vdf)) libs.push(path.normalize(lib));
    }
  }
  return uniqueExistingDirs(libs);
}

function readSteamInstallDir(library) {
  const manifest = path.join(library, "steamapps", `appmanifest_${DRAGONWILDS_STEAM_APPID}.acf`);
  let raw;
  try { raw = fs.readFileSync(manifest, "utf8"); } catch { return null; }
  const match = raw.match(/"installdir"\s+"([^"]+)"/i);
  return match ? path.join(library, "steamapps", "common", match[1].replace(/\\\\/g, "\\")) : null;
}

// Accept the game root itself, a Steam library/root, or any folder inside the
// game install. Return the canonical game root when its Unreal project tree is
// present. This makes the folder picker forgiving while still rejecting random
// directories that would otherwise appear to work but always detect zero mods.
function normalizeGameInstall(input) {
  if (!input) return null;
  let current = path.resolve(String(input));
  try { if (!fs.statSync(current).isDirectory()) return null; } catch { return null; }

  const candidates = [current];
  const fromManifest = readSteamInstallDir(current);
  if (fromManifest) candidates.push(fromManifest);
  if (path.basename(current).toLowerCase() === "steamapps") {
    const lib = path.dirname(current);
    const p = readSteamInstallDir(lib);
    if (p) candidates.push(p);
  }
  for (const name of DRAGONWILDS_INSTALL_NAMES) {
    candidates.push(path.join(current, "steamapps", "common", name));
    candidates.push(path.join(current, "common", name));
  }

  // Also walk upward so selecting Binaries, Content, Paks, or ~mods works.
  let parent = current;
  for (let i = 0; i < 8; i++) {
    candidates.push(parent);
    const next = path.dirname(parent);
    if (next === parent) break;
    parent = next;
  }

  for (const candidate of candidates) {
    const project = path.join(candidate, "RSDragonwilds");
    if (fs.existsSync(path.join(project, "Binaries")) && fs.existsSync(path.join(project, "Content"))) {
      return path.normalize(candidate);
    }
  }
  return null;
}

function discoverGameInstalls(override) {
  const candidates = [];
  if (override) candidates.push(override);
  for (const library of discoverLibraries()) {
    const manifestInstall = readSteamInstallDir(library);
    if (manifestInstall) candidates.push(manifestInstall);
    for (const name of DRAGONWILDS_INSTALL_NAMES) {
      candidates.push(path.join(library, "steamapps", "common", name));
    }
  }
  const normalized = candidates.map(normalizeGameInstall).filter(Boolean);
  return [...new Map(normalized.map((p) => [p.toLowerCase(), p])).values()];
}

function filesWithExtensions(dir, extensions) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return []; }
  const wanted = new Set(extensions.map((x) => x.toLowerCase()));
  return entries.filter((e) => e.isFile() && wanted.has(path.extname(e.name).toLowerCase())).map((e) => path.join(dir, e.name));
}

// Inventory every established Dragonwilds mod layout beneath a client install.
// A logical Pak mod is grouped by basename so its .pak/.utoc/.ucas companions are
// shown as one entry. UE4SS and RuneSchema mods are folder-based.
function scanGameMods(input) {
  const installDir = normalizeGameInstall(input);
  if (!installDir) throw new Error("Choose the RuneScape: Dragonwilds Steam or PC Game Pass folder containing RSDragonwilds\\Binaries and RSDragonwilds\\Content.");
  const project = path.join(installDir, "RSDragonwilds");
  const detected = [];

  for (const folderName of ["~mods", "LogicMods"]) {
    const dir = path.join(project, "Content", "Paks", folderName);
    const groups = new Map();
    for (const file of filesWithExtensions(dir, [".pak", ".utoc", ".ucas", ".sig"])) {
      const ext = path.extname(file).toLowerCase();
      const name = path.basename(file, ext);
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(file);
    }
    for (const [name, files] of groups) detected.push({ key: `pak:${folderName.toLowerCase()}:${name.toLowerCase()}`, name, type: "pak", location: folderName, path: dir, files, syncEligible: true });
  }

  for (const platform of ["Win64", "WinGDK"]) {
    const winDir = path.join(project, "Binaries", platform);
    const ue4ssMods = path.join(winDir, "ue4ss", "Mods");
    let entries = [];
    try { entries = fs.readdirSync(ue4ssMods, { withFileTypes: true }); } catch { /* absent */ }
    for (const entry of entries) {
      if (!entry.isDirectory() || ["shared", "bpmodloadermod"].includes(entry.name.toLowerCase())) continue;
      const type = entry.name.toLowerCase() === "runeschema" ? "framework" : "ue4ss";
      detected.push({ key: `${type}:${platform.toLowerCase()}:${entry.name.toLowerCase()}`, name: entry.name, type, location: platform, path: path.join(ue4ssMods, entry.name), files: [], syncEligible: type === "ue4ss" });
    }

    const schemaDir = path.join(ue4ssMods, "RuneSchema", "mods");
    try {
      for (const entry of fs.readdirSync(schemaDir, { withFileTypes: true })) {
        if (entry.isDirectory() || entry.isFile()) detected.push({ key: `runeschema:${platform.toLowerCase()}:${entry.name.toLowerCase()}`, name: entry.name, type: "runeschema", location: platform, path: path.join(schemaDir, entry.name), files: [], syncEligible: true });
      }
    } catch { /* absent */ }

    const loaders = filesWithExtensions(winDir, [".dll"]).filter((file) => /^(dwmapi|ue4ss|xinput1_3|version|winmm)\.dll$/i.test(path.basename(file)));
    for (const file of loaders) detected.push({ key: `binary:${platform.toLowerCase()}:${path.basename(file).toLowerCase()}`, name: path.basename(file), type: "binary", location: platform, path: file, files: [file], syncEligible: false });
  }
  return { installDir, mods: detected };
}

// Given a base the caller pointed us at (a Steam root, a library folder, the
// workshop content dir, or the item folder itself), enumerate the concrete item
// directories worth checking. Being generous here means the user can pick almost
// anything sensible in the folder picker and it still resolves.
function itemCandidates(base, workshopId) {
  const id = String(workshopId);
  return [
    base,                                                                         // already the item folder
    path.join(base, id),                                                          // base = .../content/1623730
    path.join(base, "workshop", "content", DRAGONWILDS_STEAM_APPID, id),
    path.join(base, "steamapps", "workshop", "content", DRAGONWILDS_STEAM_APPID, id),
  ];
}

// Resolve a subscribed Workshop item to its on-disk folder. Searches the override
// (if any) first, then every discovered Steam library. Returns the folder that
// exists and holds an Info.json, plus the full list of places we looked (handy for
// a precise "not found, here's where I searched" error).
function resolveWorkshopItem(workshopId, override) {
  const searched = [];
  for (const base of discoverLibraries(override)) {
    for (const cand of itemCandidates(base, workshopId)) {
      searched.push(cand);
      if (fs.existsSync(path.join(cand, "Info.json"))) return { path: cand, searched };
    }
  }
  return { path: null, searched };
}

function uniqueExistingDirs(paths) {
  const seen = new Set();
  const out = [];
  for (const p of paths) {
    if (!p) continue;
    const key = path.normalize(p).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    try { if (fs.statSync(p).isDirectory()) out.push(path.normalize(p)); } catch { /* skip */ }
  }
  return out;
}

module.exports = {
  DRAGONWILDS_STEAM_APPID,
  discoverSteamRoots,
  discoverLibraries,
  normalizeGameInstall,
  discoverGameInstalls,
  scanGameMods,
  resolveWorkshopItem,
};
