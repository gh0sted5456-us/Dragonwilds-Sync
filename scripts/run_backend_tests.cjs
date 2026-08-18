const { spawnSync } = require('child_process');
const path = require('path');

const configuredPython = String(process.env.DRAGONWILDS_SYNC_PYTHON || '').trim();
const workspacePython = process.platform === 'win32'
  ? path.resolve('.venv-build', 'Scripts', 'python.exe')
  : path.resolve('.venv-build', 'bin', 'python');
const candidates = [
  ...(configuredPython ? [{ command: configuredPython, prefix: [] }] : []),
  { command: workspacePython, prefix: [] },
  ...(process.platform === 'win32'
  ? [{ command: 'py', prefix: ['-3'] }, { command: 'python', prefix: [] }, { command: 'python3', prefix: [] }]
  : [{ command: 'python3', prefix: [] }, { command: 'python', prefix: [] }]),
];

function findPython() {
  for (const candidate of candidates) {
    const probe = spawnSync(candidate.command, [...candidate.prefix, '--version'], { stdio: 'ignore', shell: false });
    if (!probe.error && probe.status === 0) return candidate;
  }
  return null;
}

const python = findPython();
if (!python) {
  console.error('[ERROR] Python 3 was not found (tried py/python/python3).');
  process.exit(1);
}

const crossPlatformTests = [
  'backend/test_identity.py',
  'backend/test_sync_safety.py',
  'backend/test_sync_manifest.py',
  'backend/test_recommendation_feeds.py',
  'backend/test_dragon_core_settings.py',
  'backend/test_server_engine.py',
  'backend/test_server_systems.py',
  'backend/test_steamcmd_server_update.py',
  'backend/test_dedicated_post_verify.py',
  'backend/test_managed_updates.py',
  'backend/test_unified_update_status.py',
  'backend/test_security.py',
  'backend/test_health_model.py',
  'backend/test_service_rpc.py',
  'backend/test_alpha5.py',
  'backend/test_alpha6.py',
  'backend/test_crypto_runtime.py',
  'backend/test_runtime_platforms.py',
  'backend/test_runtime_manager.py',
  'backend/test_orphan_watchdog.py',
  'backend/test_build_contract.py',
  'backend/test_rc2_feedback.py',
  'backend/test_rc2_followup.py',
  'backend/test_v2_integration.py',
  'backend/test_unified_console.py',
];

// Windows remains the production/V2 baseline and therefore runs every
// historical regression suite. Ubuntu runs the platform-safe core above plus
// its explicit runtime/platform contract. Older Alpha fixtures deliberately
// model Windows loader DLL ownership and must not be reinterpreted as native
// Linux behavior merely to make CI green.
const windowsHistoricalTests = [
  'backend/test_alpha7.py',
  'backend/test_alpha7_release.py',
  'backend/test_alpha8.py',
  'backend/test_alpha9.py',
  'backend/test_alpha11.py',
  'backend/test_alpha11_2.py',
  'backend/test_alpha12.py',
  'backend/test_alpha12_shared.py',
  'backend/test_alpha13.py',
  'backend/test_release1.py',
  'backend/test_release1_1.py',
  'backend/test_release1_2.py',
  'backend/test_release1_3.py',
  'backend/test_release1_3_1.py',
  'backend/test_release1_3_2_runtime.py',
  'backend/test_release1_4.py',
  'backend/test_release1_4_integrations.py',
  'backend/test_release1_4_directory_host.py',
  'backend/test_release1_4_web_directory_remote.py',
  'backend/test_release1_4_federation_safety.py',
  'backend/test_release1_5_world_browser.py',
  'backend/test_release1_6_character_routes_tunnel.py',
  'backend/test_release1_7_server_adoption.py',
  'backend/test_release1_8_gui_notifications.py',
  'backend/test_v1_1_refinements.py',
  'backend/test_v1_1_1_corrections.py',
  'backend/test_release1_1_2.py',
  // Release 1.1.3 validated the retired bundled AssetCatalog companion.
  'backend/test_release1_1_5.py',
  'backend/test_networking_v1_1_5.py',
  'backend/test_v1_1_9_mod_management.py',
];

const tests = process.platform === 'win32'
  ? [...crossPlatformTests.slice(0, 17), ...windowsHistoricalTests, ...crossPlatformTests.slice(17)]
  : crossPlatformTests;

console.log(`[backend verify] ${process.platform === 'win32' ? 'Windows full V2 regression matrix' : 'Ubuntu cross-platform RC matrix'} · ${tests.length} test files`);
for (const test of tests) {
  console.log(`> ${python.command} ${[...python.prefix, test].join(' ')}`);
  const result = spawnSync(python.command, [...python.prefix, test], { stdio: 'inherit', shell: false });
  if (result.error) {
    console.error(`[ERROR] Could not run ${test}: ${result.error.message}`);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status || 1);
}
