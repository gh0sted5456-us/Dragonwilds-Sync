CREATE TABLE IF NOT EXISTS runtime_compatibility_reports (
  reporter_hash TEXT NOT NULL,
  component TEXT NOT NULL CHECK(component IN ('ue4ss', 'runeschema')),
  version TEXT NOT NULL,
  rating INTEGER NOT NULL CHECK(rating BETWEEN 0 AND 100),
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (reporter_hash, component, version)
);

CREATE INDEX IF NOT EXISTS idx_runtime_compatibility_version
  ON runtime_compatibility_reports(component, version, updated_at DESC);
