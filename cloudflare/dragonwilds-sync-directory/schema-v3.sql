-- V3 additive schema. Existing prototype worlds/heartbeat_history tables are
-- intentionally untouched until their deployed schema/data is audited.
CREATE TABLE IF NOT EXISTS installations (
  installation_id TEXT PRIMARY KEY,
  credential_verifier TEXT NOT NULL,
  credential_ciphertext TEXT NOT NULL,
  credential_iv TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  last_seen INTEGER NOT NULL,
  app_version TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL DEFAULT 'client',
  revoked_at INTEGER
);
CREATE TABLE IF NOT EXISTS world_credentials (
  world_id TEXT PRIMARY KEY,
  installation_id TEXT NOT NULL,
  credential_verifier TEXT NOT NULL,
  credential_ciphertext TEXT NOT NULL,
  credential_iv TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  revoked_at INTEGER,
  FOREIGN KEY (installation_id) REFERENCES installations(installation_id)
);
CREATE INDEX IF NOT EXISTS idx_world_credentials_installation ON world_credentials(installation_id);
CREATE TABLE IF NOT EXISTS network_presence_v3 (
  installation_id TEXT PRIMARY KEY,
  last_seen INTEGER NOT NULL,
  app_version TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL DEFAULT 'client'
);
CREATE TABLE IF NOT EXISTS worlds_v3 (
  world_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  cl TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  host_type TEXT NOT NULL DEFAULT 'dedicated',
  player_count INTEGER NOT NULL DEFAULT 0,
  max_players INTEGER NOT NULL DEFAULT 0,
  tags_json TEXT NOT NULL DEFAULT '[]',
  mods_json TEXT NOT NULL DEFAULT '[]',
  badges_json TEXT NOT NULL DEFAULT '[]',
  rules TEXT NOT NULL DEFAULT '',
  connection_json TEXT NOT NULL DEFAULT 'null',
  last_seen INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_worlds_v3_last_seen ON worlds_v3(last_seen DESC);
CREATE TABLE IF NOT EXISTS heartbeat_history_v3 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  world_id TEXT NOT NULL,
  seen_at INTEGER NOT NULL,
  status TEXT NOT NULL,
  player_count INTEGER NOT NULL DEFAULT 0,
  cl TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_heartbeat_history_v3_world_seen ON heartbeat_history_v3(world_id, seen_at DESC);
CREATE TABLE IF NOT EXISTS rate_limits_v3 (
  bucket_id TEXT PRIMARY KEY,
  count INTEGER NOT NULL DEFAULT 0,
  expires_at INTEGER NOT NULL
);

-- Phase 5 public-safe handoff metadata. Credentials, sessions, CSRF state and
-- private administrator tokens are deliberately never stored here. The record
-- is accepted only after the base signed World heartbeat succeeds.
CREATE TABLE IF NOT EXISTS world_remote_admin_v1 (
  world_id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY (world_id) REFERENCES worlds_v3(world_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_world_remote_admin_updated ON world_remote_admin_v1(updated_at DESC);
