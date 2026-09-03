'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const phase6 = read('backend/phase6_integration.py');
const secrets = read('backend/secret_store.py');
const direct = read('backend/persistent_direct_connect.py');
const dragonConnectLua = read('resources/NativeRuntimeMods/DragonConnect/Scripts/main.lua');
const routing = read('backend/v2_remote_routing.py');
const renderer = read('renderer/release-phase6.js');
const app = read('renderer/app-v2.js');
const receipt = read('renderer/connect-world-receipt.js');
const upstream = read('renderer/upstream-sources.js');
const registry = JSON.parse(read('docs/upstream-sources.json'));
const html = read('renderer/index.html');
const css = read('renderer/release-phase6.css');

const requireText = (source, token, label = token) => {
  if (!source.includes(token)) throw new Error(`Phase 6 contract missing: ${label}`);
};
const rejectText = (source, token, label = token) => {
  if (source.includes(token)) throw new Error(`Phase 6 contract forbids: ${label}`);
};

requireText(secrets, 'DragonwildsSync.SecretReferences.v1', 'encrypted secret reference schema');
requireText(secrets, 'dws-secret://', 'stable secret reference prefix');
requireText(secrets, 'Fernet', 'encrypted-at-rest local secret vault');
requireText(secrets, '_EXCLUDED_SUFFIXES', 'hash/salt exclusion policy');
requireText(secrets, '"_hash"', 'password/hash fields are not re-encrypted');
requireText(secrets, '"_salt"', 'password/salt fields are not re-encrypted');
requireText(phase6, '_install_secret_references', 'profile/state secure-reference adapter');
requireText(phase6, 'profile.json', 'World profile secret migration');
requireText(phase6, 'settings.json', 'desired-state settings boundary');
requireText(phase6, 'DragonwildsSync.SyncJournal.v1', 'resumable sync journal');
requireText(phase6, 'DragonwildsSync.DirectConnectHandoff.v1', 'verified Direct Connect handoff receipt');
requireText(phase6, 'contains_credentials', 'credential-free handoff receipt');
requireText(phase6, 'server-pushed mods.txt', 'server literal mods.txt rejection');
requireText(phase6, 'client_generate', 'client-generated mods.txt authority');
requireText(phase6, 'RuneSchema', 'client runtime RuneSchema framework derivation');
requireText(phase6, 'SYNC_REUSE_SECONDS', 'short-lived verified Sync reuse');
requireText(phase6, 'reused_verified_sync', 'Quick Launch duplicate-sync avoidance');
requireText(phase6, 'world.launch_mismatch_override', 'explicit incomplete-Sync launch RPC');
requireText(phase6, '_NON_OVERRIDABLE_FAILURE_TERMS', 'authentication and identity override exclusion');
requireText(phase6, 'application.communities.refresh', 'explicit Community refresh');
requireText(phase6, 'application.phase6.status', 'final integration status RPC');
requireText(phase6, 'RSDWArchive/RSDWDevKit', 'Toolkit/DevKit authoritative source');
requireText(phase6, 'RSDWArchive/RSDWTools', 'RSDWTools authoritative data source');
requireText(routing, 'install_phase6_integrations', 'production V2 entrypoint installs Phase 6 adapters');

requireText(direct, 'LOGICAL_NAME = "DragonConnect"', 'logical DragonConnect identity');
requireText(direct, 'MOD_NAME = "DragonConnect"', 'canonical physical DragonConnect identity');
requireText(direct, 'REQUIRED_CLIENT_FILES = ("Scripts/main.lua", "enabled.txt")', 'Lua-only DragonConnect payload');
requireText(direct, 'Scripts" / "config.lua', 'profile-scoped Lua config handoff');
requireText(direct, 'def status(', 'DragonConnect update/repair status');
requireText(dragonConnectLua, 'FindAllOf', 'Lua widget discovery');
requireText(dragonConnectLua, 'FText(value)', 'Lua Direct Connect field hydration');
rejectText(dragonConnectLua, '.dll', 'native DLL dependency');

if (registry.sources.rsdwtools.runtime_component !== false) throw new Error('RSDWTools must remain data-only in the source registry.');
if (registry.sources['rsdw-toolkit'].repository !== 'RSDWArchive/RSDWDevKit') throw new Error('RSDW Toolkit must use RSDWArchive/RSDWDevKit.');
if (JSON.stringify(registry.sources.dragonconnect.runtime_roles) !== JSON.stringify(['client'])) throw new Error('DragonConnect must be client-only.');
if (registry.sources.dragonconnect.type !== 'bundled-lua-core') throw new Error('DragonConnect must be represented as a bundled Lua Core.');
if (registry.sources.dragonconnect.bundled_fallback !== 'resources/NativeRuntimeMods/DragonConnect') throw new Error('DragonConnect Lua fallback is incorrect.');
requireText(upstream, "'rsdw-toolkit'", 'offline/source UI knows Toolkit separately');
requireText(upstream, 'Repair DragonConnect', 'central dependency panel DragonConnect repair');
requireText(upstream, 'RSDWTools ≠ RSDW Dev Kit', 'explicit UI taxonomy distinction');
rejectText(upstream, 'Repair DragonLink-Connect', 'retired native Connect terminology');

requireText(html, 'release-phase6.css', 'Phase 6 stylesheet load');
requireText(html, 'release-phase6.js', 'Phase 6 renderer load');
requireText(html, 'connect-world-receipt.js', 'connection receipt correction layer');
requireText(renderer, 'data-phase6-settings-community', 'Settings → Community navigation');
requireText(renderer, 'application.communities.list', 'cached Community load');
requireText(renderer, 'application.communities.settings', 'Community source persistence');
requireText(renderer, 'application.communities.refresh', 'explicit Community refresh action');
requireText(renderer, 'application.phase6.status', 'cached final integration status');
requireText(renderer, 'Direct Connect', 'Community routes into existing Direct Connect flow');
requireText(renderer, '#add-world-card', 'existing Direct Connect placard reuse');
requireText(renderer, 'RSDWTools', 'Community integration taxonomy message');
requireText(renderer, 'RSDW Toolkit / DevKit', 'Community integration Toolkit distinction');
requireText(css, '.phase6-community-page', 'Community settings styling');
requireText(css, '.phase6-integration-summary', 'final integration status styling');
requireText(app, 'ENTER_WITH_INCOMPLETE_SYNC', 'explicit incomplete-Sync acknowledgement');
requireText(app, '>Backout</button><button class="btn danger" id="enter-incomplete-sync">Enter</button>', 'Enter / Backout mismatch confirmation');
requireText(app, 'Stability may be compromised', 'incomplete-Sync stability warning');
requireText(receipt, 'World Type', 'connection receipt World Type');
requireText(receipt, 'Game Mode', 'connection receipt Game Mode');
requireText(receipt, 'Password required · not saved', 'protected-world password state');
rejectText(receipt, 'Lua ready', 'implementation status jargon');

// The final handoff must never introduce another runtime/process authority.
rejectText(phase6, 'subprocess.Popen(', 'new direct subprocess lifecycle');
rejectText(phase6, 'subprocess.run(', 'new direct subprocess lifecycle');
rejectText(renderer, 'setInterval(', 'new Community polling loop');

console.log('Phase 6 final sync/profile/DragonConnect/Community integration contract: OK');
