const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { isNewer, chooseAsset, uniqueDownloadPath, assertAllowedDownloadUrl } = require('../electron/app_updater.cjs');

assert.strictEqual(isNewer('v3.5.1', '3.5.1'), false);
assert.strictEqual(isNewer('v3.5.2', '3.5.1'), true);
assert.strictEqual(isNewer('v3.5.0', '3.5.1'), false);
assert.strictEqual(isNewer('not-a-version', '3.5.1'), false);
assert.strictEqual(chooseAsset({ assets:[{name:'Dragonwilds Sync Headless.exe'},{name:'Dragonwilds Sync.exe'}] }, 'win32').name, 'Dragonwilds Sync.exe');
assert.strictEqual(assertAllowedDownloadUrl('https://github.com/owner/repo/releases/download/v1/file.exe').hostname, 'github.com');
assert.throws(() => assertAllowedDownloadUrl('http://github.com/owner/repo/file.exe'), /trusted GitHub/);
assert.throws(() => assertAllowedDownloadUrl('https://example.com/update.exe'), /trusted GitHub/);

const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'dws-updater-'));
try {
  const original = path.join(directory, 'Dragonwilds Sync-Portable.exe');
  fs.writeFileSync(original, 'verified-update');
  const digest = crypto.createHash('sha256').update('verified-update').digest('hex');
  assert.deepStrictEqual(uniqueDownloadPath(directory, path.basename(original), digest), { path: original, alreadyDownloaded:true });
  const different = uniqueDownloadPath(directory, path.basename(original), '0'.repeat(64));
  assert.strictEqual(path.basename(different.path), 'Dragonwilds Sync-Portable (1).exe');
  assert.strictEqual(different.alreadyDownloaded, false);
} finally {
  fs.rmSync(directory, { recursive:true, force:true });
}
console.log('Manual portable updater contract: PASS');
