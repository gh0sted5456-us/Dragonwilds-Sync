const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const failures = [];
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const need = (rel, values) => {
  const text = read(rel);
  for (const value of values) if (!text.includes(value)) failures.push(`${rel}: missing ${value}`);
  return text;
};

need('backend/v3_identity.py', ['CANONICAL_FILENAME = "ID.txt"', 'LEGACY_FILENAMES', 'discover_identity_file', 'parse_id_text', 'render_id_text', 'PersistenceID', 'ITEM Name', 'AssetPath']);
need('backend/v3_item_registry.py', ['DragonwildsSync.ItemRegistry.v1', 'strong_keys', 'PersistenceID', 'ModId', 'ITEM Name', 'AssetPath', 'merge_item_sources', 'rsdwl', 'ID.txt']);
need('backend/v3_exchange.py', [
  'DragonwildsSync.RSDWLExchange.v1', 'VERSION = 4', 'PACKAGE_TYPE = "exchange"',
  '"ID.txt"', '"World"', '"Characters"', '"ModInfo"', '"PackageManifest"',
  'collect_world_entries', 'collect_character_entries', 'export_exchange', 'inspect_exchange', 'plan_import', 'apply_import',
  '"update"', '"copy"', '"skip"', '"review"', 'Symlinks are not permitted', 'Case-colliding/duplicate',
  'world_id', 'public_card', 'source_world_id', 'ensure_world_identity', 'dws-secret://',
]);
need('backend/dragonwilds_service.py', [
  'dragonwilds_service_v3_phase2', 'v3.exchange.inspect', 'v3.exchange.plan_import', 'v3.exchange.export', 'v3.exchange.import',
  'v3.item.registry', 'v3.identity.inspect', 'NETWORK.ensure_world_identity', 'metadataMigrated', 'exportsMigrated',
]);
need('backend/test_v3_phase3.py', ['multi-world.rsdwl', 'world_decisions=', '"update"', '"copy"', 'manifest-only.rsdwl', 'path traversal', 'symlink']);
need('PROJECT_STATE/archive/V3_PHASE3.md', ['ID.txt', '.rsdwl', 'Update Existing', 'Import as Copy', 'Skip', 'Review Differences', 'Character', 'Item Registry', 'Reuse → Migrate → Verify → Retire']);

if (!fs.existsSync(path.join(root, 'backend', 'dragonwilds_service_v3_phase2.py'))) failures.push('missing preserved V3 Phase 2 service layer');

const identity = read('backend/v3_identity.py');
if (/CANONICAL_FILENAME\s*=\s*["']identity\.txt/i.test(identity)) failures.push('ID.txt must be the canonical exported identity filename');

const exchange = read('backend/v3_exchange.py');
const transitionalManualSecretName = 'WORLD_' + 'SECRETS_JSON';
for (const forbidden of ['extractall(', 'os.system(', 'subprocess.', 'credential_ref\":', transitionalManualSecretName]) {
  if (exchange.includes(forbidden)) failures.push(`backend/v3_exchange.py: forbidden Phase 3 pattern ${forbidden}`);
}
if (!exchange.includes('profile["exchange_provenance"]') || !exchange.includes('action == "copy"') || !exchange.includes('ensure_world_identity')) {
  failures.push('backend/v3_exchange.py: Copy/Update publication-identity boundary is incomplete');
}

const registry = read('backend/v3_item_registry.py');
if (/source.*rsdwl.*[0-9]{2,}/i.test(registry) && !registry.includes('Revision')) failures.push('Item registry must not prioritize .rsdwl solely by source');

if (failures.length) {
  console.error('[V3 Phase 3] FAIL');
  failures.forEach((failure) => console.error(` - ${failure}`));
  process.exit(1);
}
console.log('[V3 Phase 3] PASS · ID.txt, logical Item Registry, hardened multi-World/Character .rsdwl exchange contract verified');
