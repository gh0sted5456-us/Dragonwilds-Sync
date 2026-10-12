const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
// Read the actual entry point, bypassing historical path redirects used by legacy checks.
const descriptor = fs.openSync(require('node:path').join(__dirname, '../renderer/app.js'), 'r');
let source;
try { source = fs.readFileSync(descriptor, 'utf8'); } finally { fs.closeSync(descriptor); }
for (const quick of [false, true]) {
  const writes = [];
  vm.runInNewContext(source, {
    URLSearchParams,
    window: { location: { search: quick ? '?quick=1' : '' } },
    document: { documentElement: { dataset: {} }, write: html => writes.push(html) },
  });
  for (const html of writes) assert.match(html, /^<script src="[^"]+"><\/script>$/);
  if (!quick) {
    assert.equal(writes.length, 4);
    assert(writes.some(html => html.includes('release-machine-mod-mapping.js')));
  } else assert.equal(writes.length, 1);
}
console.log('Renderer bootstrap emits complete script elements in Full and Quick modes: PASS');
