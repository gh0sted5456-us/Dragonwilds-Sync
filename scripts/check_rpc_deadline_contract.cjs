const fs = require('fs');

const main = fs.readFileSync('electron/main-v2.cjs', 'utf8');
const preload = fs.readFileSync('electron/preload-v2.cjs', 'utf8');
const failures = [];

for (const required of [
  'DEFAULT_SERVICE_TIMEOUT_MS',
  'LONG_SERVICE_TIMEOUT_MS',
  'BACKGROUND_SERVICE_TIMEOUT_MS',
  'function serviceTimeoutFor(method)',
  'pending.set(id,{resolve,reject,timer',
  'if(!pending.delete(id))return',
  'clearPendingTimer(waiter)',
  "serviceInvoke('application.shutdown',{}, {timeoutMs:30000})",
]) {
  if (!main.includes(required)) failures.push(`electron/main-v2.cjs missing ${required}`);
}
if (!main.includes('timer.unref?.()')) failures.push('main-process service deadline timer must not keep Electron alive');
for (const required of [
  'READ_TIMEOUT_MS',
  'DEFAULT_INVOKE_TIMEOUT_MS',
  'LONG_INVOKE_TIMEOUT_MS',
  'function rendererTimeoutFor(method)',
  "ipcRenderer.invoke('dragonwilds:invoke', method, params, {timeoutMs})",
]) {
  if (!preload.includes(required)) failures.push(`electron/preload-v2.cjs missing ${required}`);
}
if (preload.includes('if (!READ_POLICIES[method] && !DEDUPE_ONLY.has(method)) return request')) {
  failures.push('preload still permits unbounded renderer requests');
}

if (failures.length) {
  for (const failure of failures) console.error(`[RPC deadline] ${failure}`);
  process.exit(1);
}
console.log('[RPC deadline] PASS · main pending requests are bounded and timers are cleared on response/exit');
