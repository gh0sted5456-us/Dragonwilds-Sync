'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const phase6 = read('backend/phase6_integration.py');
const secrets = read('backend/secret_store.py');
const direct = read('backend/persistent_direct_connect.py');
const routing = read('backend/v2_remote_routing.py');
const renderer = read('renderer/release-phase6.js');
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
requireText(secrets, 'password_hash', 'hash/salt exclusion policy');
requireText(phase6, '_install_secret_references', 'profile/state secure-reference adapter');
requireText(phase6, 'profile.json', 'World profile secret migration');
requireText(phase6, 'settings.json', 'desired-state settings boundary');
requireText(phase6, 'DragonwildsSync.SyncJournal.v1', 'resumable sync journal');
requireText(phase6, 'DragonwildsSync.DirectConnectHandoff.v1', 'verified Direct Connect handoff receipt');
requireText(phase6, 'contains_credentials', 'credential-free handoff receipt');
requireText(phase6, 'server-pushed mods.txt', 'server literal mods.txt rejection');
requireText(phase6, 'client_generate', 'client-generated mods.txt authority');
requireText(phase6, 'PersistentDirectConnectIP', 'DragonConnect legacy physical identity');
requireText(phase6, 'RuneSchema', 'client runtime RuneSchema framework derivation');
requireText(phase6, 'DragonCore is host/server behavior', 'client role excludes DragonCore behavior');
requireText(phase6, 'SYNC_REUSE_SECONDS', 'short-lived verified Sync reuse');
requireText(phase6, 'reused_verified_sync', 'Quick Launch duplicate-sync avoidance');
requireText(phase6, 'application.communities.refresh', 'explicit Community refresh');
requireText(phase6, 'application.phase6.status', 'final integration status RPC');
requireText(phase6, 'RSDWArchive/RSDWDevKit', 'Toolkit/DevKit authoritative source');
requireText(phase6, 'RSDWArchive/RSDWTools', 'RSDWTools authoritative data source');
requireText(routing, 'install_phase6_integrations', 'production V2 entrypoint installs Phase 6 adapters');

requireText(direct, 'LOGICAL_NAME = "DragonConnect"', 'logical DragonConnect identity');
requireText(direct, 'MOD_NAME = "PersistentDirectConnectIP"', 'retained physical DragonConnect identity');
requireText(direct, 'MARKER_NAME', 'managed DragonConnect bundle marker');
requireText(direct, 'def status(', 'DragonConnect update/repair status');
requireText(direct, 'durable credentials stay in the encrypted launcher secret vault', 'runtime-only DragonConnect config note');

if (registry.sources.rsdwtools.runtime_component !== false) throw new Error('RSDWTools must remain data-only in the source registry.');
if (registry.sources['rsdw-toolkit'].repository !== 'RSDWArchive/RSDWDevKit') throw new Error('RSDW Toolkit must use RSDWArchive/RSDWDevKit.');
if (!registry.sources.dragonconnect.runtime_roles.includes('client') || registry.sources.dragonconnect.runtime_roles.includes('server')) throw new Error('DragonConnect source registry role must be CLIENT-only.');
if (!registry.sources.dragonconnect.legacy_physical_names.includes('PersistentDirectConnectIP')) throw new Error('DragonConnect legacy physical identity was lost.');
requireText(upstream, "'rsdw-toolkit'", 'offline/source UI knows Toolkit separately');
requireText(upstream, 'Repair DragonConnect', 'central dependency panel DragonConnect repair');
requireText(upstream, 'RSDWTools ≠ RSDW Toolkit', 'explicit UI taxonomy distinction');

requireText(html, 'release-phase6.css', 'Phase 6 stylesheet load');
requireText(html, 'release-phase6.js', 'Phase 6 renderer load');
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

// The final handoff must never introduce another runtime/process authority.
rejectText(phase6, 'subprocess.Popen(', 'new direct subprocess lifecycle');
rejectText(phase6, 'subprocess.run(', 'new direct subprocess lifecycle');
rejectText(renderer, 'setInterval(', 'new Community polling loop');

console.log('Phase 6 final sync/profile/DragonConnect/Community integration contract: OK');
