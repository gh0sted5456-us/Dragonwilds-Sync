const fs = require('fs');

function read(path) {
  return fs.readFileSync(path, 'utf8');
}

function need(source, token, label = token) {
  if (!source.includes(token)) throw new Error(`Phase 4 contract missing: ${label}`);
}

function forbid(source, token, label = token) {
  if (source.includes(token)) throw new Error(`Phase 4 contract violation: ${label}`);
}

const phase = read('backend/phase4_runtime_startup.py');
const cl = read('backend/cl_authority.py');
const runner = read('scripts/run_backend_tests.cjs');
const pkg = read('package.json');

[
  'DragonwildsSync.RuntimeMaterialization.v1',
  'def _tree_signature(',
  'st_mtime_ns',
  'def _sync_tree(',
  'shutil.copy2',
  'def prepare_start(',
  'def process_probe(',
  'def start_dedicated(',
  'prepared_scan_reused',
  'materialization_mode',
  'already_materialized',
  'legacy_live_adoption',
  'unknown_owner_preserved',
  'def _phase4_start_verified(',
  '"resolve_profile", "materialize_save_mods", "generate_runtime_state"',
  '"launch_process", "verify_process", "start_broadcast", "verify_broadcast"',
  'snapshot_client_world',
].forEach((token) => need(phase, token));

// Normal local materialization is intentionally metadata-based. Explicit
// Verify/Repair and network synchronization retain the existing cryptographic
// hash paths; the launch hot path must not hash large mod/PAK trees.
forbid(phase, 'import hashlib', 'no hashing dependency in launch materialization');
forbid(phase, 'sha256(', 'no SHA-256 work in launch materialization');

const startVerifiedStart = phase.indexOf('def _phase4_start_verified(');
const startVerifiedEnd = phase.indexOf('\ndef _install_runtime_manager(', startVerifiedStart);
if (startVerifiedStart < 0 || startVerifiedEnd < 0) throw new Error('Phase 4 authoritative startup function could not be isolated');
const lifecycle = phase.slice(startVerifiedStart, startVerifiedEnd);
forbid(lifecycle, 'scan_mods(', 'runtime manager must not invoke a second deep mod scan');
const ordered = [
  'prepared = prepare(',
  'started = engine.start_dedicated(',
  'process = probe(',
  'watchdog = manager._arm_watchdog(',
  'published = engine.publish(',
  'if not probe(',
  'if not manager.share.status().get("serving")',
];
let cursor = -1;
for (const token of ordered) {
  const at = lifecycle.indexOf(token, cursor + 1);
  if (at < 0) throw new Error(`Phase 4 lifecycle ordering token missing: ${token}`);
  cursor = at;
}

const fastStartStart = phase.indexOf('    def start_dedicated(');
const fastStartEnd = phase.indexOf('\n    def publish(', fastStartStart);
if (fastStartStart < 0 || fastStartEnd < 0) throw new Error('Phase 4 fast dedicated start could not be isolated');
const fastStart = phase.slice(fastStartStart, fastStartEnd);
forbid(fastStart, '.status(', 'dedicated launch must not collect full telemetry merely to verify the process');
need(fastStart, 'popen_hidden(', 'existing hidden-process launcher');
need(fastStart, 'process_probe(', 'lightweight process verification');

need(cl, 'from phase4_runtime_startup import install_phase4_runtime_patches');
need(cl, 'install_phase4_runtime_patches(server_engine_module)');
need(runner, "'backend/test_phase4_runtime_startup.py'");
need(pkg, 'scripts/check_phase4_runtime_startup.cjs');

console.log('Phase 4 runtime materialization / process-before-broadcast contract: OK');
