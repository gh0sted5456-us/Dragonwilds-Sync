PRAGMA foreign_keys = ON;

ALTER TABLE public_source_runs ADD COLUMN scan_cursor INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public_source_runs ADD COLUMN scan_generation TEXT NOT NULL DEFAULT '';
ALTER TABLE public_source_runs ADD COLUMN scan_started_at INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public_source_runs ADD COLUMN scan_completed_at INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public_source_runs ADD COLUMN scan_total INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_public_source_runs_scan
  ON public_source_runs (last_attempt_at, scan_cursor);
