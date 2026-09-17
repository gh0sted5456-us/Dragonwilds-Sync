const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`${label}: missing ${JSON.stringify(needle)}`);
};
const forbidText = (text, needle, label) => {
  if (text.includes(needle)) throw new Error(`${label}: forbidden ${JSON.stringify(needle)}`);
};

const index = read('renderer/index.html');
const phase2 = read('renderer/release-phase2.js');
const appV2 = read('renderer/app-v2.js');
// profile_settings.py is the current V3 adapter; profile_settings_v1.py owns the
// retained WorldProfileSettings.v1 implementation it extends in place.
const profileSettings = read('backend/profile_settings.py') + '\n' + read('backend/profile_settings_v1.py');
const routing = read('backend/v2_remote_routing.py');
const runner = read('scripts/run_backend_tests.cjs');
const loaderRepository = read('backend/loader_repository.py');
const deployment = read('backend/mod_deployment_cleanup.py');
const syncEngine = read('backend/sync_engine.py');

requireText(index, 'release-phase2.css', 'Phase 2 stylesheet');
requireText(index, 'release-phase2.js', 'Phase 2 renderer');
requireText(phase2, '+ Direct Connect', 'World Management Direct Connect action');
forbidText(phase2, 'See in Explorer', 'redundant profile Explorer button');
forbidText(phase2, 'View Mods', 'redundant profile Mods button');
requireText(appV2, 'data-action="profile-mod-storage"', 'profile card AppData context action');
requireText(appV2, "openProfileMods('server',id)", 'server profile AppData opener');
requireText(appV2, "openProfileMods('local',id)", 'local profile AppData opener');
requireText(phase2, 'WORLD SAVE LOADED', 'loaded save indicator');
requireText(phase2, 'NO WORLD SAVE LOADED', 'empty save indicator');
requireText(phase2, "invoke('server.world.save.status'", 'dedicated save evidence');
for (const group of ["['Profile'", "['Tools'", "['Hosting'", "['Roster'"]) requireText(phase2, group, `consolidated tab group ${group}`);
forbidText(phase2, 'window.location.reload', 'World Management must not reload the renderer');
for (const token of [
  'openRuntimeBuildManager(kind)',
  'RuneSchema Version Manager',
  'UE4SS Version Manager',
  'data-runtime-build-check',
  'data-runtime-build-delete-selected',
  'Publish / stored date',
  'manage-runeschema-builds',
  'manage-ue4ss-builds',
]) forbidText(appV2, token, `retired shared runtime version manager ${token}`);
for (const token of [
  "['UE4SSLoader','UE4SS Loader']",
  "['RuneSchemaLoader','RuneSchema Loader']",
  'loaders/ue4ss',
  'loaders/runeschema',
]) requireText(appV2, token, `World-owned runtime staging ${token}`);
for (const token of ['Edit Mod Loaders', 'Install Verified Loaders', 'profile.loaders.install', 'dws:manage-profile-loaders']) {
  requireText(appV2, token, `profile loader workflow ${token}`);
}
for (const token of ['PACKAGE_SCHEMA', 'SHA256=', 'safe path', 'loader_repository']) {
  requireText(loaderRepository, token, `verified loader repository ${token}`);
}
requireText(deployment, "(ue4ss_loader, game_root, {'id.txt'})", 'UE4SS loader-first deployment');
requireText(deployment, "(runeschema_loader, game_root, {'id.txt'})", 'RuneSchema loader-first deployment');
if (syncEngine.indexOf('deploy_staged_loaders(profile_roots') > syncEngine.indexOf("(profile_roots['ue4ss']")) {
  throw new Error('Client profile restore must deploy loader entities before mod entities');
}
forbidText(appV2, 'id="runeschema-flavor-select"', 'legacy inline RuneSchema selector');
forbidText(appV2, 'id="ue4ss-version-select"', 'legacy inline UE4SS selector');

requireText(profileSettings, 'DragonwildsSync.WorldProfileSettings.v1', 'settings.json schema');
requireText(profileSettings, 'DragonwildsSync.WorldProfileRegistry.v1', 'profile registry schema');
requireText(profileSettings, '"saves": {', 'save association model');
requireText(profileSettings, '"associated": associated', 'multiple save association groundwork');
requireText(profileSettings, '"active": current', 'active save selection');
requireText(profileSettings, 'profile_store.write_json(settings_path', 'atomic profile settings writer');
requireText(profileSettings, '"password" in folded', 'secret redaction');
requireText(profileSettings, 'folded.endswith("_token")', 'token redaction');
requireText(profileSettings, 'install_phase2_profile_adapters', 'legacy-provider compatibility adapter');
requireText(routing, 'install_phase2_profile_adapters()', 'Phase 2 adapter startup wiring');
requireText(runner, 'backend/test_phase2_profile_settings.py', 'Phase 2 backend regression');

console.log('Phase 2 World Management/profile contract: OK');
