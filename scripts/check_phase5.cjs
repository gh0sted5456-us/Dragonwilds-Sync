const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const failures = [];
const read = rel => fs.readFileSync(path.join(root, rel), 'utf8');
const need = (rel, values) => { const text=read(rel); for(const value of values) if(!text.includes(value)) failures.push(`${rel}: missing ${value}`); return text; };

const phase4 = need('backend/v3_phase4.py', [
  '_PUBLIC_CARD_SWITCHES','show_description','show_region','show_players','show_build','show_rules',
  '_apply_public_card_controls','_remote_admin_metadata','DIRECTORY_HOST.status()','/api/v1/remote-admin/ping','browser_requires_https','live_probe_required'
]);
need('renderer/release-phase5-placard-window.js', [
  'phase5-placard-window','openPlacard','toggleMaximize','minimizeWindow','ResizeObserver','data-phase5-open-placard',
  'v3.phase4.platforms.registry','openInAppBrowser','__DWSYNC_PHASE5_PLACARDS__'
]);
need('renderer/release-phase5-placard-window.css', ['resize:both','maximized','minimized','focused','phase5-placard-task']);
need('backend/v3_phase4_web_focus.py', [
  'dws-v3p4-focus','data-v3p4-open','Open Placard','#world=','touch-friendly'
]);
const remote = need('backend/phase5_remote_admin.py', [
  'dragonwilds-sync-remote-admin','/api/v1/remote-admin/ping','/admin/login','target-world','remote_admin_enabled','WORLD_ID_MISMATCH','FINGERPRINT_MISMATCH'
]);
const directory = need('cloudflare/dragonwilds-sync-directory/worker-phase5.js', [
  "import base from './worker.js'",'world_remote_admin_v1','sanitizeRemote','https:','remote_admin_handoff','target-world','/api/v1/remote-admin/ping'
]);
need('cloudflare/dragonwilds-sync-directory/schema-v3.sql', ['world_remote_admin_v1','FOREIGN KEY (world_id) REFERENCES worlds_v3']);
const website = need('website/script.js', [
  'normalizeRemoteAdmin','openVerifiedRemoteAdmin','CONTACTING SERVER','dragonwilds-sync-remote-admin','Target server probe','world_id','fingerprint','SERVER VERIFIED'
]);
const runeschema = need('backend/managed_updates.py', [
  'RUNESCHEMA_REPOSITORY_URL = "https://github.com/UnskippableCutscene/RuneSchema"',
  'RUNESCHEMA_RELEASES_URL','ensure_runeschema_source','_runeschema_resolver_source','official_source',
  'install_authoritative_runeschema_update'
]);
const sources = need('docs/upstream-sources.json', [
  '"repository": "UnskippableCutscene/RuneSchema"',
  '"release_url": "https://github.com/UnskippableCutscene/RuneSchema/releases"',
  '"type": "github-release"'
]);
need('backend/test_managed_updates.py', [
  'test_runeschema_official_source_is_default_and_api_resolved',
  'test_runeschema_explicit_custom_source_is_preserved',
  'RUNESCHEMA_REPOSITORY_URL','RUNESCHEMA_RELEASES_URL'
]);
const desired = need('backend/runtime_worker_config.py', [
  'RuntimeDesiredConfig.v1','create_desired_snapshot','load_desired_snapshot','verify_authoritative_settings','settingsHash','desired-current.json','sync_profile_settings'
]);
const worker = need('backend/runtime_worker.py', [
  'START_RUNTIME','STOP_RUNTIME','RESTART_RUNTIME','GET_LOG_TAIL','_start_runtime','_stop_runtime','_restart_runtime',
  'desiredConfigRevision','appliedConfigRevision','load_desired_snapshot','verify_authoritative_settings',
  'game.stdout.log','game.stderr.log','GAME_EXITED_UNEXPECTEDLY','CREATE_NEW_PROCESS_GROUP','start_new_session',
  'JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE','windows-job-kill-on-close','orphan-watchdog-fallback','RUNTIME_RUNNING'
]);
need('backend/worker_supervisor.py', [
  'create_desired_snapshot','configRevision','start_runtime','stop_runtime','restart_runtime','log_tail','START_RUNTIME','STOP_RUNTIME','RESTART_RUNTIME','GET_LOG_TAIL'
]);
const bridge = need('backend/runtime_worker_bridge.py', [
  'WorkerBackedServerEngine','AuthoritativeRuntimeManager','world-runtime-worker','deferred_to_worker','dedicated_enabled','DWSYNC_DISABLE_RUNTIME_WORKERS',
  'revisioned-settings-snapshot','desired_config_revision','applied_config_revision','share_owner','application','start_runtime','stop_runtime','arm_orphan_watchdog'
]);
need('backend/test_phase5_runtime_worker_bridge.py', [
  'test_start_stop_through_authoritative_manager','test_explicit_rollback_keeps_direct_engine','test_restart_reattaches_existing_worker_without_duplicate_start','test_failed_start_cleans_worker_without_direct_fallback'
]);
need('backend/test_runtime_worker_config.py', [
  'plaintext secret leaked','old desired revision was mutated','stale desired runtime revision was not rejected'
]);
const service = need('backend/dragonwilds_service.py', [
  'install_runtime_worker_bridge','_install_phase5_workers','phase5_runtime_workers','_ensure_phase5_worker_gate',
  'phase5c-windows-linux-parity','config["dedicated_enabled"] = False',
  'runtime.worker.runtime.start','runtime.worker.runtime.stop','runtime.worker.runtime.restart','runtime.worker.runtime.logs','_worker_revision'
]);
need('renderer/index.html', ['release-phase5-placard-window.css','release-phase5-placard-window.js']);
need('backend/web_release_polish_hook.py', ['v3_phase4_web_focus','phase5_remote_admin']);
need('cloudflare/dragonwilds-sync-directory/wrangler.toml', ['main = "worker-phase5.js"']);

if (/password|csrf|session|credential_ref|admin_token/i.test(JSON.stringify({
  ping: remote.slice(remote.indexOf('def ping_payload'), remote.indexOf('def install'))
}))) failures.push('Remote Admin public ping must not expose credentials/session/CSRF/admin token fields');
if (!directory.includes('const heartbeatClone =') || !directory.includes('response.ok')) failures.push('Official directory must retain Remote Admin metadata only after the signed base heartbeat succeeds');
if (!website.includes("endpoint.protocol !== 'https:'")) failures.push('GitHub handoff must require HTTPS target endpoints');
if (!website.includes("String(live?.world_id || '') !== String(world.worldId || '')")) failures.push('GitHub handoff must compare live World ID before login');
if (!website.includes("String(live?.fingerprint || '') !== expectedFingerprint")) failures.push('GitHub handoff must compare live fingerprint when one is advertised');
if (/^(?:from|import)\s+server_engine\b/m.test(worker)) failures.push('World worker must lazy-load ServerEngine only after a runtime command');
if (!bridge.includes('return self.original.publish(profile_id)')) failures.push('Phase 5C must retain parent SHARE publication until dedicated worker parity is proven');
if (!phase4.includes('result.pop("connection", None)')) failures.push('Phase 4 public connection must remain opt-in');
if (/"password"\s*:|"server_key"\s*:|"admin_pass"\s*:/i.test(desired)) failures.push('Desired runtime snapshot module must not construct plaintext credential fields');
if (!worker.includes('self.applied_config_revision = desired["revision"]')) failures.push('Worker must report the exact desired revision as applied only after verified launch');
if (!bridge.includes('applied_revision != desired_revision')) failures.push('Runtime bridge must fail a start whose applied revision does not match desired revision');
if (!service.includes('activation_gate')) failures.push('Normal service must expose the Phase 5C activation gate instead of silently enabling an unverified worker path');
if (sources.includes('"download_url": "https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/resources/RuneSchema-core-latest.zip"')) failures.push('RuneSchema source registry must not retain the temporary Dragonwilds Sync-hosted ZIP as update authority');
if (!runeschema.includes('resolver_source = _runeschema_resolver_source(source_url)')) failures.push('Official RuneSchema releases URL must resolve through the GitHub API-capable repository source');

if (failures.length) {
  console.error('[Phase 5] FAIL'); failures.forEach(x => console.error(` - ${x}`)); process.exit(1);
}
console.log('[Phase 5] PASS · Phase 4 corrections, official RuneSchema releases, verified Remote Admin handoff, revisioned desired state and gated dedicated World Runtime Worker ownership contracts present');
