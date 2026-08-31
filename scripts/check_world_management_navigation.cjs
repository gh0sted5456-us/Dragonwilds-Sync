const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'renderer/app-v2.js'), 'utf8');
const publicList = fs.readFileSync(path.join(root, 'renderer/public-server-list.js'), 'utf8');
const failures = [];

for (const token of [
  'data-world-management-tab="manifest">Sync World Directory',
  'id="dws-public-server-list-mount"',
  'data-connected-world-category="favorites"',
  'data-connected-world-category="connected"',
  "button.dataset.connectedWorldCategory==='favorites'?'favorites':'all'",
]) if (!app.includes(token)) failures.push(`renderer/app-v2.js: missing ${token}`);

for (const retired of ['World Finder', 'world-directory-webview', 'data-world-tab=']) {
  if (app.includes(retired)) failures.push(`renderer/app-v2.js: retired duplicate surface remains: ${retired}`);
}
if (!publicList.includes("document.querySelector('#dws-public-server-list-mount')")) failures.push('Sync World Directory must mount only in its top-level workspace');

if (failures.length) {
  console.error('[World Management Navigation] FAIL');
  failures.forEach((failure) => console.error(` - ${failure}`));
  process.exit(1);
}
console.log('[World Management Navigation] PASS · Connected Worlds and Sync World Directory are distinct workspaces');
