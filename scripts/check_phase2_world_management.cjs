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
const profileSettings = read('backend/profile_settings.py');
const routing = read('backend/v2_remote_routing.py');
const runner = read('scripts/run_backend_tests.cjs');

requireText(index, 'release-phase2.css', 'Phase 2 stylesheet');
requireText(index, 'release-phase2.js', 'Phase 2 renderer');
requireText(phase2, '+ Direct Connect', 'World Management Direct Connect action');
requireText(phase2, 'See in Explorer', 'managed profile Explorer action');
requireText(phase2, 'View Mods', 'World profile Mods action');
requireText(phase2, 'WORLD SAVE LOADED', 'loaded save indicator');
requireText(phase2, 'NO WORLD SAVE LOADED', 'empty save indicator');
requireText(phase2, "invoke('application.storage.paths'", 'authoritative APPDATA discovery');
requireText(phase2, "['profiles', 'world', 'dedicated', id]", 'dedicated profile root');
requireText(phase2, "['profiles', 'world', 'local', id]", 'local profile root');
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
]) requireText(appV2, token, `shared runtime version manager ${token}`);
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
