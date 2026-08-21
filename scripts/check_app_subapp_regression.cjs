const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const protocol = read('backend/feature_worker_protocol.py');
const implementationFiles = [
  'renderer/app-v2.js', 'renderer/release-phase2.js', 'renderer/release-phase3.js',
  'electron/main-v2.cjs', 'electron/preload-v2.cjs',
  'backend/dragonwilds_service.py', 'backend/dragonwilds_service_v2_wrapper.py',
  'backend/dragonwilds_service_legacy.py', 'backend/character_profiles.py',
  'backend/world_save_editor.py', 'backend/spawner_catalog.py', 'backend/sync_engine.py',
  'backend/server_systems.py', 'backend/directory_host.py', 'backend/directory_web_legacy.py',
  'backend/system_process_catalog.py', 'backend/feature_worker.py',
  'website/script.js', 'website/placards.js',
];
const implementation = implementationFiles.map((file) => `\n/* ${file} */\n${read(file)}`).join('');

function fail(message) { throw new Error(message); }
function subappsFor(application) {
  const escaped = application.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = protocol.match(new RegExp(`"${escaped}"\\s*:\\s*\\{[\\s\\S]*?"subapps"\\s*:\\s*\\[([^\\]]*)\\]`));
  if (!match) fail(`Missing application identity ${application}`);
  return [...match[1].matchAll(/"([^"]+)"/g)].map((row) => row[1]);
}

const expected = {
  shell: ['navigation', 'settings', 'help', 'in-app-windows', 'quick-launch'],
  worlds: ['placards', 'private-worlds', 'hosted-worlds', 'world-save-editor', 'manifests', 'world-map'],
  characters: ['character-creator', 'character-3d', 'appearance', 'inventory', 'modded-item-repository'],
  'rsdw-l': ['character-editor', 'item-editor', 'spell-editor', 'recipe-unlocker', 'quest-editor', 'live-map', 'spawner', 'console'],
  mods: ['found-mods', 'mod-explorer', 'monaco-mod-editor', 'shared-mod-repository', 'load-order', 'runtime-metadata'],
  rsdragonwilds: ['singleplayer', 'co-op', 'dedicated-server'],
  sync: ['heartbeat', 'p2p-transfer', 'mod-sync', 'directory'],
  webgui: ['directory-browser', 'remote-login', 'remote-console'],
  system: ['launcher-update', 'server-update', 'runtime-update', 'security', 'network-diagnostics', 'integrations'],
};

// Each identity must resolve to implementation evidence outside the identity
// registry. These are workflow/RPC symbols, not the registry display labels.
const evidence = {
  navigation: ['renderPersistentShell'], settings: ['renderSettings'], help: ['renderHelp'],
  'in-app-windows': ['prepareDesktopWindow'], 'quick-launch': ['runQuickLaunch'],
  placards: ['placardFrontClassificationMarkup'], 'private-worlds': ['privateWorldById'],
  'hosted-worlds': ['serverWorlds()'], 'world-save-editor': ['world.save.editor.write'],
  manifests: ['sync_manifest'], 'world-map': ['ensureAshenfallMap'],
  'character-creator': ['character-equipment-studio'], 'character-3d': ['rsdw-avatar-webview'],
  appearance: ['nativeAppearanceField'], inventory: ['nativeItemEditorMarkup'],
  'modded-item-repository': ['openCustomItemRepository'],
  'character-editor': ['nativeCharacterEditorMarkup'], 'item-editor': ['characters.native.tool.preview'],
  'spell-editor': ['nativeSpellEditorMarkup'], 'recipe-unlocker': ['nativeRecipeEditorMarkup'],
  'quest-editor': ['nativeQuestEditorMarkup'], 'live-map': ['renderRsdwLiveMap'],
  spawner: ['refreshServerSpawner'], console: ['refreshServerConsole'],
  'found-mods': ['refresh-mod-repository'], 'mod-explorer': ['openModExplorer'],
  'monaco-mod-editor': ['loadMonaco'], 'shared-mod-repository': ['mod.repository.list'],
  'load-order': ['data-mod-move'], 'runtime-metadata': ['ID.txt'],
  singleplayer: ['singleplayer.play'], 'co-op': ['singleplayer.broadcast'],
  'dedicated-server': ['server.runtime.start'], heartbeat: ['world.discovery.heartbeat'],
  'p2p-transfer': ['download_entry'], 'mod-sync': ['sync_world'], directory: ['world.directory.join.link'],
  'directory-browser': ['public_browser_html'], 'remote-login': ['/admin/login'],
  'remote-console': ['server.console.unified'], 'launcher-update': ['application.update_status.record'],
  'server-update': ['server.runtime.update'], 'runtime-update': ['application.core_mod.update'],
  security: ['security.defender.status'], 'network-diagnostics': ['world.network.test'],
  integrations: ['hydrateIntegrations'],
};

let count = 0;
for (const [application, wanted] of Object.entries(expected)) {
  const actual = subappsFor(application);
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    fail(`${application} subapp drift: expected ${wanted.join(', ')}, found ${actual.join(', ')}`);
  }
  for (const subapp of wanted) {
    const tokens = evidence[subapp];
    if (!tokens?.length) fail(`No implementation evidence configured for ${application}/${subapp}`);
    for (const token of tokens) {
      if (!implementation.includes(token)) fail(`${application}/${subapp} lost implementation evidence ${JSON.stringify(token)}`);
    }
    count += 1;
  }
}

if (!implementation.includes('from editor_runtime_stabilization import install as _install_editor_runtime_stabilization')) {
  fail('Source service launch does not install the Character/Item editor fallback');
}
if (!implementation.includes('f"rsdw-{stamp}-{time.time_ns()}-{target.name}"')) {
  fail('Character writeback backups are not unique per Apply');
}
for (const method of [
  'application.custom_items.list', 'application.custom_items.discover', 'application.custom_items.icons',
  'application.custom_items.create', 'application.custom_items.delete', 'application.custom_items.write_to_mod',
  'application.custom_items.export', 'application.custom_items.import',
]) {
  if (!implementation.includes(method)) fail(`Item repository RPC missing: ${method}`);
}

console.log(`Current Appy/subapp implementation contract: PASS · ${Object.keys(expected).length} applications · ${count} subapps`);
