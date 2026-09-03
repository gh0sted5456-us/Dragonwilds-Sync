const fs = require('node:fs');
const path = require('path');

const root = path.join(__dirname, '..');
const registryPath = path.join(root, 'docs', 'upstream-sources.json');
const rendererPath = path.join(root, 'renderer', 'upstream-sources.js');
const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
const renderer = fs.readFileSync(rendererPath, 'utf8');
const required = ['rsdwtools', 'rsdw-icons', 'rsdw-item-manifest', 'rsdw-toolkit', 'dragonconnect', 'runeschema', 'ue4ss'];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(registry.schema === 'DragonwildsSync.UpstreamSources.v1', 'Unexpected upstream source schema.');
assert(registry.sources && typeof registry.sources === 'object', 'Upstream source registry must contain sources.');
for (const id of required) {
  assert(registry.sources[id], `Missing required upstream source: ${id}`);
  assert(registry.sources[id].enabled !== false, `Required upstream source is disabled: ${id}`);
}
assert(registry.sources['rsdw-icons'].path, 'RSDW icon source must declare its canonical path.');
assert(registry.sources['rsdw-item-manifest'].path, 'RSDW item manifest source must declare its canonical path.');
assert(registry.sources.rsdwtools.repository === 'RSDWArchive/RSDWTools', 'RSDWTools data must use the authoritative RSDWTools repository.');
assert(registry.sources.rsdwtools.branch === 'main', 'RSDWTools data must use its main branch.');
assert(registry.sources.rsdwtools.runtime_component === false, 'RSDWTools must remain a data/content source, not the UE4SS runtime Toolkit.');
assert(registry.sources['rsdw-toolkit'].repository === 'RSDWArchive/RSDWDevKit', 'RSDW Dev Kit must use the authoritative RSDWDevKit repository.');
assert(registry.sources['rsdw-toolkit'].release_url === 'https://github.com/RSDWArchive/RSDWDevKit/releases', 'RSDW Dev Kit must resolve releases from GitHub.');
assert(['server','host'].every((role)=>(registry.sources['rsdw-toolkit'].runtime_roles || []).includes(role)), 'RSDW Dev Kit must declare server/host runtime roles.');
assert(!(registry.sources['rsdw-toolkit'].runtime_roles || []).includes('client'), 'RSDW Dev Kit is server-only and must not be synchronized to clients.');
assert(JSON.stringify(registry.sources.dragonconnect.runtime_roles || []) === JSON.stringify(['client']), 'DragonConnect must be client-only launcher infrastructure.');
assert(registry.sources.dragonconnect.display_name === 'DragonConnect', 'The client Core must use the DragonConnect identity.');
assert(registry.sources.dragonconnect.type === 'bundled-lua-core', 'DragonConnect must remain a bundled Lua Core.');
assert(registry.sources.dragonconnect.bundled_fallback === 'resources/NativeRuntimeMods/DragonConnect', 'DragonConnect must resolve to the bundled Lua Core.');
assert(!registry.sources.dragonconnect.legacy_physical_names, 'Obsolete connector aliases must not remain in the source registry.');
assert(registry.sources.runeschema.repository === 'UnskippableCutscene/RuneSchema', 'RuneSchema updates must use the official upstream repository.');
assert(registry.sources.runeschema.release_url === 'https://github.com/UnskippableCutscene/RuneSchema/releases', 'RuneSchema must resolve official GitHub releases.');
assert(registry.sources.runeschema.bundled_fallback === 'resources/RuneSchema-core-latest.zip', 'RuneSchema must retain the packaged Stable Build.');
assert(registry.sources.ue4ss.repository === 'UE4SS-RE/RE-UE4SS', 'UE4SS updates must use the upstream RE-UE4SS repository.');
assert(registry.sources.ue4ss.release_url === 'https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest', 'UE4SS must resolve the Dragonwilds-compatible upstream channel.');
assert(registry.sources.ue4ss.bundled_fallback === 'resources/DragonwildsServerRuntime/UE4SS-core-latest.zip', 'UE4SS must retain the packaged Stable Build.');

const forbidden = new Set(['command', 'postinstall', 'post_install', 'script', 'powershell', 'shell', 'exec']);
function inspect(value, trail = 'registry') {
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    assert(!forbidden.has(String(key).toLowerCase()), `Unsafe executable registry field at ${trail}.${key}`);
    if (typeof child === 'string' && /_url$/.test(key) && child) assert(/^https:\/\//i.test(child), `Non-HTTPS URL at ${trail}.${key}`);
    inspect(child, `${trail}.${key}`);
  }
}
inspect(registry);

// Settings must be shell-first/offline-first. Opening Runtime & Data may use a
// cached or packaged registry immediately, but it must never wait on GitHub to
// paint the dependency controls.
assert(renderer.includes('const FETCH_TIMEOUT_MS = 3500'), 'Upstream registry network reads must have a bounded timeout.');
assert(renderer.includes('function primeRegistryFromLocal()'), 'Settings must have a local-first registry bootstrap.');
assert(renderer.includes('function refreshRegistryInBackground(page, section)'), 'Remote registry refresh must be background work.');
assert(renderer.includes("const observationRoot=document.getElementById('app')||document.documentElement"), 'Source-panel mutation work must target the app root when available.');
const renderStart = renderer.indexOf('async function renderPanel(page, options = {})');
const renderEnd = renderer.indexOf('\n  function enhance()', renderStart);
assert(renderStart >= 0 && renderEnd > renderStart, 'Could not inspect the Settings source-panel renderer.');
const renderPanel = renderer.slice(renderStart, renderEnd);
const insertionPoint = renderPanel.indexOf("base.insertAdjacentElement('beforebegin',section)");
assert(insertionPoint > 0, 'Settings source panel must still insert into Runtime & Data.');
const firstPaintPath = renderPanel.slice(0, insertionPoint);
assert(firstPaintPath.includes('primeRegistryFromLocal();'), 'Settings source panel must seed from local data before insertion.');
assert(!firstPaintPath.includes('await loadRegistry('), 'Settings source panel must not await remote registry work before first paint.');
assert(renderPanel.includes('refreshRegistryInBackground(page,section)'), 'Settings must refresh GitHub sources only after the local panel is mounted.');

console.log(`upstream source registry checks passed · ${Object.keys(registry.sources).length} sources · Settings local-first paint`);
