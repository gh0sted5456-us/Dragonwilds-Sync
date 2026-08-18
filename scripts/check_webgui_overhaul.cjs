const fs = require('fs');

function read(path) { return fs.readFileSync(path, 'utf8'); }
function requireText(haystack, needle, label) {
  if (!haystack.includes(needle)) throw new Error(`WebGUI overhaul contract missing ${label || needle}`);
}

const index = read('renderer/index.html');
const release = read('renderer/release-webgui-overhaul.js');
const css = read('renderer/release-webgui-overhaul.css');
const service = read('backend/dragonwilds_service.py');
const consoleModule = read('backend/unified_console.py');
const recommendations = read('backend/recommendation_feeds.py');
const spec = read('backend/DragonwildsSync.Service.spec');
const directoryHost = read('backend/directory_host.py');
const runner = read('scripts/run_backend_tests.cjs');

requireText(index, 'release-webgui-overhaul.css', 'overhaul stylesheet load');
requireText(index, 'release-webgui-overhaul.js', 'overhaul script load');
requireText(index, "img-src 'self' data: file: http://127.0.0.1:* https:;", 'remote recommendation artwork CSP');

requireText(release, 'dws-recommended-media', 'recommended-mod artwork cards');
requireText(release, 'Direct Download', 'curator-provided direct-download action');
requireText(release, 'dws-native-context-detail', 'Item Editor rich context card');
requireText(release, 'Right-click for full item details', 'Spawner item inspector');
requireText(release, 'server.console.unified', 'unified console polling');
requireText(release, "data-dws-console-filter=\"game\"", 'game console filter');
requireText(release, "data-dws-console-filter=\"server\"", 'server console filter');
requireText(release, "data-dws-console-filter=\"sync\"", 'sync console filter');
requireText(css, '.dws-console-row.source-game', 'game console colour');
requireText(css, '.dws-console-row.source-server', 'server console colour');
requireText(css, '.dws-console-row.source-sync', 'sync console colour');

requireText(service, 'install_engine_session_hook(_legacy.ENGINE)', 'per-process session log hook');
requireText(service, 'if method == "server.console.unified":', 'unified console RPC');
requireText(consoleModule, 'DragonwildsSync.previous.log', 'previous-session rotation');
requireText(consoleModule, 'Streams: GAME COMMANDS | SERVER | SYNC TRAFFIC', 'merged text log contract');
requireText(runner, 'backend/test_unified_console.py', 'unified console regression test');

requireText(recommendations, '_enrich_public_artwork', 'public artwork enrichment');
requireText(recommendations, '"banner_url"', 'banner URL feed field');
requireText(recommendations, '"icon_url"', 'icon URL feed field');
requireText(recommendations, '"download_url"', 'direct download feed field');

// The original WebHost platform icon packaging bug must remain permanently
// covered both in PyInstaller data collection and the source/one-file resolver.
requireText(spec, "renderer/assets/platforms", 'PyInstaller platform SVG bundle');
requireText(directoryHost, 'Path(bundle_root) / "renderer" / "assets" / "platforms" / filename', 'one-file platform icon resolver');
requireText(directoryHost, 'path.startswith("/assets/platforms/")', 'WebHost platform icon route');

console.log('WebGUI overhaul contract checks passed');
