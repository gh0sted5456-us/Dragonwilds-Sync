const fs = require('node:fs');
const path = require('path');

const registryPath = path.join(__dirname, '..', 'docs', 'upstream-sources.json');
const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
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
assert(registry.sources.rsdwtools.runtime_component === false, 'RSDWTools must remain a data/content source, not the UE4SS runtime Toolkit.');
assert(registry.sources['rsdw-toolkit'].repository === 'RSDWArchive/RSDWDevKit', 'RSDW Toolkit / DevKit must use the authoritative RSDWDevKit repository.');
assert(['server','host'].every((role)=>(registry.sources['rsdw-toolkit'].runtime_roles || []).includes(role)), 'RSDW Dev Kit must declare server/host runtime roles.');
assert(!(registry.sources['rsdw-toolkit'].runtime_roles || []).includes('client'), 'RSDW Dev Kit is server-only and must not be synchronized to clients.');
assert(['client','server','host'].every((role)=>(registry.sources.dragonconnect.runtime_roles || []).includes(role)), 'DragonConnect must be baseline infrastructure for hosts and clients.');
assert(['DragonConnectHelper','PersistentDirectConnectIP'].every((name)=>(registry.sources.dragonconnect.legacy_physical_names || []).includes(name)), 'DragonLink-Connect must retain both legacy physical identities during compatibility migration.');
assert(registry.sources.runeschema.download_url || registry.sources.runeschema.bundled_fallback, 'RuneSchema needs a remote or bundled source.');
assert(registry.sources.ue4ss.release_url || registry.sources.ue4ss.download_url, 'UE4SS needs an update source.');

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

console.log(`upstream source registry checks passed · ${Object.keys(registry.sources).length} sources`);
