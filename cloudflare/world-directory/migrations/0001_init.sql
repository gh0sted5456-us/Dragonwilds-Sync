PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS worlds (
  world_id TEXT PRIMARY KEY,
  world_name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  version TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'offline',
  players_current INTEGER NOT NULL DEFAULT 0,
  players_max INTEGER NOT NULL DEFAULT 0,
  tags_json TEXT NOT NULL DEFAULT '[]',
  mods_json TEXT NOT NULL DEFAULT '[]',
  rules_json TEXT NOT NULL DEFAULT '[]',
  badges_json TEXT NOT NULL DEFAULT '[]',
  public_connect_host TEXT NOT NULL DEFAULT '',
  public_connect_port INTEGER,
  is_listed INTEGER NOT NULL DEFAULT 1,
  last_seen INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_worlds_listed_seen
  ON worlds (is_listed, last_seen DESC);

CREATE TABLE IF NOT EXISTS heartbeat_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  world_id TEXT NOT NULL,
  seen_at INTEGER NOT NULL,
  status TEXT NOT NULL,
  players_current INTEGER NOT NULL DEFAULT 0,
  players_max INTEGER NOT NULL DEFAULT 0,
  version TEXT NOT NULL DEFAULT '',
  UNIQUE(world_id, seen_at),
  FOREIGN KEY(world_id) REFERENCES worlds(world_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_history_world_seen
  ON heartbeat_history (world_id, seen_at DESC);
