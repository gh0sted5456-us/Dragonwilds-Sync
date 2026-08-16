const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '..', 'renderer', 'app.js'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(source.includes('data-webhost-tab="live">Dragonwilds Sync'),
  'The combined Sync workspace must expose its Dragonwilds Sync preview tab.');
assert(source.includes('data-webhost-tab="settings">Networking'),
  'The combined Sync workspace must expose its Networking tab.');
assert(source.includes("navButton('webhost', webhostLinked?'◆':'◇', 'Sync')"),
  'Website and Remote Server capabilities must roll up under one Sync navigation item.');
assert(!source.includes("navButton('remote-server'"),
  'Remote Server must not create a second Host navigation item.');
assert(source.includes('id="toggle-webhost-remote-admin"'),
  'Sync Networking must independently expose Remote Server Access.');
assert(!source.includes("if(routedWebhost) state.webhostTab='live'"),
  'The routed WebHost workspace must not reset the selected tab during render.');

console.log('renderer route contract checks passed');
