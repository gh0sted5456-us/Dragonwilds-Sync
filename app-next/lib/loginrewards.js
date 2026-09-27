// lib/loginrewards.js
// Reads the DailyLoginRewards UE4SS mod's players.json so the app can show the SAME
// login-streak numbers the mod awards rewards from — keeping the two "in sync" instead
// of the app's own calendar-day streak (lib/playerstats.js) disagreeing with the mod.
//
// The mod tracks streaks off a rolling window of each player's own last login (UNIX
// seconds), not calendar days: a login within 24h changes nothing, 24–48h bumps the
// streak, past 48h resets it. Rather than reimplement (and drift from) that, we just
// read the numbers the mod already computed. File shape:
//     { "Randy": { "lastRewardUnix": 1784470178, "streak": 6 }, ... }
// keyed by in-game display name.
const fs = require("fs");
const path = require("path");
const dbm = require("./db");
const ue4ss = require("./ue4ss");
const { P } = require("./paths");

// A players.json is a tiny flat map; anything past this is not the file we expect and
// reading it would only risk memory/parse cost on a wrong or hostile path.
const MAX_BYTES = 2 * 1024 * 1024; // 2 MiB
// Per-world manual override for the file path, stored as a plain app setting keyed by
// world id (blank/unset = auto-detect under the world's UE4SS Mods folder).
const PATH_SETTING = (worldId) => `loginRewardsPath:${worldId}`;

function getPathOverride(worldId) {
  const v = dbm.getSetting(PATH_SETTING(worldId), null);
  return v && String(v).trim() ? String(v).trim() : null;
}
function setPathOverride(worldId, p) {
  const v = p && String(p).trim() ? String(p).trim() : null;
  dbm.setSetting(PATH_SETTING(worldId), v);
  return v;
}

// Find the mod's players.json under the world's UE4SS Mods folder. Mod folder naming
// varies between installs (DailyLoginRewards, DailyRewards, a fork's name…), so rather
// than hard-code one folder we scan each mod folder shallowly for a players.json. We
// look in the folder root and its Scripts subfolder — the two places UE4SS Lua mods
// keep runtime state — and stop at the first match. Returns an absolute path or null.
function autodetect(installDir) {
  let modsRoot;
  try { modsRoot = ue4ss.modsDir(installDir); } catch { return null; }
  let entries;
  try { entries = fs.readdirSync(modsRoot, { withFileTypes: true }); } catch { return null; }
  // Prefer a folder that looks like the reward mod, but fall back to any that has the file.
  const looksLikeReward = (n) => /reward|login|daily/i.test(n);
  const dirs = entries.filter((e) => e.isDirectory()).map((e) => e.name);
  const ordered = [...dirs.filter(looksLikeReward), ...dirs.filter((n) => !looksLikeReward(n))];
  for (const name of ordered) {
    for (const rel of ["players.json", path.join("Scripts", "players.json")]) {
      const candidate = path.join(modsRoot, name, rel);
      try { if (fs.statSync(candidate).isFile()) return candidate; } catch { /* keep looking */ }
    }
  }
  return null;
}

// Resolve the file we'll read for a world: explicit override first, else auto-detect.
function resolvePath(world) {
  const override = getPathOverride(world.world_id);
  if (override) return { path: override, source: "override" };
  const hit = world.install_dir ? autodetect(world.install_dir) : null;
  return { path: hit, source: hit ? "auto" : null };
}

// Turn parsed JSON into a clean, bounded list of {name, streak, lastRewardUnix}. Skips
// entries that aren't the expected shape rather than throwing, so one bad row (or a file
// that's almost-but-not-quite this mod's) can't blank the whole leaderboard.
function normalize(obj) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return [];
  const out = [];
  for (const [name, v] of Object.entries(obj)) {
    const nm = String(name || "").trim();
    if (!nm || !v || typeof v !== "object") continue;
    const streak = Number(v.streak);
    // lastRewardUnix is seconds in the file; expose it as ms so callers match the app's
    // millisecond timestamps everywhere else.
    const unix = Number(v.lastRewardUnix);
    if (!Number.isFinite(streak) || streak < 0) continue;
    out.push({
      name: nm,
      streak: Math.floor(streak),
      lastReward: Number.isFinite(unix) && unix > 0 ? Math.round(unix * 1000) : null,
    });
  }
  return out;
}

// Parse a players.json file safely. Returns { players } or throws a friendly error the
// API can surface. Separated from readStreaks so it can also validate an uploaded file.
function parseFile(filePath) {
  let stat;
  try { stat = fs.statSync(filePath); } catch { throw new Error("File not found."); }
  if (!stat.isFile()) throw new Error("That path is not a file.");
  if (stat.size > MAX_BYTES) throw new Error("File is too large to be a players.json.");
  let raw;
  try { raw = fs.readFileSync(filePath, "utf8"); } catch (e) { throw new Error(`Couldn't read the file: ${e.message}`); }
  return { players: normalize(parseText(raw)) };
}

// Parse raw JSON text (from a file or an upload). Throws on invalid JSON.
function parseText(text) {
  if (Buffer.byteLength(text, "utf8") > MAX_BYTES) throw new Error("File is too large to be a players.json.");
  let obj;
  try { obj = JSON.parse(text); } catch { throw new Error("File is not valid JSON."); }
  return obj;
}

// Public: read the mod streaks for a world. Never throws — a missing/unreadable file is
// a normal state (mod not installed), reported via found:false so the UI can hint at it.
// Returns { found, path, source, players: [{name, streak, lastReward}], error }.
function readStreaks(world) {
  const { path: filePath, source } = resolvePath(world);
  if (!filePath) return { found: false, path: null, source: null, players: [], error: null };
  try {
    const { players } = parseFile(filePath);
    return { found: true, path: filePath, source, players, error: null };
  } catch (e) {
    // The path resolved but the file is bad/unreadable — surface it so the operator can fix
    // the path rather than silently showing nothing.
    return { found: false, path: filePath, source, players: [], error: e.message };
  }
}

// Upload fallback: validate raw players.json text, park it under the app's data dir,
// and point this world's override at it. Used when the operator's mod folder isn't on
// this machine (remote host). Throws on invalid content so a bad upload is rejected
// before it replaces a working path. Returns { path, count }.
function saveUpload(worldId, text) {
  const players = normalize(parseText(text)); // throws on bad JSON / too large
  if (!players.length) throw new Error("No valid player entries found in that file.");
  const dest = path.join(P.loginRewards(), `${worldId}.json`);
  fs.writeFileSync(dest, typeof text === "string" ? text : JSON.stringify(text), "utf8");
  setPathOverride(worldId, dest);
  return { path: dest, count: players.length };
}

module.exports = {
  readStreaks,
  getPathOverride, setPathOverride,
  resolvePath, autodetect,
  parseFile, parseText, normalize,
  saveUpload,
  MAX_BYTES,
};
