// lib/presence.js
// Background player-presence tracker. Polls each running, REST-enabled world's
// player list on an interval, diffs it against the previous snapshot, records
// join/leave sessions, and fires "join"/"leave" Discord notifications (routed
// per-world like every other event via notify()).
//
// This is the single source of truth for session diffing — the API routes no
// longer diff inline, so there's exactly one place that logs sessions and one
// place that can notify, avoiding double-counting from overlapping polls.
const dbm = require("./db");
const sup = require("./supervisor");
const rest = require("./restclient");
const { notify } = require("./notify");
const { fireJoinSchedules } = require("./scheduler");
const idlestop = require("./idlestop");

const PRESENCE_MS = 10000; // 10s — snappy enough for join/leave, light on the REST API
const g = globalThis;
if (!g.__APP_PRESENCE) g.__APP_PRESENCE = new Map(); // world_id -> Map(uid -> name)  [confirmed present]
if (!g.__APP_PENDING) g.__APP_PENDING = new Map();   // world_id -> Map(uid -> {firstName, ticks})

// Polls to wait before confirming a join when we can't otherwise tell the in-game
// name has loaded. Only players whose name never settles differently ever wait this
// long — and for them the name is correct anyway, so it's a pure delay.
const GRACE_POLLS = 3;

const keyOf = (p) => String(p.userId || p.playerId || p.name || "").trim();
const nameOf = (p, uid) => String((p && p.name) || "").trim() || uid;

// Has this player's in-game character name loaded yet? On connect, Palworld reports
// `name` as the platform account name until the character spawns, then swaps it for
// the in-game name. We treat the name as settled once it differs from the platform
// account name (when the server exposes `accountName`), or once it has changed from
// the name we first saw the player under (the account→character flip).
function nameSettled(p, firstName) {
  const nm = String((p && p.name) || "").trim();
  if (!nm) return false;
  const acct = String((p && p.accountName) || "").trim();
  if (acct && nm !== acct) return true;
  if (firstName != null && nm !== firstName) return true;
  return false;
}

// Diff one world's current player list against its last snapshot. A newly-seen
// player is held in a short "pending" grace window rather than logged immediately,
// so the join is recorded with the loaded in-game name (matching the leave) instead
// of the platform account name the server briefly reports on connect. Only NOTIFIES
// once a baseline exists, so the first observation of a world (app just booted, or
// world just started with players already on) seeds silently.
function observe(world, players) {
  const wid = world.world_id;
  const hadBaseline = g.__APP_PRESENCE.has(wid);
  const confirmed = g.__APP_PRESENCE.get(wid) || new Map();
  const pending = g.__APP_PENDING.get(wid) || new Map();

  const cur = new Map(); // uid -> player object
  for (const p of players || []) {
    const uid = keyOf(p);
    if (uid) cur.set(uid, p);
  }

  // First sight of this world: seed everyone as confirmed silently (no joins).
  if (!hadBaseline) {
    for (const [uid, p] of cur) confirmed.set(uid, nameOf(p, uid));
    g.__APP_PRESENCE.set(wid, confirmed);
    g.__APP_PENDING.set(wid, pending);
    return;
  }

  const joined = [];
  const left = [];

  // Leaves: a confirmed player who's gone. Use their settled (stored) name.
  for (const [uid, name] of confirmed) {
    if (!cur.has(uid)) { dbm.logSession(wid, uid, name, "leave"); left.push(name); confirmed.delete(uid); }
  }
  // A pending player who left before we ever confirmed them (flash-join): drop it
  // silently — no join/leave pair for someone who never really loaded in.
  for (const uid of [...pending.keys()]) if (!cur.has(uid)) pending.delete(uid);

  // Keep confirmed names current, so a later leave shows the in-game name too.
  for (const [uid, p] of cur) if (confirmed.has(uid)) confirmed.set(uid, nameOf(p, uid));

  // Confirm pending joins once the in-game name has settled or the grace cap hits.
  for (const [uid, pend] of pending) {
    const p = cur.get(uid);
    if (!p) continue;
    pend.ticks += 1;
    if (nameSettled(p, pend.firstName) || pend.ticks >= GRACE_POLLS) {
      const name = nameOf(p, uid);
      confirmed.set(uid, name);
      pending.delete(uid);
      dbm.logSession(wid, uid, name, "join");
      joined.push(name);
    }
  }

  // New sightings: start the grace window, don't log/notify yet.
  for (const [uid, p] of cur) {
    if (confirmed.has(uid) || pending.has(uid)) continue;
    pending.set(uid, { firstName: nameOf(p, uid), ticks: 0 });
  }

  g.__APP_PRESENCE.set(wid, confirmed);
  g.__APP_PENDING.set(wid, pending);

  for (const name of joined) {
    notify(wid, "join", `${name} joined ${world.display_name}`, { player: name }).catch(() => {});
    // Fire any "when a player joins" scheduled messages/notices for this join.
    fireJoinSchedules(wid, name).catch(() => {});
  }
  for (const name of left) notify(wid, "leave", `${name} left ${world.display_name}`, { player: name }).catch(() => {});
}

async function tick() {
  if (g.__APP_PRESENCE_BUSY) return;
  g.__APP_PRESENCE_BUSY = true;
  try {
    for (const w of dbm.listWorlds()) {
      const running = sup.isRunning(w.world_id) || sup.pidAlive(w.process_id);
      // Keep the death-file tailer alive for any running world — including servers this
      // app adopted rather than spawned (startWorld only tails what it launches). This is
      // the single guarantee that deaths get picked up regardless of how a server started.
      if (running) { try { sup.ensureDeathTail(w.world_id, w.install_dir); } catch {} }
      else { sup.stopDeathTail(w.world_id); }
      if (!running || !w.rest_api_enabled) {
        // Drop the baseline for stopped worlds so a later restart re-seeds
        // silently — the "stop" event already covers everyone leaving.
        g.__APP_PRESENCE.delete(w.world_id);
        g.__APP_PENDING.delete(w.world_id);
        // A stopped world can't be idle-stopped; drop any pending timer.
        idlestop.clear(w.world_id);
        continue;
      }
      let res;
      try { res = await rest.players(w); }
      catch { continue; } // transient (server busy/booting): keep baseline, no false leaves
      const players = res && res.players ? res.players : [];
      observe(w, players);
      // Idle auto-stop rides the same snapshot: no extra REST call, and it sees the
      // exact player count observe() just diffed.
      try { idlestop.evaluate(w, players); } catch (e) { dbm.logEvent(w.world_id, "scheduler", `Idle auto-stop check failed: ${e.message}`); }
    }
  } finally {
    g.__APP_PRESENCE_BUSY = false;
  }
}

function ensurePresence() {
  if (g.__APP_PRESENCE_TIMER) return;
  g.__APP_PRESENCE_TIMER = setInterval(() => { tick().catch(() => {}); }, PRESENCE_MS);
  tick().catch(() => {}); // seed baselines immediately so the first real change notifies
}

// Is this player in the latest snapshot? Delayed on-join messages use this to
// avoid greeting someone who already left during their delay. The snapshot is at
// most PRESENCE_MS old, so a player who left seconds ago may still read as online
// — close enough for a greeting, and it always settles within one poll.
function isOnline(worldId, name) {
  const want = String(name || "").trim().toLowerCase();
  if (!want) return false;
  const snap = g.__APP_PRESENCE.get(worldId);
  if (snap) for (const n of snap.values()) if (String(n).trim().toLowerCase() === want) return true;
  // A player still in their join grace window is online too (just not yet logged).
  const pend = g.__APP_PENDING.get(worldId);
  if (pend) for (const v of pend.values()) if (String(v.firstName).trim().toLowerCase() === want) return true;
  return false;
}

// How many players the latest snapshot shows for a world (0 if never seen). Idle
// auto-stop uses this as a last-moment guard before it actually stops the server,
// so pending (still-connecting) players count too — don't stop on someone mid-join.
function onlineCount(worldId) {
  const snap = g.__APP_PRESENCE.get(worldId);
  const pend = g.__APP_PENDING.get(worldId);
  return (snap ? snap.size : 0) + (pend ? pend.size : 0);
}

module.exports = { ensurePresence, observe, isOnline, onlineCount };
