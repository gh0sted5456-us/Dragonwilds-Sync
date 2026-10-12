PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS world_publishers (
  world_id TEXT PRIMARY KEY,
  operator_fingerprint TEXT NOT NULL,
  public_key TEXT NOT NULL,
  registered_at INTEGER NOT NULL,
  last_seen INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_world_publishers_operator_world
  ON world_publishers (operator_fingerprint, world_id);
