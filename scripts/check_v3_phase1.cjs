const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const deprecatedHost = 'dragonwilds-sync-directory.' + 'lucas-alexander-jones94.workers.dev';
const expectedNetworkUrl = 'https://dragonwilds-sync-directory.' + 'dragonwilds.workers.dev';
const transitionalSecretEnv = 'WORLD_' + 'SECRETS_JSON';
const ignoredRoots = new Set(['.git', 'node_modules', 'release', 'dist-service', '.venv-build']);
const textExtensions = new Set(['.py', '.js', '.cjs', '.mjs', '.json', '.md', '.txt', '.html', '.css', '.yml', '.yaml', '.ps1', '.bat', '.sh']);
// These files publish or consume the canonical endpoint for non-Python
// surfaces. They are replicas, not configuration authorities. Keeping the
// list explicit prevents a new runtime owner from appearing unnoticed.
const officialNetworkReplicaAllowlist = new Set([
  '.github/scripts/build_public_server_snapshot.py',
  'renderer/public-server-list.js',
  'website/.PUBLIC_DIRECTORY_AGGREGATION_CONTRACT.md',
  'website/assets/public-worlds-fallback.json',
  'website/directory-source.json',
]);

function walk(folder, out = []) {
  for (const entry of fs.readdirSync(folder, { withFileTypes: true })) {
    if (ignoredRoots.has(entry.name)) continue;
    const absolute = path.join(folder, entry.name);
    if (entry.isDirectory()) walk(absolute, out);
    else if (entry.isFile() && textExtensions.has(path.extname(entry.name).toLowerCase())) out.push(absolute);
  }
  return out;
}

function relative(file) {
  return path.relative(root, file).replaceAll('\\', '/');
}

const failures = [];
const files = walk(root);
let officialLiteralOwners = [];
let worldSecretsCodeOwners = [];
for (const file of files) {
  let text = '';
  try { text = fs.readFileSync(file, 'utf8'); } catch { continue; }
  const rel = relative(file);
  if (text.includes(deprecatedHost)) failures.push(`${rel}: deprecated official Worker hostname remains`);
  if (text.includes(expectedNetworkUrl) && !officialNetworkReplicaAllowlist.has(rel)) officialLiteralOwners.push(rel);
  const isDocumentation = path.extname(rel).toLowerCase() === '.md';
  if (text.includes(transitionalSecretEnv) && !isDocumentation && !rel.startsWith('PROJECT_STATE/') && !rel.startsWith('docs/')) {
    worldSecretsCodeOwners.push(rel);
  }
}

const expectedOwner = 'backend/network_config.py';
if (officialLiteralOwners.length !== 1 || officialLiteralOwners[0] !== expectedOwner) {
  failures.push(`official network URL must have one literal owner (${expectedOwner}); found: ${officialLiteralOwners.join(', ') || 'none'}`);
}
if (worldSecretsCodeOwners.length) {
  failures.push(`${transitionalSecretEnv} is transitional documentation only; code references found: ${worldSecretsCodeOwners.join(', ')}`);
}

const requiredDocs = [
  'PROJECT_STATE/archive/V3_PHASE1_AUDIT.md',
  'PROJECT_STATE/archive/V3_PERSISTENCE_MATRIX.md',
  'PROJECT_STATE/archive/V3_MIGRATION_MATRIX.md',
  'PROJECT_STATE/archive/V3_PHASE1_BASELINE.json',
];
for (const rel of requiredDocs) {
  if (!fs.existsSync(path.join(root, rel))) failures.push(`missing Phase 1 artifact: ${rel}`);
}

const persistencePath = path.join(root, 'PROJECT_STATE', 'V3_PERSISTENCE_MATRIX.md');
if (fs.existsSync(persistencePath)) {
  const text = fs.readFileSync(persistencePath, 'utf8');
  for (const field of [
    'World name', 'save selection/path', 'visibility', 'max players', 'server password reference',
    'ports', 'launch options', 'server executable/path', 'restart policy', 'watchdog',
    'update policy', 'update + restart policy', 'WebHost/WebGUI settings', 'broadcast settings',
    'public-directory settings', 'broadcast destinations', 'public-card settings', 'mod/runtime policy',
    'backup policy', 'advanced launch settings', 'default server paths', 'SteamCMD configuration',
    'auto-start behavior', 'default update policy', 'network presence preference', 'broadcast defaults',
    'WebGUI defaults', 'notification preferences', 'restart/update preferences',
  ]) {
    if (!text.includes(field)) failures.push(`persistence matrix is missing required field: ${field}`);
  }
}

const migrationPath = path.join(root, 'PROJECT_STATE', 'V3_MIGRATION_MATRIX.md');
if (fs.existsSync(migrationPath)) {
  const text = fs.readFileSync(migrationPath, 'utf8');
  for (const track of [
    'World Management', 'Single-Player', 'Co-Op', 'Dedicated Servers', 'Profiles', 'World Saves', 'Characters',
    'UE4SS', 'RuneSchema', 'Pak Mods', 'DragonLink-Connect', 'RSDWTools', 'RSDW DevKit',
    'Mod Manager', 'Explorer', 'Mod Editing', 'Item Editor', 'Spawner', 'Console', 'Console Commands',
    'Broadcast Messages', 'Heartbeat', 'Direct Connect', 'WebGUI', 'Community', 'Notifications', 'Updates',
    'Settings', 'Online Settings', 'Performance Settings', 'World Export', 'Character Export', 'Import', '.rsdwl',
    'Windows Installer', 'Windows Portable', 'Linux', 'Proton',
  ]) {
    if (!text.includes(track)) failures.push(`migration matrix is missing required track: ${track}`);
  }
}

if (failures.length) {
  console.error('[V3 Phase 1] FAIL');
  for (const failure of failures) console.error(` - ${failure}`);
  process.exit(1);
}
console.log('[V3 Phase 1] PASS · canonical network endpoint, deprecated-host/secret scan, audit artifacts and matrices verified');
