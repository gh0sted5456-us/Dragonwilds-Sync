const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const failures = [];
const read = rel => fs.readFileSync(path.join(root, rel), 'utf8');
const need = (rel, values) => { const text=read(rel); for(const value of values) if(!text.includes(value)) failures.push(`${rel}: missing ${value}`); return text; };

const phase4 = need('backend/v3_phase4.py', [
  '_PUBLIC_CARD_SWITCHES','show_description','show_region','show_players','show_build','show_rules',
  '_apply_public_card_controls','_remote_admin_metadata','/api/v1/remote-admin/ping','browser_requires_https','live_probe_required'
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
const website = need('website/script.js', [
  'normalizeRemoteAdmin','openVerifiedRemoteAdmin','CONTACTING SERVER','dragonwilds-sync-remote-admin','Target server probe','world_id','fingerprint','SERVER VERIFIED'
]);
const worker = need('backend/runtime_worker.py', [
  'START_RUNTIME','STOP_RUNTIME','RESTART_RUNTIME','_start_runtime','_stop_runtime','_restart_runtime','start_new_session','CREATE_NEW_PROCESS_GROUP','RUNTIME_RUNNING'
]);
need('backend/worker_supervisor.py', ['start_runtime','stop_runtime','restart_runtime','START_RUNTIME','STOP_RUNTIME','RESTART_RUNTIME']);
const bridge = need('backend/runtime_worker_bridge.py', [
  'WorkerBackedServerEngine','AuthoritativeRuntimeManager','world-runtime-worker','deferred_to_worker','dedicated_enabled','DWSYNC_DISABLE_RUNTIME_WORKERS',
  'share_owner','application','start_runtime','stop_runtime','arm_orphan_watchdog'
]);
need('backend/test_phase5_runtime_worker_bridge.py', [
  'test_start_stop_through_authoritative_manager','test_explicit_rollback_keeps_direct_engine','test_restart_reattaches_existing_worker'
]);
need('backend/dragonwilds_service.py', [
  'install_runtime_worker_bridge','_install_phase5_workers','phase5_runtime_workers','runtime.worker.runtime.start','runtime.worker.runtime.stop','runtime.worker.runtime.restart'
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
if (!bridge.includes('return self.original.publish(profile_id)')) failures.push('Phase 5 runtime-only parity stage must retain existing parent SHARE publication until dedicated worker parity is proven');
if (!phase4.includes('result.pop("connection", None)')) failures.push('Phase 4 public connection must remain opt-in');

if (failures.length) {
  console.error('[Phase 5] FAIL'); failures.forEach(x => console.error(` - ${x}`)); process.exit(1);
}
console.log('[Phase 5] PASS · Phase 4 corrections, focused placards, verified direct Remote Admin handoff and dedicated World Runtime Worker bridge contracts present');
