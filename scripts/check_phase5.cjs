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
  'RuntimeDesiredConfig.v1','create_desired_snapshot','load_desired_snapshot','verify_authoritative_settings','settingsHash','desired-current.json','sync_profile_settings',
  '_prepare_main_owned_runtime_profile','_install_worker_persistence_overlay','WORKER_AUTH_ENV','persistenceAuthority','workerPersistence',
  'profile_store.load_server_profile = worker_load_server_profile','profile_store.save_server_profile = worker_save_server_profile',
  'profile_store.load_state = worker_load_state','profile_store.save_state = worker_save_state'
]);
const worker = need('backend/runtime_worker.py', [
  'START_RUNTIME','STOP_RUNTIME','RESTART_RUNTIME','GET_LOG_TAIL','_start_runtime','_stop_runtime','_restart_runtime',
  'START_SHARE','STOP_SHARE','GET_SHARE_PAYLOAD','_start_share','_stop_share','_share_payload','FILE_SHARE_STATUS',
  'desiredConfigRevision','appliedConfigRevision','load_desired_snapshot','verify_authoritative_settings',
  'game.stdout.log','game.stderr.log','GAME_EXITED_UNEXPECTEDLY','CREATE_NEW_PROCESS_GROUP','start_new_session',
  'JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE','windows-job-kill-on-close','orphan-watchdog-fallback','RUNTIME_RUNNING'
]);
const supervisor = need('backend/worker_supervisor.py', [
  'create_desired_snapshot','configRevision','start_runtime','stop_runtime','restart_runtime','log_tail',
  'start_share','stop_share','share_payload','START_RUNTIME','STOP_RUNTIME','RESTART_RUNTIME','START_SHARE','STOP_SHARE','GET_SHARE_PAYLOAD','GET_LOG_TAIL'
]);
const bridge = need('backend/runtime_worker_bridge.py', [
  'WorkerBackedServerEngine','WorkerBackedShare','world-runtime-worker','deferred_to_worker','dedicated_enabled','share_enabled','DWSYNC_DISABLE_RUNTIME_WORKERS',
  'revisioned-settings-snapshot','desired_config_revision','applied_config_revision','share_owner','heartbeat_owner','webgui_owner',
  'start_runtime','stop_runtime','start_share','stop_share','arm_orphan_watchdog','_rewire_legacy_share','share_payload=share_adapter.broadcast_payload','share_status=share_adapter.status'
]);
const bridgeTests = need('backend/test_phase5_runtime_worker_bridge.py', [
  'test_start_stop_through_authoritative_manager','test_explicit_rollback_keeps_direct_engine_and_share',
  'test_share_slice_can_be_rolled_back_independently','test_restart_reattaches_existing_worker_without_duplicate_game_start',
  'test_failed_start_cleans_worker_without_direct_fallback','Parent process must not start a duplicate dedicated Sync listener'
]);
const configTests = need('backend/test_runtime_worker_config.py', [
  'plaintext secret leaked','old desired revision was mutated','stale desired runtime revision was not rejected',
  'workerPersistence','World worker wrote durable profile.json','World worker changed authoritative settings.json','World worker wrote durable launcher_v2.json',
  'old-family-key','family_join_rotated_at'
]);
const service = need('backend/dragonwilds_service.py', [
  'install_runtime_worker_bridge','_install_phase5_workers','phase5_runtime_workers','_ensure_phase5_worker_gate',
  'phase5c-windows-linux-parity-passed','config["dedicated_enabled"] = True',
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
if (!bridge.includes('response = self.supervisor.start_share(profile_id)')) failures.push('Phase 5D dedicated Sync publication must execute through the World worker');
if (!bridge.includes('return self.original.publish(profile_id)')) failures.push('Phase 5D must retain an explicit share-only rollback path until parity is proven');
if (!bridge.includes('config.setdefault("heartbeat_owner", "application")')) failures.push('Heartbeat ownership must remain application-owned in the first Phase 5D Sync-share slice');
if (!bridge.includes('config.setdefault("webgui_owner", "application")')) failures.push('WebGUI ownership must remain application-owned in the first Phase 5D Sync-share slice');
if (!bridge.includes('legacy.SHARE = share_adapter')) failures.push('Retained V3 heartbeat readers must be rewired to the worker-backed SHARE proxy');
if (!bridgeTests.includes('assert stop_share < stop_runtime < stop_worker')) failures.push('Phase 5D test must prove Share -> Runtime -> Worker stop ordering');
if (!phase4.includes('result.pop("connection", None)')) failures.push('Phase 4 public connection must remain opt-in');
if (/"password"\s*:|"server_key"\s*:|"admin_pass"\s*:/i.test(desired)) failures.push('Desired runtime snapshot module must not construct plaintext credential fields');
if (!desired.includes('profile_store.read_json(profile_store.SERVER_PROFILES_DIR / profile_id / "profile.json", {})')) failures.push('Worker persistence overlay must refresh from main-owned durable profile state before each verified revision');
if (!desired.includes('profile_store.read_json(profile_store.V2_SETTINGS_PATH, {})')) failures.push('Worker global-state overlay must read without becoming the durable launcher-state writer');
if (!configTests.includes('assert profile_path.read_bytes() == profile_bytes')) failures.push('Worker config regression must prove profile.json remains byte-identical after legacy runtime save calls');
if (!configTests.includes('assert settings_path.read_bytes() == settings_bytes')) failures.push('Worker config regression must prove authoritative settings.json remains byte-identical');
if (!worker.includes('self.applied_config_revision = desired["revision"]')) failures.push('Worker must report the exact desired revision as applied only after verified launch');
if (!bridge.includes('applied_revision != desired_revision')) failures.push('Runtime bridge must fail a start whose applied revision does not match desired revision');
if (!service.includes('activation_gate')) failures.push('Normal service must expose the recorded Phase 5C gate result and preserve explicit rollback state');
if (!service.includes('Existing explicit ``dedicated_enabled`` values are preserved')) failures.push('Phase 5C activation must preserve an explicit operator rollback choice');
if (sources.includes('"download_url": "https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/main/resources/RuneSchema-core-latest.zip"')) failures.push('RuneSchema source registry must not retain the temporary Dragonwilds Sync-hosted ZIP as update authority');
if (!runeschema.includes('resolver_source = _runeschema_resolver_source(source_url)')) failures.push('Official RuneSchema releases URL must resolve through the GitHub API-capable repository source');

if (failures.length) {
  console.error('[Phase 5] FAIL'); failures.forEach(x => console.error(` - ${x}`)); process.exit(1);
}
console.log('[Phase 5] PASS · retained Phase 4 corrections, passed Phase 5C dedicated worker gate, worker-owned dedicated Sync share, and application-owned durable profile/settings authority');