const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const version = String(process.argv[2] || '').trim().replace(/^v/i, '');
if (!/^\d+\.\d+\.\d+$/.test(version)) {
  console.error('Usage: node scripts/stamp_release_version.cjs <major.minor.patch>');
  process.exit(2);
}

function writeJson(relative, mutate) {
  const file = path.join(root, relative);
  const value = JSON.parse(fs.readFileSync(file, 'utf8'));
  mutate(value);
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

writeJson('package.json', (value) => { value.version = version; });
writeJson('package-lock.json', (value) => {
  value.version = version;
  if (value.packages?.['']) value.packages[''].version = version;
});
writeJson('docs/changelog.json', (value) => {
  const release = Array.isArray(value.releases) ? value.releases[0] : null;
  if (!release) throw new Error('docs/changelog.json has no consolidated release');
  release.version = version;
  if (Array.isArray(release.highlights)) {
    release.highlights = release.highlights.map((item) => String(item).replace(
      /Windows remains portable-only in version \d+\.\d+\.\d+/,
      `Windows remains portable-only in version ${version}`,
    ));
  }
});

function replaceVersion(relative, pattern, replacement) {
  const file = path.join(root, relative);
  const original = fs.readFileSync(file, 'utf8');
  if (!pattern.test(original)) throw new Error(`Could not locate version field in ${relative}`);
  const updated = original.replace(pattern, replacement);
  fs.writeFileSync(file, updated, 'utf8');
}

replaceVersion(
  'backend/runtime_versions.py',
  /DRAGONWILDS_SYNC_VERSION\s*=\s*"\d+\.\d+\.\d+"/,
  `DRAGONWILDS_SYNC_VERSION = "${version}"`,
);
for (const relative of ['backend/dragonwilds_service.py', 'backend/v3_exchange.py']) {
  const file = path.join(root, relative);
  const original = fs.readFileSync(file, 'utf8');
  const appVersionPattern = /app_version(?:\s*:\s*str)?\s*=\s*"\d+\.\d+\.\d+"/g;
  if (!appVersionPattern.test(original)) throw new Error(`Could not locate app_version in ${relative}`);
  appVersionPattern.lastIndex = 0;
  const updated = original.replace(appVersionPattern, (match) => (
    match.replace(/"\d+\.\d+\.\d+"/, `"${version}"`)
  ));
  fs.writeFileSync(file, updated, 'utf8');
}

const metaPath = path.join(root, 'renderer', 'release-meta.js');
let meta = fs.readFileSync(metaPath, 'utf8');
meta = meta.replace(/version:\s*'\d+\.\d+\.\d+'/, `version: '${version}'`);
meta = meta.replace(/"name":\s*"V\d+\.\d+(?:\.\d+)?"/, `"name": "V${version}"`);
fs.writeFileSync(metaPath, meta, 'utf8');

const buildPath = path.join(root, 'build.bat');
let build = fs.readFileSync(buildPath, 'utf8');
build = build.replace(/Dragonwilds Sync \d+\.\d+\.\d+ - Portable Build/g, `Dragonwilds Sync ${version} - Portable Build`);
build = build.replace(/Dragonwilds Sync \d+\.\d+\.\d+ - Portable Windows Build/g, `Dragonwilds Sync ${version} - Portable Windows Build`);
fs.writeFileSync(buildPath, build, 'utf8');

console.log(`Stamped Dragonwilds Sync release metadata as ${version}`);
