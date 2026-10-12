-- Global retention searches by timestamp, not by World. The existing
-- (world_id, seen_at) index cannot efficiently serve this predicate.
CREATE INDEX IF NOT EXISTS idx_heartbeat_history_seen_at
  ON heartbeat_history (seen_at);
