'use strict';

// Whole-tree entrypoint and ownership contract. This deliberately checks build
// assembly as well as direct imports so PyInstaller hooks are not falsely
// reported as dead code. Website deployment now belongs to its separate repo.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const list = (directory, extension) => fs.readdirSync(path.join(root, directory))
  .filter((file) => file.endsWith(extension)).sort();
const fail = (message) => { throw new Error(`source ownership contract: ${message}`); };
const need = (text, token, label) => { if (!text.includes(token)) fail(`${label} lost ${JSON.stringify(token)}`); };

const packageJson = JSON.parse(read('package.json'));
const bootstrap = read('electron/bootstrap.cjs');
const main = read('electron/main.cjs');
const electronMain = read('electron/main-v2.cjs');
const rendererHtml = list('renderer', '.html').map((file) => read(`renderer/${file}`)).join('\n');
const websiteHtml = list('website', '.html').map((file) => read(`website/${file}`)).join('\n');

if (packageJson.main !== 'electron/bootstrap.cjs') fail(`package main is unclassified: ${packageJson.main}`);
need(bootstrap, "require('./main.cjs')", 'Electron bootstrap parent');
need(main, "require('./main-v2.cjs')", 'Electron argument-adapter parent');
need(electronMain, "preload: path.join(__dirname, 'preload-v2.cjs')", 'sandbox renderer parent');
need(electronMain, "path.join(projectRoot(), 'backend', 'dragonwilds_service.py')", 'Core subprocess parent');

// preload.cjs is not a live BrowserWindow preload. It remains only as a tiny
// historical redirect to preload-v2.cjs so old source-contract fixtures do not
// carry or exercise a second bridge implementation.
if (/preload:\s*path\.join\(__dirname,\s*['"]preload\.cjs['"]\)/.test(electronMain)) {
  fail('compatibility preload.cjs was reintroduced as a live sandbox preload');
}
need(read('electron/preload.cjs'), "require('./preload-v2.cjs')", 'preload compatibility redirect');
need(read('scripts/v3_contract_runner.cjs'), "electron', 'preload.cjs'", 'preload compatibility lane');
need(read('scripts/v3_backend_test_runner.py'), 'electron" / "preload.cjs"', 'backend preload compatibility lane');

const rendererScripts = new Set(list('renderer', '.js'));
const rendererStyles = new Set(list('renderer', '.css'));
const referencedAssets = (text, extension) => new Set(
  [...text.matchAll(new RegExp(`["']([^"']+\\.${extension})(?:\\?[^"']*)?["']`, 'g'))]
    .map((row) => path.basename(row[1])),
);
const liveRendererScripts = referencedAssets(rendererHtml, 'js');
const liveRendererStyles = referencedAssets(rendererHtml, 'css');
if (read('renderer/app.js').includes('app-v2.js')) liveRendererScripts.add('app-v2.js');
for (const file of rendererScripts) if (!liveRendererScripts.has(file)) fail(`unowned renderer script: renderer/${file}`);
for (const file of rendererStyles) if (!liveRendererStyles.has(file)) fail(`unowned renderer stylesheet: renderer/${file}`);

const websiteScripts = list('website', '.js');
const websiteStyles = list('website', '.css');
const websiteMigrationFragments = new Set([
  'download-flip.css', 'download-flip.js', 'home-demo.css', 'placard-detail-popovers.css',
  'placard-enhancements.css', 'placard-enhancements.js', 'placards.css', 'placards.js',
  'platform-assets.js', 'server-build.js', 'top-flow.css', 'top-flow.js',
]);
for (const file of [...websiteScripts, ...websiteStyles]) {
  const directlyLoaded = websiteHtml.includes(file);
  if (!directlyLoaded && !websiteMigrationFragments.has(file)) fail(`unowned website source: website/${file}`);
}

// Python runtime hooks are referenced by the PyInstaller spec rather than by a
// normal import. Include the spec and test/build sources in the reference graph
// before flagging a module as unowned.
const backendFiles = list('backend', '.py');
const backendModules = backendFiles.filter((file) => !file.startsWith('test_'));
const backendReferenceText = [
  ...backendFiles.map((file) => read(`backend/${file}`)),
  read('backend/DragonwildsSync.Service.spec'),
  ...list('scripts', '.cjs').map((file) => read(`scripts/${file}`)),
  ...list('scripts', '.py').map((file) => read(`scripts/${file}`)),
].join('\n');
const backendEntrypoints = new Set([
  'dragonwilds_service.py', 'runtime_worker.py', 'feature_worker.py', 'orphan_watchdog.py',
  'packaged_stdio_guard.py', 'web_release_polish_hook.py', 'external_mod_hosting_hook.py',
]);
for (const file of backendModules) {
  if (backendEntrypoints.has(file)) continue;
  const moduleName = file.slice(0, -3);
  const referenced = [
    `from ${moduleName} import`, `import ${moduleName}`, `import_module("${moduleName}")`,
    `import_module('${moduleName}')`, `'${moduleName}'`, `"${moduleName}"`,
  ].some((token) => backendReferenceText.includes(token));
  if (!referenced) fail(`unowned backend module: backend/${file}`);
}

const service = read('backend/dragonwilds_service.py');
if (read('backend/feature_worker_protocol.py').includes('"label": "RSDragonwilds"')) {
  fail('obsolete RSDragonwilds user-facing Appy label returned');
}
for (const method of ['feature.worker.list', 'feature.worker.prepare', 'feature.worker.status', 'feature.worker.acquire', 'feature.worker.release', 'feature.worker.stop', 'feature.worker.execute']) {
  need(service, `method == "${method}"`, 'diagnostic feature-worker RPC classification');
}

console.log(`Source ownership contract: PASS · ${rendererScripts.size + rendererStyles.size} renderer assets · ${websiteScripts.length + websiteStyles.length} website sources · ${backendModules.length} backend modules · 1 redirect-only preload shim · 7 diagnostic worker RPCs`);
