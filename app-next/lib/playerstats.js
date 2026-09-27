// lib/playerstats.js
// Derives a per-player login-streak leaderboard from the join history the app already
// records in the `sessions` table (lib/presence.js logs one 'join' per offline→online
// transition). No external mod file or configuration — every server gets this for free.
//
// "Streak" = consecutive LOCAL calendar days on which a player logged in at least once.
// Day boundaries follow the host's local timezone (that's how an operator thinks about
// "days"), computed as a DST-safe integer calendar-day index.
const dbm = require("./db");

const DAY_MS = 86400000;
const WINDOW_DAYS = 400; // how far back to consider — bounds memory on chatty worlds

// created_at (ms) → integer calendar-day index in the host's LOCAL timezone. Built from
// the local Y/M/D via Date.UTC so day-to-day differences are exact whole days even across
// daylight-saving transitions (adding 86_400_000 to a local ms value would not be).
function localDayIndex(ms) {
  const d = new Date(ms);
  return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / DAY_MS;
}

function todayIndex() {
  return localDayIndex(Date.now());
}

// Longest run of consecutive day indices in a sorted, de-duplicated ascending array.
function longestRun(days) {
  let best = 0, run = 0, prev = null;
  for (const d of days) {
    run = prev !== null && d === prev + 1 ? run + 1 : 1;
    if (run > best) best = run;
    prev = d;
  }
  return best;
}

// Current run ending at today or yesterday (so a streak isn't considered broken merely
// because the player hasn't logged in yet today). 0 if the last login was before that.
function currentRun(days) {
  if (!days.length) return 0;
  const today = todayIndex();
  const last = days[days.length - 1];
  if (last !== today && last !== today - 1) return 0;
  let run = 1;
  for (let i = days.length - 2; i >= 0; i--) {
    if (days[i] === days[i + 1] - 1) run++;
    else if (days[i] === days[i + 1]) continue; // dupes already removed, but be safe
    else break;
  }
  return run;
}

// Public: login-streak leaderboard for one world, highest current streak first.
// Returns [{ id, name, lastSeen, firstSeen, totalLogins, currentStreak, longestStreak }].
function loginStats(worldId) {
  const since = Date.now() - WINDOW_DAYS * DAY_MS;
  const rows = dbm.allJoinSessions(worldId, since); // oldest → newest
  const byId = new Map();
  for (const r of rows) {
    // Identity: the stable user id when present, else fall back to a normalized name.
    // (presence.js stores user_id = userId||playerId||name, so it's rarely empty.)
    const name = (r.player_name || "").trim();
    const id = (r.user_id && String(r.user_id).trim()) || (name ? `name:${name.toLowerCase()}` : "");
    if (!id) continue;
    let e = byId.get(id);
    if (!e) { e = { id, name, firstSeen: r.created_at, lastSeen: r.created_at, totalLogins: 0, days: new Set() }; byId.set(id, e); }
    // rows are ascending, so the last write wins → most recent display name + lastSeen.
    e.name = name || e.name;
    e.lastSeen = r.created_at;
    e.totalLogins++;
    e.days.add(localDayIndex(r.created_at));
  }

  const out = [];
  for (const e of byId.values()) {
    const days = [...e.days].sort((a, b) => a - b);
    out.push({
      id: e.id,
      name: e.name,
      firstSeen: e.firstSeen,
      lastSeen: e.lastSeen,
      totalLogins: e.totalLogins,
      currentStreak: currentRun(days),
      longestStreak: longestRun(days),
    });
  }
  out.sort((a, b) =>
    b.currentStreak - a.currentStreak ||
    b.longestStreak - a.longestStreak ||
    b.lastSeen - a.lastSeen
  );
  return out;
}

module.exports = { loginStats, localDayIndex };
