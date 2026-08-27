const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'renderer', 'app-v2.js'), 'utf8');
const loader = fs.readFileSync(path.join(root, 'renderer', 'app.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'renderer', 'index.html'), 'utf8');

for (const label of ['Website &amp; Directory', 'Manifest &amp; Heartbeats', 'Server Management', 'WebGUI Preview']) {
  if (!app.includes(label)) throw new Error(`Sync first-render label is missing: ${label}`);
}
for (const stale of ['>Website Management</button>', '>Remote Management</button>', '>Live Preview</button>']) {
  if (app.includes(stale)) throw new Error(`Stale first-render Sync tab remains: ${stale}`);
}
if (!loader.includes('app-v2.js?v=3.0.1-sync-tabs-avatar-2')) throw new Error('app-v2 cache key was not advanced.');
if (!index.includes('app.js?v=3.0.1-sync-tabs-avatar-2')) throw new Error('app loader cache key was not advanced.');
if (!app.includes("typeof window.dwsApplyAvatarParams==='function'")) throw new Error('Avatar readiness must wait for the RSDWModel bridge.');
if (!app.includes("document.querySelector('#avatar-loading')?.hidden===false")) throw new Error('Avatar readiness must use the renderer loading state.');
if (app.includes("ready:'models-pending'")) throw new Error('Avatar readiness must not depend on one upstream status sentence.');

console.log('Sync tab hydration and Character Preview readiness contract passed.');
