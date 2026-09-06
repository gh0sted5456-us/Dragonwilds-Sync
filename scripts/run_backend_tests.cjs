const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const configuredPython = String(process.env.DRAGONWILDS_SYNC_PYTHON || '').trim();
const workspacePython = process.platform === 'win32' ? path.resolve('.venv-build', 'Scripts', 'python.exe') : path.resolve('.venv-build', 'bin', 'python');
const candidates = [
  ...(configuredPython ? [{ command: configuredPython, prefix: [] }] : []),
  { command: workspacePython, prefix: [] },
  ...(process.platform === 'win32' ? [{ command: 'py', prefix: ['-3'] }, { command: 'python', prefix: [] }, { command: 'python3', prefix: [] }] : [{ command: 'python3', prefix: [] }, { command: 'python', prefix: [] }]),
];
function findPython(){for(const candidate of candidates){const probe=spawnSync(candidate.command,[...candidate.prefix,'--version'],{stdio:'ignore',shell:false});if(!probe.error&&probe.status===0)return candidate;}return null;}
const python=findPython(); if(!python){console.error('[ERROR] Python 3 was not found (tried py/python/python3).');process.exit(1);}
const crossPlatformTests = [
  'backend/test_save_delivery.py',
  'backend/test_runtime_update_policy.py',
  'backend/test_mod_deployment_cleanup.py',
  'backend/test_computer_profiles.py','backend/test_remote_user_permissions.py','backend/test_service_subprocess_protocol.py','backend/test_worker_ipc_timeout.py','backend/test_worker_startup_observability.py','backend/test_profile_cache_authority.py','backend/test_state_read_durability.py','backend/test_id_hotload.py',
  'backend/test_headless_cli.py',
  'backend/test_character_item_regression.py',
  'backend/test_character_soft_assignment.py',
  'backend/test_mod_archive_layout.py',
  'backend/test_profile_mod_management_revamp.py',
  'backend/test_profile_mod_pathing_guards.py',
  'backend/test_executable_save_paths.py',
  'backend/test_profile_mod_destination_settings.py',
  'backend/test_runtime_architecture.py',
  'backend/test_setup_ux_regression.py',
  'backend/test_safety_rules_audit.py',
  'backend/test_readme_profile_mod_pathing_contract.py',
  'backend/test_dragonlink_native.py',
  'backend/test_dragonlink_contracts.py',
  'backend/test_external_file_mirror.py',
  'backend/test_hybrid_external_mod_delivery.py',
  'backend/test_hosting_capabilities.py',
  'backend/test_trusted_devices.py',
  'backend/test_complete_reset_runtime_paths.py',
  'backend/test_profile_runtime_paths.py',
  'backend/test_profile_vault.py',
  'backend/test_data_root.py',
  'backend/test_save_management.py',
  'backend/test_worldsave_backup_client.py',
  'backend/test_backup_naming.py',
  'backend/test_v27_release.py',
  'backend/test_v27_13_runtime_profiles.py',
  'backend/test_v27_14_final_cleanup.py',
  'backend/test_v27_15_runeschema_flavor_lock.py',
  'backend/test_runeschema_repository.py',
  'backend/test_runtime_version_archive.py',
  'backend/test_runeschema_063_console.py',
  'backend/test_connection_transport.py',
  'backend/test_live_share_manifest_refresh.py',
  'backend/test_runtime_worker_sync_password.py',
  'backend/test_runtime_worker_directory_heartbeat.py',
  'backend/test_client_launch_once.py',
  'backend/test_direct_connect_route.py',
  'backend/test_connected_snapshot_namespace.py',
  'backend/test_connection_diagnostics.py',
  'backend/test_discovery_profile_lifecycle.py',
  'backend/test_cloudflare_directory_publication.py',
  'backend/test_world_directory_v3_heartbeat.py',
  'backend/test_connected_world_reviews.py',
  'backend/test_identity.py','backend/test_profile_play_time.py','backend/test_connected_world_identity.py','backend/test_dedicated_config_and_route_retention.py','backend/test_player_backups.py','backend/test_official_runeschema_restore.py','backend/test_worldsave_import.py','backend/test_sync_safety.py','backend/test_sync_manifest.py','backend/test_mod_hash_isolation.py','backend/test_system_process_catalog.py','backend/test_recommendation_feeds.py','backend/test_core_components.py','backend/test_authoritative_mod_taxonomy.py','backend/test_phase2_profile_settings.py','backend/test_shell_persistence_stabilization.py','backend/test_phase3_responsiveness.py','backend/test_editor_webhost_stabilization.py','backend/test_phase4_runtime_startup.py','backend/test_phase6_integration.py','backend/test_phase6_background_completion.py','backend/test_dragonconnect_autohandoff.py','backend/test_cl_authority.py','backend/test_phase3_web.py','backend/test_server_engine.py','backend/test_server_systems.py','backend/test_steamcmd_server_update.py','backend/test_dedicated_post_verify.py','backend/test_managed_updates.py','backend/test_runtime_cache_compat.py','backend/test_runtime_reset_window_contract.py','backend/test_unified_update_status.py','backend/test_phase3_remote_core.py','backend/test_security.py','backend/test_health_model.py','backend/test_service_rpc.py','backend/test_alpha5.py','backend/test_alpha6.py','backend/test_crypto_runtime.py','backend/test_runtime_platforms.py','backend/test_runtime_archive_policy.py','backend/test_runtime_client_selection_publish.py','backend/test_runtime_manager.py','backend/test_orphan_watchdog.py','backend/test_build_contract.py','backend/test_rc2_feedback.py','backend/test_rc2_followup.py','backend/test_v2_integration.py','backend/test_unified_console.py','backend/test_runtime_console_policy.py','backend/test_runeschema_tools.py','backend/test_ue4ss_repository.py','backend/test_v3_phase1.py','backend/test_v3_phase2.py','backend/test_v3_phase3.py','backend/test_v3_phase4.py','backend/test_runtime_worker_phase2.py','backend/test_runtime_worker_config.py','backend/test_phase5_runtime_worker_bridge.py','backend/test_feature_workers.py','backend/test_experimental_dedicated_mod_sync.py','backend/test_website_draft_import.py',
];
const windowsHistoricalTests = [
  'backend/test_alpha7.py','backend/test_alpha7_release.py','backend/test_alpha8.py','backend/test_alpha9.py','backend/test_alpha11.py','backend/test_alpha11_2.py','backend/test_alpha12.py','backend/test_alpha12_shared.py','backend/test_alpha13.py','backend/test_release1.py','backend/test_release1_1.py','backend/test_release1_1_3.py','backend/test_release1_2.py','backend/test_release1_3.py','backend/test_release1_3_1.py','backend/test_release1_3_2_runtime.py','backend/test_release1_4.py','backend/test_release1_4_integrations.py','backend/test_release1_4_directory_host.py','backend/test_release1_4_web_directory_remote.py','backend/test_release1_4_federation_safety.py','backend/test_release1_4_spawner.py','backend/test_release1_5_world_browser.py','backend/test_release1_6_character_routes_tunnel.py','backend/test_release1_7_server_adoption.py','backend/test_release1_8_gui_notifications.py','backend/test_v1_1_refinements.py','backend/test_v1_1_1_corrections.py','backend/test_release1_1_2.py','backend/test_release1_1_5.py','backend/test_networking_v1_1_5.py','backend/test_v1_1_9_mod_management.py','backend/test_windows_atomic_replace.py',
];
const tests=process.platform==='win32'?[...crossPlatformTests.slice(0,30),...windowsHistoricalTests,...crossPlatformTests.slice(30)]:crossPlatformTests;
const isolatedCiPreflights=new Set(['backend/test_remote_user_permissions.py','backend/test_service_subprocess_protocol.py','backend/test_worker_ipc_timeout.py','backend/test_worker_startup_observability.py','backend/test_state_read_durability.py','backend/test_id_hotload.py','backend/test_character_item_regression.py','backend/test_character_soft_assignment.py']);
if(process.argv.includes('--list')){
 console.log(JSON.stringify(tests.filter(test=>process.env.GITHUB_ACTIONS!=='true'||!isolatedCiPreflights.has(test))));
 process.exit(0);
}
console.log(`[backend verify] ${process.platform==='win32'?'Windows full V2 regression matrix':'Ubuntu cross-platform RC matrix'} · ${tests.length} test files`);
async function runIsolatedTest(test, runner){
 const isolatedAppData=fs.mkdtempSync(path.join(os.tmpdir(),'dragonwilds-sync-test-'));
 // Legacy modules cache Windows app-data paths at import time, before a test
 // installs its fixture. Never let reset/backup tests discover real game saves.
 const localAppData=path.join(isolatedAppData,'LocalAppData');
 const roamingAppData=path.join(isolatedAppData,'RoamingAppData');
 fs.mkdirSync(localAppData,{recursive:true});fs.mkdirSync(roamingAppData,{recursive:true});
 try{
  return await new Promise(resolve=>{
   const child=spawn(python.command,[...python.prefix,runner,test],{stdio:'inherit',shell:false,env:{...process.env,DRAGONWILDS_SYNC_APPDATA:isolatedAppData,LOCALAPPDATA:localAppData,APPDATA:roamingAppData}});
   child.once('error',error=>resolve({error,status:null}));
   child.once('close',status=>resolve({error:null,status}));
  });
 } finally {
  try{fs.rmSync(isolatedAppData,{recursive:true,force:true});}catch(error){console.warn(`[WARN] Could not remove isolated test AppData ${isolatedAppData}: ${error.message}`);}
 }
}
async function main(){
for(const test of tests){
 if(process.env.GITHUB_ACTIONS==='true'&&isolatedCiPreflights.has(test)){
  console.log(`> ${test} already passed as an isolated workflow preflight`);
  continue;
 }
 const runner='scripts/v3_backend_test_runner.py';
 console.log(`> ${python.command} ${[...python.prefix,runner,test].join(' ')}`);
 let result=await runIsolatedTest(test,runner);
 if(process.env.GITHUB_ACTIONS==='true'&&!result.error&&result.status!==0){
  console.warn(`[WARN] ${test} failed in the shared Windows job; retrying once with fresh process state.`);
  result=await runIsolatedTest(test,runner);
 }
 if(result.error){console.error(`[ERROR] Could not run ${test}: ${result.error.message}`);process.exit(1);}
 if(result.status!==0){
  if(process.env.GITHUB_ACTIONS==='true')console.error(`::error file=${test},line=1::Backend regression failed: ${test}`);
  process.exit(result.status||1);
 }
}
}
main().catch(error=>{console.error(error);process.exit(1);});
