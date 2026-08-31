const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const js = fs.readFileSync(path.join(root, 'renderer/public-server-list.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'renderer/public-server-list.css'), 'utf8');
const failures = [];

for (const token of [
  "https://gh0sted5456-us.github.io/Dragonwilds-Sync-Web/servers.html",
  'const PAGE_SIZE = 50',
  'filtered.slice(pageStart, pageStart + PAGE_SIZE)',
  'renderPagination(filtered.length)',
  'currentPage = 1',
  'dws-public-server-pagination',
  "document.querySelector('#dws-public-server-list-mount')",
  'world.isSync && world.launcherBroadcasting',
  "filter((world) => world.isSync && world.launcherBroadcasting)",
  'Dragonwilds is active without Sync',
  'assets/navigation/dragonwilds.webp',
  'assets/navigation/sync.svg',
  'Sync Public World Directory',
]) {
  if (!js.includes(token)) failures.push(`renderer/public-server-list.js: missing ${token}`);
}
if (js.includes('public-worlds-fallback.json')) {
  failures.push('renderer/public-server-list.js: retired website snapshot fallback must not return');
}
for (const retired of ['dws-public-server-tab', 'dws-public-server-link', "closest('[data-world-tab]')"]) {
  if (js.includes(retired)) failures.push(`renderer/public-server-list.js: retired Connected Worlds integration remains: ${retired}`);
}
if (!css.includes('.dws-public-server-pagination[hidden]{display:none}')) {
  failures.push('renderer/public-server-list.css: pagination hidden-state contract is missing');
}
if (/filtered\.forEach\(\(world\)/.test(js)) {
  failures.push('renderer/public-server-list.js: full filtered result set is still rendered');
}

if (failures.length) {
  console.error('[Public Server List] FAIL');
  failures.forEach((failure) => console.error(` - ${failure}`));
  process.exit(1);
}
console.log('[Sync Public World Directory] PASS · launcher broadcasts expose Sync, Game, and combined states across at most 50 cards per page');
