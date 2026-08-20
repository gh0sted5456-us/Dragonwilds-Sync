PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS public_source_worlds (
  source_id TEXT NOT NULL,
  source_world_id TEXT NOT NULL,
  source_name TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  world_name TEXT NOT NULL,
  server_name TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  country_code TEXT NOT NULL DEFAULT '',
  country_name TEXT NOT NULL DEFAULT '',
  version TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'offline',
  players_current INTEGER NOT NULL DEFAULT 0,
  players_max INTEGER NOT NULL DEFAULT 0,
  tags_json TEXT NOT NULL DEFAULT '[]',
  badges_json TEXT NOT NULL DEFAULT '[]',
  public_connect_host TEXT NOT NULL DEFAULT '',
  public_connect_port INTEGER,
  password_protected INTEGER NOT NULL DEFAULT 0,
  first_seen INTEGER NOT NULL DEFAULT 0,
  last_seen INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  refresh_token TEXT NOT NULL DEFAULT '',
  is_listed INTEGER NOT NULL DEFAULT 1,
  updated_at INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (source_id, source_world_id)
);

CREATE INDEX IF NOT EXISTS idx_public_source_worlds_listed_seen
  ON public_source_worlds (is_listed, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_public_source_worlds_endpoint
  ON public_source_worlds (public_connect_host, public_connect_port);

CREATE INDEX IF NOT EXISTS idx_public_source_worlds_name_version
  ON public_source_worlds (world_name COLLATE NOCASE, version COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS public_source_runs (
  source_id TEXT PRIMARY KEY,
  last_attempt_at INTEGER NOT NULL DEFAULT 0,
  last_success_at INTEGER NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  last_count INTEGER NOT NULL DEFAULT 0
);
