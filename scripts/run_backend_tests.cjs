const { spawnSync } = require('child_process');
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
  'backend/test_identity.py','backend/test_sync_safety.py','backend/test_sync_manifest.py','backend/test_recommendation_feeds.py','backend/test_dragon_core_settings.py','backend/test_core_components.py','backend/test_authoritative_mod_taxonomy.py','backend/test_phase2_profile_settings.py','backend/test_shell_persistence_stabilization.py','backend/test_phase3_responsiveness.py','backend/test_editor_webhost_stabilization.py','backend/test_phase4_runtime_startup.py','backend/test_phase6_integration.py','backend/test_cl_authority.py','backend/test_phase3_web.py','backend/test_server_engine.py','backend/test_server_systems.py','backend/test_steamcmd_server_update.py','backend/test_dedicated_post_verify.py','backend/test_managed_updates.py','backend/test_unified_update_status.py','backend/test_phase3_remote_core.py','backend/test_security.py','backend/test_health_model.py','backend/test_service_rpc.py','backend/test_alpha5.py','backend/test_alpha6.py','backend/test_crypto_runtime.py','backend/test_runtime_platforms.py','backend/test_runtime_manager.py','backend/test_orphan_watchdog.py','backend/test_build_contract.py','backend/test_rc2_feedback.py','backend/test_rc2_followup.py','backend/test_v2_integration.py','backend/test_unified_console.py','backend/test_v3_phase2.py','backend/test_v3_phase3.py','backend/test_v3_phase4.py','backend/test_runtime_worker_phase2.py',
];
const windowsHistoricalTests = [
  'backend/test_alpha7.py','backend/test_alpha7_release.py','backend/test_alpha8.py','backend/test_alpha9.py','backend/test_alpha11.py','backend/test_alpha11_2.py','backend/test_alpha12.py','backend/test_alpha12_shared.py','backend/test_alpha13.py','backend/test_release1.py','backend/test_release1_1.py','backend/test_release1_2.py','backend/test_release1_3.py','backend/test_release1_3_1.py','backend/test_release1_3_2_runtime.py','backend/test_release1_4.py','backend/test_release1_4_integrations.py','backend/test_release1_4_directory_host.py','backend/test_release1_4_web_directory_remote.py','backend/test_release1_4_federation_safety.py','backend/test_release1_5_world_browser.py','backend/test_release1_6_character_routes_tunnel.py','backend/test_release1_7_server_adoption.py','backend/test_release1_8_gui_notifications.py','backend/test_v1_1_refinements.py','backend/test_v1_1_1_corrections.py','backend/test_release1_1_2.py','backend/test_release1_1_5.py','backend/test_networking_v1_1_5.py','backend/test_v1_1_9_mod_management.py',
];
const tests=process.platform==='win32'?[...crossPlatformTests.slice(0,28),...windowsHistoricalTests,...crossPlatformTests.slice(28)]:crossPlatformTests;
console.log(`[backend verify] ${process.platform==='win32'?'Windows full V2 regression matrix':'Ubuntu cross-platform RC matrix'} · ${tests.length} test files`);
for(const test of tests){
 const runner='scripts/v3_backend_test_runner.py';
 console.log(`> ${python.command} ${[...python.prefix,runner,test].join(' ')}`);
 const isolatedAppData=fs.mkdtempSync(path.join(os.tmpdir(),'dragonwilds-sync-test-'));
 const env={...process.env,DRAGONWILDS_SYNC_APPDATA:isolatedAppData}; let result;
 try{result=spawnSync(python.command,[...python.prefix,runner,test],{stdio:'inherit',shell:false,env});}
 finally{try{fs.rmSync(isolatedAppData,{recursive:true,force:true});}catch(error){console.warn(`[WARN] Could not remove isolated test AppData ${isolatedAppData}: ${error.message}`);}}
 if(result.error){console.error(`[ERROR] Could not run ${test}: ${result.error.message}`);process.exit(1);} if(result.status!==0)process.exit(result.status||1);
}