PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS world_invites (
  token_hash TEXT PRIMARY KEY,
  world_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  use_count INTEGER NOT NULL DEFAULT 0,
  last_used_at INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(world_id) REFERENCES worlds(world_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_world_invites_world_expiry
  ON world_invites (world_id, expires_at DESC);

CREATE INDEX IF NOT EXISTS idx_world_invites_expiry
  ON world_invites (expires_at);
