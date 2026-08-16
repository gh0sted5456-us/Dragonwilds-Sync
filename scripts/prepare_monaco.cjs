const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const expectedVersion = '0.52.2';
const packagePath = path.join(root, 'node_modules', 'monaco-editor', 'package.json');
const source = path.join(root, 'node_modules', 'monaco-editor', 'min', 'vs');
const target = path.join(root, 'renderer', 'vendor', 'monaco', 'vs');

if (!fs.existsSync(packagePath)) {
  console.error(`Monaco Editor ${expectedVersion} is not installed. Run npm install first.`);
  process.exit(2);
}

let installedVersion = '';
try {
  installedVersion = String(JSON.parse(fs.readFileSync(packagePath, 'utf8')).version || '');
} catch (error) {
  console.error(`Could not read Monaco Editor package metadata: ${error.message}`);
  process.exit(2);
}

// Dragonwilds Sync currently embeds Monaco through its AMD loader. Monaco 0.53+
// deprecated/changed that build, so keep this dependency on the last compatible
// 0.52.x line until the renderer is deliberately migrated to ESM.
if (installedVersion !== expectedVersion) {
  console.error(`Incompatible Monaco Editor version: found ${installedVersion || 'unknown'}, expected ${expectedVersion}.`);
  console.error('Run npm install so package.json can restore the pinned AMD-compatible runtime.');
  process.exit(2);
}

const requiredRelative = [
  'loader.js',
  path.join('editor', 'editor.main.js'),
  path.join('base', 'worker', 'workerMain.js'),
];

for (const relative of requiredRelative) {
  const required = path.join(source, relative);
  if (!fs.existsSync(required)) {
    console.error(`Installed Monaco ${installedVersion} is incomplete; required file is missing: ${required}`);
    process.exit(3);
  }
}

// Dragonwilds Sync's loadMonaco() only ever creates editors with
// language: 'json' | 'lua' | 'ini' | 'plaintext' (renderer/app.js), and
// never configures a non-English NLS locale. The upstream `min/vs` build
// ships every basic-language tokenizer, the full TypeScript/CSS/HTML
// language services (worker files alone: ~5.7MB/0.8MB/0.4MB), and every
// localization bundle -- none of it reachable from this app. Copying only
// what's actually used keeps the packaged app byte-identical in behavior
// while cutting several MB of pure dead weight from every build.
const copyOnly = [
  'loader.js',
  'editor', // editor.main.js / editor.main.css -- the core editor itself
  'base', // worker bootstrap + browser/ui assets (incl. codicons the editor chrome renders)
  path.join('basic-languages', 'ini'),
  path.join('basic-languages', 'lua'),
  path.join('language', 'json'), // full JSON language service (validation, not just a tokenizer)
];

fs.rmSync(target, { recursive: true, force: true });
fs.mkdirSync(path.dirname(target), { recursive: true });
for (const relative of copyOnly) {
  const from = path.join(source, relative);
  if (!fs.existsSync(from)) continue; // optional pieces (e.g. a renamed folder in a future Monaco release) never hard-fail the build
  fs.cpSync(from, path.join(target, relative), { recursive: true });
}

for (const relative of requiredRelative) {
  const required = path.join(target, relative);
  if (!fs.existsSync(required)) {
    console.error(`Bundled Monaco file missing after copy: ${required}`);
    process.exit(3);
  }
}

console.log(`Bundled Monaco Editor ${installedVersion} (trimmed to json/lua/ini + core) into ${path.relative(root, target)}`);
