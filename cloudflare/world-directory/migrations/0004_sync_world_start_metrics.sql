-- Persistent public metrics for Dragonwilds Sync World launches.
-- Existing listed Sync Worlds seed the tracker once so the counter does not
-- begin below the number of Worlds already known when this migration lands.

CREATE TABLE IF NOT EXISTS network_counters (
  counter_key TEXT PRIMARY KEY,
  counter_value INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO network_counters (counter_key, counter_value, updated_at)
SELECT 'total_sync_world_starts', COUNT(*), CAST(strftime('%s','now') AS INTEGER)
FROM worlds;

CREATE TABLE IF NOT EXISTS sync_world_start_state (
  world_id TEXT PRIMARY KEY,
  last_start_id TEXT NOT NULL DEFAULT '',
  last_seen INTEGER NOT NULL DEFAULT 0,
  last_status TEXT NOT NULL DEFAULT '',
  starts INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT 0
);

-- Seed current Worlds as one already-known start each. Future accepted
-- heartbeats advance this state and increment the network counter only on a
-- detected new runtime session/start transition.
INSERT OR IGNORE INTO sync_world_start_state (
  world_id, last_start_id, last_seen, last_status, starts, updated_at
)
SELECT world_id, '', last_seen, status, 1, updated_at
FROM worlds;

CREATE TABLE IF NOT EXISTS sync_world_start_events (
  world_id TEXT NOT NULL,
  start_id TEXT NOT NULL,
  started_at INTEGER NOT NULL,
  PRIMARY KEY (world_id, start_id)
);

CREATE INDEX IF NOT EXISTS idx_sync_world_start_events_started_at
  ON sync_world_start_events(started_at DESC);
