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
if (!loader.includes('app-v2.js?v=3.1.0-window-hydration')) throw new Error('app-v2 cache key was not advanced.');
if (!index.includes('app.js?v=3.1.0-window-hydration')) throw new Error('app loader cache key was not advanced.');
if (!app.includes("typeof window.dwsApplyAvatarParams==='function'")) throw new Error('Avatar readiness must wait for the RSDWModel bridge.');
if (!app.includes("document.querySelector('#avatar-loading')?.hidden===false")) throw new Error('Avatar readiness must use the renderer loading state.');
if (app.includes("ready:'models-pending'")) throw new Error('Avatar readiness must not depend on one upstream status sentence.');
if (!app.includes("world?.kind==='connected'||world?.credentials?.source==='manual'")) throw new Error('Connected placards must have an explicit host-manifest data path.');
if (!app.includes("mergedModSummary(presentation.mod_summary,world.manifest_cache?.mod_summary)")) throw new Error('Connected placards must derive mod badges from host presentation/manifest data.');
if (!app.includes('id="s-pvp-enabled"') || !app.includes('id="detect-server-gameplay"')) throw new Error('Hosted World mode/PvP declaration controls are incomplete.');

console.log('Sync tab hydration and Character Preview readiness contract passed.');
