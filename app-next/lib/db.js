// lib/db.js
// The single registry every module reads/writes through (spec §1).
// Uses better-sqlite3 (synchronous, fast, embedded).
const Database = require("./sqlite");
const { P } = require("./paths");
const os = require("os");

let _db = null;

function db() {
  if (_db) return _db;
  _db = new Database(P.db());
  _db.pragma("journal_mode = WAL");
  migrate(_db);
  return _db;
}

// Close the DB cleanly on shutdown so the WASM backend releases its lock
// directory instead of leaving a stale one behind (which would deadlock the
// next launch).
function closeDb() {
  if (_db) { try { _db.close(); } catch {} _db = null; }
}
if (!globalThis.__APP_DB_EXIT_HOOK) {
  globalThis.__APP_DB_EXIT_HOOK = true;
  for (const sig of ["exit", "SIGINT", "SIGTERM", "SIGHUP"]) {
    try { process.on(sig, () => { closeDb(); if (sig !== "exit") process.exit(0); }); } catch {}
  }
}

// SQLite has no "ADD COLUMN IF NOT EXISTS". Next.js prerenders multiple pages
// in parallel worker processes during `next build`, and each one independently
// opens this same file and runs migrations — so two workers can race past the
// `cols.includes()` check at the same time. This makes the ALTER itself safe
// regardless of that race, instead of relying solely on the pre-check.
function addColumnIfMissing(d, sql) {
  try {
    d.exec(sql);
  } catch (e) {
    if (!/duplicate column name/i.test(e.message)) throw e;
  }
}

function migrate(d) {
  d.exec(`
    CREATE TABLE IF NOT EXISTS worlds (
      world_id TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      install_dir TEXT NOT NULL,
      platform TEXT NOT NULL DEFAULT 'linux',   -- 'windows' | 'linux' — depot fetched by SteamCMD
      env_vars TEXT NOT NULL DEFAULT '{}',   -- JSON object of custom process env vars
      wine_binary TEXT NOT NULL DEFAULT 'wine',  -- only used when platform='windows' on a non-Windows host
      wine_prefix TEXT,                       -- custom WINEPREFIX; null = auto per-world default
      wine_launch_flags TEXT NOT NULL DEFAULT '',  -- flags for 'wine' itself, inserted before the .exe path
      game_port INTEGER NOT NULL,
      query_port INTEGER NOT NULL,
      rest_api_port INTEGER NOT NULL,
      rcon_port INTEGER NOT NULL,
      admin_password TEXT NOT NULL DEFAULT '',
      rest_api_enabled INTEGER NOT NULL DEFAULT 1,
      rcon_enabled INTEGER NOT NULL DEFAULT 0,
      process_id INTEGER,
      owner_id TEXT,
      default_world_name TEXT,
      status TEXT NOT NULL DEFAULT 'stopped',
      autostart INTEGER NOT NULL DEFAULT 0,
      crash_guard INTEGER NOT NULL DEFAULT 1,
      build_id TEXT,
      latest_known_build_id TEXT,
      crash_count INTEGER NOT NULL DEFAULT 0,
      extra_args TEXT DEFAULT '',
      created_at INTEGER NOT NULL,
      last_started_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      world_id TEXT,
      kind TEXT NOT NULL,
      message TEXT,
      created_at INTEGER NOT NULL
    );

    -- Who did what from Discord. Its own table rather than events(), because this has
    -- to be filtered by user and action, not just read back as a list of sentences.
    -- Refusals are recorded too: "who tried and was turned away" is the half of an
    -- audit trail that actually matters.
    CREATE TABLE IF NOT EXISTS discord_actions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      world_id TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      action TEXT NOT NULL,
      user_id TEXT NOT NULL,
      user_name TEXT,
      guild_id TEXT,
      result TEXT NOT NULL,        -- ok | denied | error
      detail TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_discord_actions_world_at ON discord_actions(world_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS backups (
      id TEXT PRIMARY KEY,
      world_id TEXT NOT NULL,
      file_path TEXT NOT NULL,
      size_bytes INTEGER,
      reason TEXT,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS schedules (
      id TEXT PRIMARY KEY,
      world_id TEXT NOT NULL,
      job_type TEXT NOT NULL,          -- restart | backup | update | system_message | onscreen_notice
      mode TEXT NOT NULL,              -- interval | daily | minutes | on_join
      interval_hours REAL,             -- for interval mode
      interval_minutes REAL,           -- for minutes mode
      time_of_day TEXT,                -- 'HH:MM' for daily mode
      message TEXT,                    -- text for system_message / onscreen_notice jobs
      join_match TEXT,                 -- player name to match for on_join mode (blank = anyone)
      join_delay_seconds INTEGER,      -- for on_join mode: wait this long after the join before sending
      enabled INTEGER NOT NULL DEFAULT 1,
      last_run INTEGER,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      world_id TEXT NOT NULL,
      user_id TEXT,
      player_name TEXT,
      event TEXT NOT NULL,             -- join | leave
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS deaths (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      world_id TEXT NOT NULL,
      victim TEXT NOT NULL,
      cause TEXT,                  -- EPalDeadType name: Attack | Falling | Drown | ...
      killer TEXT,                 -- resolved display name / player name, or NULL when environmental
      killer_raw TEXT,             -- killer's raw internal codename (creature/npc), kept for re-resolving + new-creature detection
      killer_kind TEXT,            -- creature | player | npc | '' (empty = no killer)
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS app_settings (
      key TEXT PRIMARY KEY,
      value TEXT
    );

    CREATE TABLE IF NOT EXISTS ini_versions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      world_id TEXT NOT NULL,
      content TEXT NOT NULL,
      note TEXT,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS broadcasts (
      id TEXT PRIMARY KEY,
      world_id TEXT NOT NULL,
      message TEXT NOT NULL,
      fire_at INTEGER NOT NULL,     -- epoch ms when it should be broadcast
      created_at INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending'  -- pending | missed
    );

    CREATE TABLE IF NOT EXISTS mods (
      id TEXT PRIMARY KEY,
      world_id TEXT NOT NULL,
      package_name TEXT NOT NULL,
      display_name TEXT,
      workshop_id TEXT,
      version TEXT,
      source TEXT,               -- workshop | manual | local
      folder TEXT,               -- folder name under Mods/Workshop
      is_server INTEGER DEFAULT 1,
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at INTEGER NOT NULL
    );

    -- Remote Access (v2.7.0). A share "code" grants a remote person scoped control of
    -- either the whole app (all worlds) or a single world, limited to an allow-list of
    -- world tabs. The 5-digit code is the credential a guest types at /remote.
    CREATE TABLE IF NOT EXISTS remote_codes (
      id TEXT PRIMARY KEY,
      code TEXT NOT NULL,              -- 5-digit join code
      label TEXT,                      -- optional nickname the admin gives
      scope TEXT NOT NULL,             -- 'full' (all worlds) | 'world' (one world)
      world_id TEXT,                   -- set when scope='world'
      tabs TEXT NOT NULL DEFAULT '[]', -- JSON array of allowed world-tab ids
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at INTEGER NOT NULL,
      last_used_at INTEGER
    );

    -- One row per guest device that has authenticated with a code. The cookie the guest
    -- holds is this token; last_seen_at drives the active/inactive dot in the admin UI.
    CREATE TABLE IF NOT EXISTS remote_sessions (
      token TEXT PRIMARY KEY,
      code_id TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      last_seen_at INTEGER NOT NULL,
      ip TEXT,
      user_agent TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_remote_sessions_code ON remote_sessions(code_id);

    -- Every action a remote guest performs, kept for the per-code audit log. code_snapshot
    -- denormalizes the code + label at action time so the log stays readable after the
    -- code is deleted.
    CREATE TABLE IF NOT EXISTS remote_audit (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code_id TEXT,
      code_snapshot TEXT,
      ts INTEGER NOT NULL,
      action TEXT NOT NULL,
      world_id TEXT,
      detail TEXT,
      ip TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_remote_audit_code_at ON remote_audit(code_id, ts DESC);
  `);

  // ---- lightweight migrations for databases created before newer columns ----
  const cols = d.prepare("PRAGMA table_info(worlds)").all().map((c) => c.name);
  if (!cols.includes("rcon_enabled")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN rcon_enabled INTEGER NOT NULL DEFAULT 0");
  }
  if (!cols.includes("mods_enabled")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN mods_enabled INTEGER NOT NULL DEFAULT 0");
  }
  if (!cols.includes("icon_data")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN icon_data TEXT");   // data URL (small)
  }
  if (!cols.includes("banner_data")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN banner_data TEXT"); // data URL (small)
  }
  if (!cols.includes("accent_color")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN accent_color TEXT");
  }
  if (!cols.includes("community_server")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN community_server INTEGER NOT NULL DEFAULT 0");
  }
  if (!cols.includes("platform")) {
    // Backfill existing rows with the host's own platform — they were
    // provisioned before this feature existed, so that's the correct value.
    const hostPlat = os.platform() === "win32" ? "windows" : "linux";
    addColumnIfMissing(d, `ALTER TABLE worlds ADD COLUMN platform TEXT NOT NULL DEFAULT '${hostPlat}'`);
  }
  if (!cols.includes("env_vars")) {
    addColumnIfMissing(d, `ALTER TABLE worlds ADD COLUMN env_vars TEXT NOT NULL DEFAULT '{}'`);
  }
  if (!cols.includes("wine_binary")) {
    addColumnIfMissing(d, `ALTER TABLE worlds ADD COLUMN wine_binary TEXT NOT NULL DEFAULT 'wine'`);
  }
  if (!cols.includes("wine_prefix")) {
    addColumnIfMissing(d, `ALTER TABLE worlds ADD COLUMN wine_prefix TEXT`);
  }
  if (!cols.includes("wine_launch_flags")) {
    addColumnIfMissing(d, `ALTER TABLE worlds ADD COLUMN wine_launch_flags TEXT NOT NULL DEFAULT ''`);
  }
  // Legacy multithreading launch flags (issue #11): Palworld's engine has handled
  // multithreading on its own since 1.0, so -useperfthreads/-NoAsyncLoadingThread/
  // -UseMultithreadForDS can now hurt more than help on some setups. Default stays
  // on (1) so every existing and new world keeps behaving exactly as before unless
  // someone opts out per world.
  if (!cols.includes("legacy_perf_flags")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN legacy_perf_flags INTEGER NOT NULL DEFAULT 1");
  }
  // Discord webhook moved from a single global setting to per-world (v1.3.1):
  // each world carries its own webhook, notify-on events, and chat-relay flag.
  if (!cols.includes("discord_webhook")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN discord_webhook TEXT NOT NULL DEFAULT ''");
  }
  if (!cols.includes("notify_events")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN notify_events TEXT"); // JSON {kind:bool}; null = all on
  }
  if (!cols.includes("discord_relay_chat")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN discord_relay_chat INTEGER NOT NULL DEFAULT 0");
  }
  // Multiple Discord webhooks with per-event routing (v2.1.0). JSON:
  // { hooks:[{id,name,url}], routes:{start:id,...,chat:id} }. Null = no channels.
  if (!cols.includes("discord_webhooks")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN discord_webhooks TEXT");
    // One-time backfill for people upgrading who were already using Discord: turn
    // their single webhook into one "Default Channel" and route their events to it,
    // so notifications keep working without reconfiguring. Chat is only routed if
    // the chat relay was already on, to preserve their exact prior behaviour. Worlds
    // with no webhook get nothing.
    //
    // An event the user had switched off in the old UI (notify_events {kind:false},
    // where missing/blank means all on) stays off. Routing everything to the webhook
    // regardless — as this did originally — silently turned those notifications back
    // on during the upgrade, with no way to tell it had happened.
    try {
      const rows = d.prepare(
        "SELECT world_id, discord_webhook, discord_relay_chat, notify_events FROM worlds WHERE discord_webhook IS NOT NULL AND discord_webhook <> ''"
      ).all();
      for (const r of rows) {
        const url = String(r.discord_webhook || "").trim();
        if (!url) continue;
        let events = {};
        try { events = (r.notify_events ? JSON.parse(r.notify_events) : null) || {}; } catch { events = {}; }
        const routes = {};
        for (const k of ["start", "stop", "restart", "crash", "backup", "update"]) {
          routes[k] = events[k] === false ? "" : "default";
        }
        routes.chat = r.discord_relay_chat ? "default" : "";
        const cfg = { hooks: [{ id: "default", name: "Default Channel", url }], routes };
        d.prepare("UPDATE worlds SET discord_webhooks=? WHERE world_id=?").run(JSON.stringify(cfg), r.world_id);
      }
    } catch { /* non-fatal — the read-time fallback still covers un-migrated worlds */ }
  }
  // The old global webhook/notify settings are gone now that it's per-world — drop the
  // stale rows so nothing keeps posting to a webhook the UI no longer surfaces.
  try {
    d.exec("DELETE FROM app_settings WHERE key IN ('discordWebhook','notifyEvents','discordRelayChat')");
  } catch {}

  // Player join password (v1.5.0). Distinct from admin_password: this is the
  // ServerPassword players type on the in-game join screen. Empty = open server.
  if (!cols.includes("server_password")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN server_password TEXT NOT NULL DEFAULT ''");
  }
  if (!cols.includes("owner_id")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN owner_id TEXT");
  }
  if (!cols.includes("default_world_name")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN default_world_name TEXT");
  }
  // Pre-shutdown warning countdown (v1.5.0): broadcast timed notices to players
  // before a scheduled/manual restart or update, then hand off to Palworld's
  // native red shutdown countdown.
  if (!cols.includes("warn_enabled")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN warn_enabled INTEGER NOT NULL DEFAULT 0");
  }
  if (!cols.includes("warn_lead_minutes")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN warn_lead_minutes INTEGER NOT NULL DEFAULT 10");
  }
  if (!cols.includes("warn_interval_minutes")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN warn_interval_minutes INTEGER NOT NULL DEFAULT 2");
  }
  if (!cols.includes("warn_message")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN warn_message TEXT NOT NULL DEFAULT 'The server will restart in {minutes} minute(s). Please get to a safe place.'");
  }

  // Per-world Discord bot (v2.5.0). JSON: the user's own bot token, the app id behind
  // it, the one guild it's linked to, and who may use the commands. Null until someone
  // sets a bot up. The token lives here and nowhere else — it is never sent to the UI.
  if (!cols.includes("discord_bot")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN discord_bot TEXT");
  }

  // Per-world custom Discord notification templates (JSON {kind: template}). Blank/absent
  // for a kind means "use the built-in default message". Placeholders like {world},
  // {player} are filled at send time by lib/notify.js.
  if (!cols.includes("notify_templates")) {
    addColumnIfMissing(d, "ALTER TABLE worlds ADD COLUMN notify_templates TEXT NOT NULL DEFAULT '{}'");
  }

  // Pal name mapping removed for RSDW: we keep killer raw text but do not resolve
  // creature codenames to friendly display names. Remove any lingering DB columns
  // related to pal name overrides to avoid confusion; leave existing data untouched.

  // The killer's raw internal codename, kept alongside the resolved display name so a
  // later rename (or a newly-added override) re-labels past deaths, and so Pals not yet
  // in any map can be detected and surfaced for naming. Old rows stay NULL and fall back
  // to their stored display name.
  const dcols = d.prepare("PRAGMA table_info(deaths)").all().map((c) => c.name);
  if (!dcols.includes("killer_raw")) addColumnIfMissing(d, "ALTER TABLE deaths ADD COLUMN killer_raw TEXT");

  // Scheduled-broadcast status (v1.5.0): a broadcast whose time passed while the app
  // was closed is kept and flagged 'missed' instead of firing late or vanishing.
  const bcols = d.prepare("PRAGMA table_info(broadcasts)").all().map((c) => c.name);
  if (!bcols.includes("status")) {
    addColumnIfMissing(d, "ALTER TABLE broadcasts ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'");
  }

  // Scheduled system messages / on-screen notices, and the minutes + on_join
  // trigger modes (v2.x): schedules gain a message, a fine-grained minutes
  // interval, and a player-name matcher for the "when a player joins" trigger.
  const scols = d.prepare("PRAGMA table_info(schedules)").all().map((c) => c.name);
  if (!scols.includes("interval_minutes")) addColumnIfMissing(d, "ALTER TABLE schedules ADD COLUMN interval_minutes REAL");
  if (!scols.includes("message")) addColumnIfMissing(d, "ALTER TABLE schedules ADD COLUMN message TEXT");
  if (!scols.includes("join_match")) addColumnIfMissing(d, "ALTER TABLE schedules ADD COLUMN join_match TEXT");
  // A pause between the join and the message (v2.3.0). Existing on_join rows stay
  // NULL, which the scheduler reads as "send immediately" — their behavior is unchanged.
  if (!scols.includes("join_delay_seconds")) addColumnIfMissing(d, "ALTER TABLE schedules ADD COLUMN join_delay_seconds INTEGER");
  // "Skip the next run" (v2.x): a one-shot flag the scheduler consumes at the next
  // due firing — it skips that occurrence, rebases the timer, and clears itself, so
  // the schedule stays on and resumes on its normal cadence afterward.
  if (!scols.includes("skip_next")) addColumnIfMissing(d, "ALTER TABLE schedules ADD COLUMN skip_next INTEGER NOT NULL DEFAULT 0");
}

// ---- generic settings kv ----
function getSetting(key, fallback = null) {
  const row = db().prepare("SELECT value FROM app_settings WHERE key=?").get(key);
  if (!row) return fallback;
  try { return JSON.parse(row.value); } catch { return row.value; }
}
function setSetting(key, value) {
  db().prepare(
    "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value"
  ).run(key, JSON.stringify(value));
}

// ---- worlds ----
function listWorlds() {
  return db().prepare("SELECT * FROM worlds ORDER BY created_at ASC").all();
}
function getWorld(id) {
  return db().prepare("SELECT * FROM worlds WHERE world_id=?").get(id);
}
function insertWorld(w) {
  db().prepare(`INSERT INTO worlds
    (world_id, display_name, install_dir, platform, env_vars, wine_binary, wine_prefix, wine_launch_flags,
     game_port, query_port, rest_api_port, rcon_port, admin_password, rest_api_enabled,
     owner_id, default_world_name,
     status, autostart, crash_guard, build_id, extra_args, created_at)
    VALUES (@world_id,@display_name,@install_dir,@platform,@env_vars,@wine_binary,@wine_prefix,@wine_launch_flags,
     @game_port,@query_port,@rest_api_port,@rcon_port,@admin_password,@rest_api_enabled,
     @owner_id, @default_world_name,
     @status,@autostart,@crash_guard,@build_id,@extra_args,@created_at)`).run(w);
  return getWorld(w.world_id);
}
function updateWorld(id, patch) {
  const cur = getWorld(id);
  if (!cur) return null;
  const merged = { ...cur, ...patch };
  if (merged.icon_data === undefined) merged.icon_data = null;
  if (merged.banner_data === undefined) merged.banner_data = null;
  if (merged.accent_color === undefined) merged.accent_color = null;
  if (merged.community_server === undefined) merged.community_server = 0;
  if (merged.discord_webhook === undefined || merged.discord_webhook === null) merged.discord_webhook = "";
  if (merged.notify_events === undefined) merged.notify_events = null;
  if (merged.discord_relay_chat === undefined || merged.discord_relay_chat === null) merged.discord_relay_chat = 0;
  if (merged.discord_webhooks === undefined) merged.discord_webhooks = null;
  if (merged.discord_bot === undefined) merged.discord_bot = null;
  if (merged.notify_templates === undefined || merged.notify_templates === null) merged.notify_templates = "{}";
  // Pal name mapping removed for RSDW; keep legacy DB column handling minimal.
  if (merged.server_password === undefined || merged.server_password === null) merged.server_password = "";
  if (merged.warn_enabled === undefined || merged.warn_enabled === null) merged.warn_enabled = 0;
  if (merged.warn_lead_minutes === undefined || merged.warn_lead_minutes === null) merged.warn_lead_minutes = 10;
  if (merged.warn_interval_minutes === undefined || merged.warn_interval_minutes === null) merged.warn_interval_minutes = 2;
  if (merged.warn_message === undefined || merged.warn_message === null) merged.warn_message = "The server will restart in {minutes} minute(s). Please get to a safe place.";
  if (merged.platform === undefined || merged.platform === null) merged.platform = "linux";
  if (merged.env_vars === undefined || merged.env_vars === null) merged.env_vars = "{}";
  if (merged.wine_binary === undefined || merged.wine_binary === null || merged.wine_binary === "") merged.wine_binary = "wine";
  if (merged.wine_prefix === undefined) merged.wine_prefix = null;
  if (merged.wine_launch_flags === undefined || merged.wine_launch_flags === null) merged.wine_launch_flags = "";
  if (merged.legacy_perf_flags === undefined || merged.legacy_perf_flags === null) merged.legacy_perf_flags = 1;
  db().prepare(`UPDATE worlds SET
    display_name=@display_name, install_dir=@install_dir, game_port=@game_port,
    query_port=@query_port, rest_api_port=@rest_api_port, rcon_port=@rcon_port,
    admin_password=@admin_password, rest_api_enabled=@rest_api_enabled,
    rcon_enabled=@rcon_enabled, mods_enabled=@mods_enabled,
    process_id=@process_id, status=@status, autostart=@autostart,
    crash_guard=@crash_guard, build_id=@build_id,
    latest_known_build_id=@latest_known_build_id, crash_count=@crash_count,
    extra_args=@extra_args, last_started_at=@last_started_at,
    icon_data=@icon_data, banner_data=@banner_data, accent_color=@accent_color,
    community_server=@community_server, discord_webhook=@discord_webhook,
    notify_events=@notify_events, discord_relay_chat=@discord_relay_chat,
    discord_webhooks=@discord_webhooks, discord_bot=@discord_bot,
    notify_templates=@notify_templates,
    server_password=@server_password, warn_enabled=@warn_enabled,
    warn_lead_minutes=@warn_lead_minutes, warn_interval_minutes=@warn_interval_minutes,
    warn_message=@warn_message, platform=@platform, env_vars=@env_vars,
    wine_binary=@wine_binary, wine_prefix=@wine_prefix, wine_launch_flags=@wine_launch_flags,
    legacy_perf_flags=@legacy_perf_flags
    WHERE world_id=@world_id`).run(merged);
  return getWorld(id);
}
function deleteWorld(id) {
  db().prepare("DELETE FROM worlds WHERE world_id=?").run(id);
  db().prepare("DELETE FROM backups WHERE world_id=?").run(id);
  db().prepare("DELETE FROM schedules WHERE world_id=?").run(id);
  db().prepare("DELETE FROM events WHERE world_id=?").run(id);
  db().prepare("DELETE FROM sessions WHERE world_id=?").run(id);
  db().prepare("DELETE FROM ini_versions WHERE world_id=?").run(id);
  db().prepare("DELETE FROM broadcasts WHERE world_id=?").run(id);
}

// ---- scheduled broadcasts (v1.5.0) ----
function listBroadcasts(worldId) {
  return db().prepare("SELECT * FROM broadcasts WHERE world_id=? ORDER BY fire_at ASC").all(worldId);
}
function insertBroadcast(b) {
  db().prepare("INSERT INTO broadcasts(id,world_id,message,fire_at,created_at) VALUES(@id,@world_id,@message,@fire_at,@created_at)").run(b);
  return db().prepare("SELECT * FROM broadcasts WHERE id=?").get(b.id);
}
function updateBroadcast(id, patch) {
  const cur = db().prepare("SELECT * FROM broadcasts WHERE id=?").get(id);
  if (!cur) return null;
  const merged = { ...cur, ...patch };
  db().prepare("UPDATE broadcasts SET message=@message, fire_at=@fire_at, status=@status WHERE id=@id").run(merged);
  return db().prepare("SELECT * FROM broadcasts WHERE id=?").get(id);
}
function markBroadcastMissed(id) {
  db().prepare("UPDATE broadcasts SET status='missed' WHERE id=?").run(id);
}
function deleteBroadcast(id) {
  db().prepare("DELETE FROM broadcasts WHERE id=?").run(id);
}
// Pending broadcasts across every world whose time has come. Missed ones are left
// alone (they're kept for the user to reschedule or send manually).
function dueBroadcasts(now) {
  return db().prepare("SELECT * FROM broadcasts WHERE fire_at<=? AND status='pending' ORDER BY fire_at ASC").all(now);
}

// ---- ini version history (v1.5.0 in-app ini editor) ----
const INI_HISTORY_MAX = 100; // keep the most recent N snapshots per world
function insertIniVersion(worldId, content, note) {
  db().prepare("INSERT INTO ini_versions(world_id,content,note,created_at) VALUES(?,?,?,?)")
    .run(worldId, content, note || "", Date.now());
  // prune the oldest beyond the cap so history can't grow without bound
  db().prepare(
    `DELETE FROM ini_versions WHERE world_id=? AND id NOT IN
       (SELECT id FROM ini_versions WHERE world_id=? ORDER BY id DESC LIMIT ?)`
  ).run(worldId, worldId, INI_HISTORY_MAX);
}
function listIniVersions(worldId, limit = 100) {
  // metadata only (no content) — keeps the list response small
  return db().prepare("SELECT id, note, created_at, length(content) AS size FROM ini_versions WHERE world_id=? ORDER BY id DESC LIMIT ?").all(worldId, limit);
}
function getIniVersion(worldId, vid) {
  return db().prepare("SELECT * FROM ini_versions WHERE world_id=? AND id=?").get(worldId, vid);
}

// ---- events ----
function logEvent(worldId, kind, message) {
  db().prepare("INSERT INTO events(world_id,kind,message,created_at) VALUES(?,?,?,?)")
    .run(worldId, kind, message || "", Date.now());
}
function listEvents(worldId, limit = 100) {
  if (worldId) {
    return db().prepare("SELECT * FROM events WHERE world_id=? ORDER BY id DESC LIMIT ?").all(worldId, limit);
  }
  return db().prepare("SELECT * FROM events ORDER BY id DESC LIMIT ?").all(limit);
}

// ---- discord audit ----
function logDiscordAction(row) {
  db().prepare(
    "INSERT INTO discord_actions(world_id,created_at,action,user_id,user_name,guild_id,result,detail) VALUES(?,?,?,?,?,?,?,?)"
  ).run(
    row.worldId, row.at || Date.now(), row.action, String(row.userId || ""),
    row.userName || "", row.guildId || "", row.result || "ok", row.detail || ""
  );
}

// Filtered history. Every filter is optional and they stack, so the UI can narrow by
// any combination of when / who / what without a query per case.
function listDiscordActions(worldId, opts = {}) {
  const where = ["world_id = ?"];
  const args = [worldId];
  if (opts.from) { where.push("created_at >= ?"); args.push(Number(opts.from)); }
  if (opts.to) { where.push("created_at <= ?"); args.push(Number(opts.to)); }
  if (opts.userId) { where.push("user_id = ?"); args.push(String(opts.userId)); }
  if (opts.action) { where.push("action = ?"); args.push(String(opts.action)); }
  if (opts.result) { where.push("result = ?"); args.push(String(opts.result)); }
  const limit = Math.min(Math.max(Number(opts.limit) || 200, 1), 1000);
  args.push(limit);
  return db().prepare(
    `SELECT * FROM discord_actions WHERE ${where.join(" AND ")} ORDER BY id DESC LIMIT ?`
  ).all(...args);
}

// The distinct people who have ever done something, so the filter can offer real
// names instead of asking for an id.
function listDiscordActors(worldId) {
  return db().prepare(
    "SELECT user_id, MAX(user_name) AS user_name, COUNT(*) AS n, MAX(created_at) AS last_at FROM discord_actions WHERE world_id=? GROUP BY user_id ORDER BY last_at DESC"
  ).all(worldId);
}

// ---- backups ----
function insertBackup(b) {
  db().prepare("INSERT INTO backups(id,world_id,file_path,size_bytes,reason,created_at) VALUES(@id,@world_id,@file_path,@size_bytes,@reason,@created_at)").run(b);
}
function listBackups(worldId) {
  return db().prepare("SELECT * FROM backups WHERE world_id=? ORDER BY created_at DESC").all(worldId);
}
function deleteBackupRow(id) {
  db().prepare("DELETE FROM backups WHERE id=?").run(id);
}

// ---- schedules ----
function listSchedules(worldId) {
  if (worldId) return db().prepare("SELECT * FROM schedules WHERE world_id=? ORDER BY created_at ASC").all(worldId);
  return db().prepare("SELECT * FROM schedules ORDER BY created_at ASC").all();
}
function insertSchedule(s) {
  db().prepare(`INSERT INTO schedules(id,world_id,job_type,mode,interval_hours,interval_minutes,time_of_day,message,join_match,join_delay_seconds,enabled,created_at)
    VALUES(@id,@world_id,@job_type,@mode,@interval_hours,@interval_minutes,@time_of_day,@message,@join_match,@join_delay_seconds,@enabled,@created_at)`).run(s);
}
function updateScheduleRun(id, ts) {
  db().prepare("UPDATE schedules SET last_run=? WHERE id=?").run(ts, id);
}
// Arm/disarm the one-shot "skip the next run" flag for a schedule.
function setScheduleSkipNext(id, on) {
  db().prepare("UPDATE schedules SET skip_next=? WHERE id=?").run(on ? 1 : 0, id);
}
function deleteSchedule(id) {
  db().prepare("DELETE FROM schedules WHERE id=?").run(id);
}

// ---- sessions (join/leave) ----
function logSession(worldId, userId, name, event) {
  db().prepare("INSERT INTO sessions(world_id,user_id,player_name,event,created_at) VALUES(?,?,?,?,?)")
    .run(worldId, userId, name, event, Date.now());
}
function listSessions(worldId, limit = 50) {
  // Only presence events belong in the join/leave history. Older builds also wrote
  // chat messages here (event='chat'), which rendered as bogus "leave" entries.
  return db().prepare("SELECT * FROM sessions WHERE world_id=? AND event IN ('join','leave') ORDER BY id DESC LIMIT ?").all(worldId, limit);
}
// All 'join' events since a cutoff (ms), oldest first — feeds the login-streak stats
// (lib/playerstats.js). Bounded by the caller so a very old, chatty world can't load
// an unbounded history into memory.
function allJoinSessions(worldId, sinceMs = 0) {
  return db().prepare(
    "SELECT user_id, player_name, created_at FROM sessions WHERE world_id=? AND event='join' AND created_at>=? ORDER BY created_at ASC"
  ).all(worldId, sinceMs);
}

// ---- deaths (player death tracking, fed by the DWSMDeathRelay UE4SS mod) ----
function logDeath(worldId, d) {
  db().prepare(
    "INSERT INTO deaths(world_id,victim,cause,killer,killer_raw,killer_kind,created_at) VALUES(?,?,?,?,?,?,?)"
  ).run(worldId, d.victim, d.cause || null, d.killer || null, d.killerRaw || null, d.killerKind || null, d.at || Date.now());
}
function listDeaths(worldId, limit = 50) {
  return db().prepare("SELECT * FROM deaths WHERE world_id=? ORDER BY id DESC LIMIT ?").all(worldId, limit);
}

// Distinct killer codenames seen in a world's deaths (creature/npc only) — the raw material
// for "new creature" detection: the caller compares these against the known map + overrides
// and surfaces any that resolve only to a prettified fallback. Scoped to one world.
function seenKillers(worldId) {
  return db().prepare(
    "SELECT killer_raw AS codename, killer_kind AS kind, COUNT(*) AS n, MAX(created_at) AS last_at " +
    "FROM deaths WHERE world_id=? AND killer_raw IS NOT NULL AND killer_kind IN ('pal','npc') " +
    "GROUP BY killer_raw, killer_kind ORDER BY n DESC, last_at DESC"
  ).all(worldId);
}
// Same, across every world — for global new-Pal detection.
function allSeenKillers() {
  return db().prepare(
    "SELECT killer_raw AS codename, killer_kind AS kind, COUNT(*) AS n, MAX(created_at) AS last_at " +
    "FROM deaths WHERE killer_raw IS NOT NULL AND killer_kind IN ('pal','npc') " +
    "GROUP BY killer_raw, killer_kind ORDER BY n DESC, last_at DESC"
  ).all();
}
// Death tallies per victim (most-killed first) — a small leaderboard companion to the
// login-streak stats. Bounded to keep a chatty world from loading everything at once.
function deathCounts(worldId, limit = 50) {
  return db().prepare(
    "SELECT victim, COUNT(*) AS deaths, MAX(created_at) AS last_at FROM deaths WHERE world_id=? GROUP BY victim ORDER BY deaths DESC, last_at DESC LIMIT ?"
  ).all(worldId, limit);
}

// ---- mods ----
function listMods(worldId) {
  return db().prepare("SELECT * FROM mods WHERE world_id=? ORDER BY created_at ASC").all(worldId);
}
function getMod(id) {
  return db().prepare("SELECT * FROM mods WHERE id=?").get(id);
}
function insertMod(m) {
  db().prepare(`INSERT INTO mods
    (id, world_id, package_name, display_name, workshop_id, version, source, folder, is_server, enabled, created_at)
    VALUES (@id,@world_id,@package_name,@display_name,@workshop_id,@version,@source,@folder,@is_server,@enabled,@created_at)`).run(m);
  return getMod(m.id);
}
function updateMod(id, patch) {
  const cur = getMod(id);
  if (!cur) return null;
  const merged = { ...cur, ...patch };
  db().prepare(`UPDATE mods SET
    package_name=@package_name, display_name=@display_name, workshop_id=@workshop_id,
    version=@version, source=@source, folder=@folder, is_server=@is_server, enabled=@enabled
    WHERE id=@id`).run(merged);
  return getMod(id);
}
function deleteMod(id) {
  db().prepare("DELETE FROM mods WHERE id=?").run(id);
}

// ---- remote access (v2.7.0) ----
function insertRemoteCode(c) {
  db().prepare(`INSERT INTO remote_codes(id,code,label,scope,world_id,tabs,enabled,created_at)
    VALUES(@id,@code,@label,@scope,@world_id,@tabs,@enabled,@created_at)`).run(c);
  return getRemoteCode(c.id);
}
function listRemoteCodes() {
  return db().prepare("SELECT * FROM remote_codes ORDER BY created_at DESC").all();
}
function getRemoteCode(id) {
  return db().prepare("SELECT * FROM remote_codes WHERE id=?").get(id);
}
// Look a code up by its digits. Only enabled codes are considered a valid credential —
// a disabled code must behave as if it doesn't exist for login purposes.
function getRemoteCodeByCode(code) {
  return db().prepare("SELECT * FROM remote_codes WHERE code=? AND enabled=1").get(String(code));
}
function updateRemoteCode(id, patch) {
  const cur = getRemoteCode(id);
  if (!cur) return null;
  const merged = { ...cur, ...patch };
  if (merged.enabled === undefined || merged.enabled === null) merged.enabled = 1;
  db().prepare(`UPDATE remote_codes SET
    label=@label, scope=@scope, world_id=@world_id, tabs=@tabs,
    enabled=@enabled, last_used_at=@last_used_at
    WHERE id=@id`).run(merged);
  return getRemoteCode(id);
}
function touchRemoteCode(id, ts) {
  db().prepare("UPDATE remote_codes SET last_used_at=? WHERE id=?").run(ts || Date.now(), id);
}
// Deleting a code drops its live sessions too, but the audit rows are kept (they carry a
// denormalized snapshot) so the record of what that code did survives its deletion.
function deleteRemoteCode(id) {
  db().prepare("DELETE FROM remote_sessions WHERE code_id=?").run(id);
  db().prepare("DELETE FROM remote_codes WHERE id=?").run(id);
}
function createRemoteSession(s) {
  db().prepare(`INSERT INTO remote_sessions(token,code_id,created_at,last_seen_at,ip,user_agent)
    VALUES(@token,@code_id,@created_at,@last_seen_at,@ip,@user_agent)`).run(s);
  return db().prepare("SELECT * FROM remote_sessions WHERE token=?").get(s.token);
}
function getRemoteSession(token) {
  return db().prepare("SELECT * FROM remote_sessions WHERE token=?").get(String(token || ""));
}
function touchRemoteSession(token, ts) {
  db().prepare("UPDATE remote_sessions SET last_seen_at=? WHERE token=?").run(ts || Date.now(), String(token || ""));
}
function deleteRemoteSession(token) {
  db().prepare("DELETE FROM remote_sessions WHERE token=?").run(String(token || ""));
}
function deleteSessionsForCode(codeId) {
  db().prepare("DELETE FROM remote_sessions WHERE code_id=?").run(codeId);
}
function countActiveSessions(codeId, sinceMs) {
  const row = db().prepare("SELECT COUNT(*) AS n FROM remote_sessions WHERE code_id=? AND last_seen_at>=?").get(codeId, sinceMs);
  return row ? row.n : 0;
}
function logRemoteAudit(row) {
  db().prepare(
    "INSERT INTO remote_audit(code_id,code_snapshot,ts,action,world_id,detail,ip) VALUES(?,?,?,?,?,?,?)"
  ).run(
    row.codeId || null, row.codeSnapshot || null, row.ts || Date.now(),
    String(row.action || ""), row.worldId || null, row.detail || null, row.ip || null
  );
}
function listRemoteAudit(codeId, limit = 200) {
  const n = Math.min(Math.max(Number(limit) || 200, 1), 1000);
  return db().prepare("SELECT * FROM remote_audit WHERE code_id=? ORDER BY id DESC LIMIT ?").all(codeId, n);
}

module.exports = {
  db, getSetting, setSetting,
  listWorlds, getWorld, insertWorld, updateWorld, deleteWorld,
  logEvent, listEvents,
  logDiscordAction, listDiscordActions, listDiscordActors,
  insertBackup, listBackups, deleteBackupRow,
  listSchedules, insertSchedule, updateScheduleRun, setScheduleSkipNext, deleteSchedule,
  logSession, listSessions, allJoinSessions,
  logDeath, listDeaths, deathCounts, seenKillers, allSeenKillers,
  insertIniVersion, listIniVersions, getIniVersion,
  listBroadcasts, insertBroadcast, updateBroadcast, markBroadcastMissed, deleteBroadcast, dueBroadcasts,
  listMods, getMod, insertMod, updateMod, deleteMod,
  insertRemoteCode, listRemoteCodes, getRemoteCode, getRemoteCodeByCode,
  updateRemoteCode, touchRemoteCode, deleteRemoteCode,
  createRemoteSession, getRemoteSession, touchRemoteSession, deleteRemoteSession,
  deleteSessionsForCode, countActiveSessions,
  logRemoteAudit, listRemoteAudit,
};
