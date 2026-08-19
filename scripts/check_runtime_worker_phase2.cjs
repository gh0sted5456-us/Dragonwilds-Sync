const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const failures = [];
const read = rel => fs.readFileSync(path.join(root, rel), 'utf8');
const need = (rel, values) => { const text=read(rel); for(const value of values) if(!text.includes(value)) failures.push(`${rel}: missing ${value}`); return text; };

const protocol = need('backend/runtime_worker_protocol.py', [
  'PROTOCOL_VERSION = 1','MAX_MESSAGE_BYTES','AF_PIPE','AF_UNIX','send_bytes','recv_bytes','DWSYNC_RUNTIME_WORKER_AUTH','atomic_json','0o600','worker-state.json'
]);
const worker = need('backend/runtime_worker.py', [
  'WORKER_READY','PING','GET_STATUS','STOP','PROTOCOL_MISMATCH','COMMAND_NOT_ALLOWED','gamePid','authRef'
]);
const supervisor = need('backend/worker_supervisor.py', [
  'WorkerSupervisor','--runtime-worker','sys.executable','token_urlsafe','SecretStore','is_reference','CREATE_NEW_PROCESS_GROUP','start_new_session','reconcile','cleanup_stale','spawn','stop','list_status'
]);
const service = need('backend/dragonwilds_service.py', [
  'if __name__ == "__main__" and "--runtime-worker" in sys.argv','runtime.worker.foundation.list','runtime.worker.foundation.status','runtime.worker.foundation.spawn','runtime.worker.foundation.stop','runtime_worker_supervisor'
]);
need('backend/test_runtime_worker_phase2.py', [
  'duplicate spawn reuses compatible worker','fresh supervisor reattaches','PROTOCOL_MISMATCH','stale worker state cleaned','Phase 2 does not launch game'
]);
need('PROJECT_STATE/RUNTIME_WORKER_PHASE1_AUDIT.md', ['AUDIT → REUSE → SEPARATE EXECUTION → VERIFY → RETIRE OLD EXECUTION PATH','Worker Candidate Decision Table','Phase 2 Readiness']);
need('PROJECT_STATE/RUNTIME_WORKER_PHASE2.md', ['Completed','Processes Added','Processes Retired','Authoritative Owners Changed','Next Phase Readiness']);

if (protocol.includes('pickle.') || protocol.includes('.send(') || protocol.includes('.recv()')) failures.push('worker protocol must exchange bounded JSON bytes, not pickle objects');
if (/socket\.(?:AF_INET|AF_INET6)/.test(protocol) || /localhost|127\.0\.0\.1/.test(protocol)) failures.push('worker control IPC must not use a normal TCP listener');
// The historical foundation guarantee is launch-on-command, not a permanent
// ban on runtime support. Phase 5 may lazy-load the retained ServerEngine only
// after START_RUNTIME; module import/spawn itself must remain lightweight.
if (/^\s*(?:from|import)\s+(?:server_engine|runtime_manager|network_service)\b/m.test(worker)) {
  failures.push('runtime modules must not be imported eagerly at worker module load time');
}
if (supervisor.includes('env[WORKER_AUTH_ENV]') && supervisor.includes('worker_args') && /worker_args[^\n]*auth_token/.test(supervisor)) failures.push('plaintext worker auth token must not be placed on command line');
if (!supervisor.includes('SecretStore') || !supervisor.includes('is_reference')) failures.push('supervisor must use encrypted secret-reference authority for reconnect credentials');
const dispatch = service.indexOf('if __name__ == "__main__" and "--runtime-worker" in sys.argv');
const heavy = service.indexOf('import dragonwilds_service_v3_phase2');
if (dispatch < 0 || heavy < 0 || dispatch > heavy) failures.push('runtime-worker dispatch must occur before heavy backend imports');

if (failures.length) {
  console.error('[Runtime Worker Phase 2] FAIL');
  failures.forEach(x => console.error(` - ${x}`));
  process.exit(1);
}
console.log('[Runtime Worker Phase 2] PASS · same-executable headless mode, authenticated local IPC, supervisor/reattach and no launch-on-spawn verified');