const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const js = fs.readFileSync(path.join(root, 'renderer/public-server-list.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'renderer/public-server-list.css'), 'utf8');
const failures = [];

for (const token of [
  "https://gh0sted5456-us.github.io/Dragonwilds-Sync-Web/",
  "https://dragonwilds-sync-directory.dragonwilds.workers.dev/api/v1/worlds",
  'const PAGE_SIZE = 50',
  'filtered.slice(pageStart, pageStart + PAGE_SIZE)',
  'renderPagination(filtered.length)',
  'currentPage = 1',
  'dws-public-server-pagination',
]) {
  if (!js.includes(token)) failures.push(`renderer/public-server-list.js: missing ${token}`);
}
if (js.includes('public-worlds-fallback.json')) {
  failures.push('renderer/public-server-list.js: retired website snapshot fallback must not return');
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
console.log('[Public Server List] PASS · desktop rendering is bounded to 50 server cards per page');
