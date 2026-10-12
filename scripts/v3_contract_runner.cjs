'use strict';

// Historical source-contract checks intentionally validate the preserved V2 /
// post-V2 implementations after V3 introduces thin canonical wrappers. This
// runner redirects only the old canonical source reads; V3 contract checks run
// directly against the new files and are never routed through this adapter.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const nativeRead = fs.readFileSync.bind(fs);
const redirects = new Map([
  [path.normalize(path.join(root, 'renderer', 'app.js')), path.join(root, 'renderer', 'app-v2.js')],
  [path.normalize(path.join(root, 'electron', 'preload.cjs')), path.join(root, 'electron', 'preload-v2.cjs')],
  [path.normalize(path.join(root, 'electron', 'main.cjs')), path.join(root, 'electron', 'main-v2.cjs')],
  [path.normalize(path.join(root, 'backend', 'profile_settings.py')), path.join(root, 'backend', 'profile_settings_v1.py')],
  [path.normalize(path.join(root, 'backend', 'dragonwilds_service.py')), path.join(root, 'backend', 'dragonwilds_service_v2_wrapper.py')],
]);

fs.readFileSync = function v3HistoricalRead(file, ...args) {
  let key = '';
  try { key = path.normalize(path.resolve(String(file))); } catch (_) {}
  const replacement = redirects.get(key);
  return nativeRead(replacement || file, ...args);
};

const checker = String(process.argv[2] || '').trim();
if (!checker) {
  console.error('Usage: node scripts/v3_contract_runner.cjs <historical-checker.cjs>');
  process.exit(2);
}
require(path.resolve(root, checker));
