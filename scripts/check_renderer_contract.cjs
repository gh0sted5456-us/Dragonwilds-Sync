const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'renderer', 'app-v2.js'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(source.includes('data-webhost-tab="live">Dragonwilds Sync'),
  'The combined Sync workspace must expose its Dragonwilds Sync preview tab.');
assert(source.includes('data-webhost-tab="settings">Website &amp; Networking'),
  'The combined Sync workspace must expose its Networking tab.');
assert(source.includes("navButton('webhost',webhostLinked?'◆':'◇','Sync'"),
  'Website and Remote Server capabilities must roll up under one Sync navigation item.');
assert(source.includes("navButton('characters-app'") && source.includes("navButton('mods-app'") && source.includes("navButton('rsdragonwilds-app'"),
  'Characters, Mods, and RSDragonwilds must be first-class Appy navigation entries.');
assert(!source.includes("navButton('remote-server'"),
  'Remote Server must not create a second Host navigation item.');
assert(source.includes('id="toggle-webhost-remote-admin"'),
  'Sync Networking must independently expose Remote Server Access.');
assert(!source.includes("if(routedWebhost) state.webhostTab='live'"),
  'The routed WebHost workspace must not reset the selected tab during render.');

function sha256(relativePath) {
  return crypto.createHash('sha256')
    .update(fs.readFileSync(path.join(root, relativePath)))
    .digest('hex');
}

function assertPng(relativePath) {
  const file = fs.readFileSync(path.join(root, relativePath));
  assert(file.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])),
    `${relativePath} must be a valid PNG asset.`);
}

const platformAssets = {
  'renderer/assets/platforms/runeschema.png': '379a7b239490eb8fcc01ff6bafdaf291f09393ab30106658af02bf96c716b105',
  'renderer/assets/platforms/ue4ss.png': '5d85d20b008b32516ee3115318b4aeaba54631f6d254477e60af55101823d98a',
};

for (const [relativePath, expectedHash] of Object.entries(platformAssets)) {
  assertPng(relativePath);
  assert(sha256(relativePath) === expectedHash,
    `${relativePath} does not match its approved canonical artwork.`);
}

for (const placard of [1, 2, 3, 4]) {
  assertPng(`renderer/assets/placards/${placard}.png`);
}

assert(source.includes("--world-placard:url('assets/placards/${placardId}.png')"),
  'Desktop world cards must use the selected placard as their full background.');
assert(source.includes('world-card-media') && source.includes('world-card-banner-blend'),
  'Desktop world cards must keep the banner and its blend layer at the top.');
assert(source.includes('world-list-row has-placard') && source.includes('hosted-list-row has-placard'),
  'Horizontal World cards must inherit the selected placard background.');

const websitePlacards = fs.readFileSync(path.join(root, 'website', 'placards.js'), 'utf8');
assert(websitePlacards.includes('raw?.banner_b64') && websitePlacards.includes('raw?.icon_b64'),
  'Website placards must accept the application banner and icon payloads.');
assert(websitePlacards.includes("makeImage('world-placard-backdrop'"),
  'Website placards must render the selected placard as the full background.');
assert((websitePlacards.match(/back\.appendChild\(makeMedia\(world\)\)/g) || []).length === 1,
  'The reverse face must inherit the same server banner as the front face.');
assert(websitePlacards.includes("card.classList.toggle('flipped')") &&
  websitePlacards.includes("event.key === 'Enter' || event.key === ' '"),
  'Website placards must provide click and keyboard-operated 3D flipping.');

console.log('renderer route and visual asset contract checks passed');
