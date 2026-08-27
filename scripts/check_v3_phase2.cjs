const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const failures = [];
const requireText = (rel, values) => {
  const text = read(rel);
  for (const value of values) if (!text.includes(value)) failures.push(`${rel}: missing ${value}`);
  return text;
};

requireText('backend/network_service.py', [
  'DirectoryNetworkService', 'dws-install-', 'dws-world-', '/api/v1/register', '/api/v1/presence',
  '/api/v1/worlds/register', '/api/v1/heartbeat', 'x-dws-timestamp', 'x-dws-signature',
  'PRESENCE_INTERVAL_SECONDS = 5 * 60', 'HEARTBEAT_INTERVAL_SECONDS = 60',
  'public_directory_enabled', 'broadcast_destinations', 'public_card', 'world_started', 'world_stopping',
]);
const phase2Service = fs.existsSync(path.join(root, 'backend', 'dragonwilds_service_v3_phase2.py'))
  ? 'backend/dragonwilds_service_v3_phase2.py'
  : 'backend/dragonwilds_service.py';
requireText(phase2Service, [
  'dragonwilds_service_v2_wrapper', 'quick.status', 'quick.start', 'quick.stop', 'quick.restart',
  'quick.update_restart', 'quick.console.execute', 'quick.broadcast', 'network.world.settings',
  'NETWORK.start_background()', 'world.discovery.heartbeat',
]);
requireText('electron/main.cjs', [
  "--quick", "--profile", "--mode", "--auto-start", "dragonwilds:create-v3-quick-shortcut",
  "buildQuickShortcutArgs", "require('./quick_shortcut.cjs')", "require('./main-v2.cjs')",
]);
requireText('electron/quick_shortcut.cjs', ["--quick --profile=${id} --mode=${normalizedMode}", "--auto-start", "PROFILE_ID_PATTERN"]);
requireText('electron/preload-v2.cjs', ['quickContext', 'createQuickShortcut', "exposeInMainWorld('dragonwilds'", "exposeInMainWorld('dragonwildsV3'"]);
requireText('renderer/app.js', ['v3Quick', 'app-v2.js']);
requireText('renderer/release-v3-phase2.js', [
  'Create Quick Shortcut', 'Open Quick + Start', 'Open Full Dragonwilds Sync', 'View Mods',
  'Broadcast Message', 'quick.console.execute', 'Participate in Dragonwilds Sync Network',
  'Broadcast this World publicly', '[data-application-settings-tab="network"].active',
]);
requireText('renderer/quick.html', ['release-v3-phase2.css', 'release-v3-phase2.js', 'v3-quick-body']);

const worker = requireText('cloudflare/dragonwilds-sync-directory/worker.js', [
  '/api/v1/register', '/api/v1/presence', '/api/v1/worlds/register', '/api/v1/heartbeat',
  '/api/v1/capabilities', '/api/v1/network', 'CREDENTIAL_WRAP_KEY', 'crypto.subtle', 'env.DB.prepare',
  'x-dws-timestamp', 'x-dws-signature', 'network_presence_v3 p JOIN installations i',
  'active_users:activeUsers', 'active_worlds:activeWorlds', 'dedicated_servers:', 'coop_hosts:', 'clients:',
  'players_in_listed_worlds:players', 'active_installations:activeUsers', 'active_players:players',
]);
requireText('cloudflare/dragonwilds-sync-directory/schema-v3.sql', [
  'CREATE TABLE IF NOT EXISTS installations', 'CREATE TABLE IF NOT EXISTS world_credentials',
  'CREATE TABLE IF NOT EXISTS network_presence_v3', 'CREATE TABLE IF NOT EXISTS worlds_v3',
  'CREATE TABLE IF NOT EXISTS heartbeat_history_v3', 'CREATE TABLE IF NOT EXISTS rate_limits_v3',
]);
if (worker.includes('WORLD_' + 'SECRETS_JSON')) failures.push('Cloudflare V3 Worker must not use transitional manual World secret provisioning');
const networkStatsStart = worker.indexOf('async function networkStats');
const networkStatsEnd = worker.indexOf('export default', networkStatsStart);
const networkStats = networkStatsStart >= 0 && networkStatsEnd > networkStatsStart
  ? worker.slice(networkStatsStart, networkStatsEnd)
  : '';
if (!networkStats.includes("p.mode='client'") || !networkStats.includes("p.mode='dedicated_server'") || !networkStats.includes("p.mode='coop_host'")) failures.push('Network aggregate must break anonymous presence down by client/dedicated/coop mode');
if (/\binstallation_id\s*:/.test(networkStats)) failures.push('Public network aggregate must never expose installation IDs');

requireText('PROJECT_STATE/archive/V3_PHASE2.md', ['Reuse → Migrate → Verify → Retire', 'Cloudflare', 'external deployment gate']);

const bootstrap = read('electron/bootstrap.cjs');
if (!bootstrap.includes("argv.includes('--quick')") || !bootstrap.includes('main-v2 owns mode-aware background services')) failures.push('electron/bootstrap.cjs: Quick must defer lean service policy to the promotable main process');

const renderer = read('renderer/release-v3-phase2.js');
for (const forbidden of ['x-dws-signature', 'x-dws-timestamp', 'installation_credential_ref', 'credential_ref =', 'setInterval(()=>api.invoke(\'network.heartbeat']) {
  if (renderer.includes(forbidden)) failures.push(`renderer/release-v3-phase2.js: renderer must not own network credential/scheduler contract (${forbidden})`);
}

const main = read('electron/main.cjs');
if (/password|world_pass|admin_pass|server_key|share_access_key/i.test(main)) failures.push('electron/main.cjs: Quick shortcut arguments must not contain credential fields');

const retainedMain = read('electron/main-v2.cjs');
if (!retainedMain.includes("preload: path.join(__dirname, 'preload-v2.cjs')")) failures.push('electron/main-v2.cjs: BrowserWindow must select the self-contained sandbox preload');
if (!retainedMain.includes('sandbox: true')) failures.push('electron/main-v2.cjs: BrowserWindow preload must remain sandboxed');
if (!retainedMain.includes("'renderer', 'quick.html'")) failures.push('electron/main-v2.cjs: Quick windows must use the lean dedicated renderer entry');
if (!retainedMain.includes("autoStart: argv.includes('--auto-start')")) failures.push('electron/main-v2.cjs: second-instance Quick handoff must preserve auto-start');
for (const token of ['startBackgroundServices', 'promoteToFullApplication', "process.env.DWS_V3_QUICK='0'", "['coop','server'].includes(mode)"]) {
  if (!retainedMain.includes(token)) failures.push(`electron/main-v2.cjs: Quick promotion/resource contract missing ${token}`);
}
for (const token of ['profile_scope', 'launch_sequence', '_quick_console_execute', 'unified_console_snapshot']) {
  if (!read(phase2Service).includes(token)) failures.push(`${phase2Service}: profile-scoped Quick contract missing ${token}`);
}
for (const token of ['quickConsole()', 'data-v3q-console-filter', 'Runtime Console', 'launchPlan()', 'same launcher process']) {
  if (!renderer.includes(token)) failures.push(`renderer/release-v3-phase2.js: scoped Quick management missing ${token}`);
}
const retainedPreload = read('electron/preload-v2.cjs');
if (/require\(['"]\.\/preload[^'"]*['"]\)/.test(retainedPreload)) failures.push('electron/preload-v2.cjs: sandbox preload must not require another local preload');

if (!fs.existsSync(path.join(root, 'backend', 'dragonwilds_service_v2_wrapper.py'))) failures.push('missing preserved post-V2 service wrapper');
if (!fs.existsSync(path.join(root, 'electron', 'main-v2.cjs'))) failures.push('missing preserved Electron main implementation');
if (!fs.existsSync(path.join(root, 'electron', 'preload-v2.cjs'))) failures.push('missing preserved preload implementation');
if (!fs.existsSync(path.join(root, 'renderer', 'app-v2.js'))) failures.push('missing preserved full renderer implementation');
if (!fs.existsSync(path.join(root, 'backend', 'profile_settings_v1.py'))) failures.push('missing preserved profile-settings implementation');

if (failures.length) {
  console.error('[V3 Phase 2] FAIL'); failures.forEach((failure)=>console.error(` - ${failure}`)); process.exit(1);
}
console.log('[V3 Phase 2] PASS · shared runtime/Quick CLI, backend network authority, anonymous network aggregates, publication controls and compatibility layers verified');
