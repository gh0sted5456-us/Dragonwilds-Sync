const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'renderer', 'app-v2.js'), 'utf8');
const avatarPreload = fs.readFileSync(path.join(root, 'electron', 'rsdw_webview_preload.cjs'), 'utf8');
const placardWindows = fs.readFileSync(path.join(root, 'renderer', 'release-phase5-placard-window.js'), 'utf8');
const responsiveCss = fs.readFileSync(path.join(root, 'renderer', 'release-responsiveness.css'), 'utf8');
const baseCss = fs.readFileSync(path.join(root, 'renderer', 'styles.css'), 'utf8');
const releaseNavigation = fs.readFileSync(path.join(root, 'renderer', 'release-navigation.js'), 'utf8');
const releasePolish = fs.readFileSync(path.join(root, 'renderer', 'release-polish.js'), 'utf8');
const performanceCss = fs.readFileSync(path.join(root, 'renderer', 'release-performance.css'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(source.includes('data-webhost-tab="live">Dragonwilds Sync'),
  'The combined Sync workspace must expose its Dragonwilds Sync preview tab.');
assert(source.includes('data-webhost-tab="settings">Website &amp; Networking'),
  'The combined Sync workspace must expose its Networking tab.');
assert(source.includes("navButton('webhost',webhostLinked?'◆':'◇','Sync'"),
  'Website and Remote Server capabilities must roll up under one Sync navigation item.');
assert(source.includes("navButton('characters-app'") && source.includes("navButton('mods-app'") && source.includes("navButton('world-management'"),
  'Characters, Mods, and Dragonwilds must be first-class Appy navigation entries.');
assert(source.includes("navButton('rsdw-launcher',navIconAsset('assets/navigation/rsdw-l.png')") &&
  source.includes("navButton('world-management',navIconAsset('assets/dragonwilds_icon.ico'),'Dragonwilds'") &&
  !source.includes("navButton('rsdragonwilds-app'") &&
  baseCss.includes('.nav-icon-image{display:block;width:22px;height:22px'),
  'Dragonwilds must retain the game artwork and own Hosting without a duplicate navigation item.');
assert(!source.includes("navButton('remote-server'"),
  'Remote Server must not create a second Host navigation item.');
assert(source.includes('id="toggle-webhost-remote-admin"'),
  'Sync Networking must independently expose Remote Server Access.');
assert(!source.includes("if(routedWebhost) state.webhostTab='live'"),
  'The routed WebHost workspace must not reset the selected tab during render.');
assert(avatarPreload.includes('main>*:not(.avatar-layout):not(#avatar-stage)') &&
  avatarPreload.includes('.avatar-layout>*:not(.avatar-viewer-panel):not(#avatar-stage)') &&
  avatarPreload.includes('.avatar-viewer-panel>*:not(#avatar-stage)'),
  'The embedded RSDWModel viewport must preserve every ancestor of #avatar-stage.');
assert(!avatarPreload.includes('main>*:not(#avatar-stage),#rsdw-header-mount'),
  'The embedded RSDWModel viewport must not hide the avatar-stage parent layout.');
assert(placardWindows.includes("event.target.closest?.('[data-phase5-placard-close],[data-phase5-placard-min],[data-phase5-placard-max]')") &&
  placardWindows.includes("if (event.key !== 'Escape') return"),
  'Placard windows must expose capture-safe titlebar controls and Escape-to-close.');
assert(!/dblclick[\s\S]{0,500}openPlacard\(card\.dataset\.worldId/.test(placardWindows),
  'Double-clicking a placard must not open an unexpected application window.');
assert(responsiveCss.includes('.placard-identity{display:grid;grid-template-columns:68px minmax(0,1fr)') &&
  responsiveCss.includes('.placard-identity .world-icon{position:static!important') &&
  responsiveCss.includes('.app-world-placard .card-title{width:100%;min-width:0;overflow:hidden}') &&
  source.includes('<div class="placard-identity">'),
  'Placard identity rows must reserve independent icon and title columns.');
assert(source.includes('class="placard-runtime-strip"') &&
  source.includes('class="placard-sync-status"') &&
  responsiveCss.includes('.app-world-placard .placard-runtime-strip{position:relative') &&
  !/world-card-front[\s\S]{0,1800}<span class="status-pill[^>]*>(?:● ONLINE|#\$\{instance\} RUNNING)/.test(source),
  'Synchronization status and runtime load must live outside the artwork-driven placard faces.');
assert(source.includes('selectedInventoryWarmRequests') &&
  !source.includes('...privateWorlds().map((world)=>({method:\'singleplayer.inventory\''),
  'Startup must hydrate only selected profile inventories, not every saved world.');
assert(source.includes("requestIdleCallback(run,{timeout})") &&
  source.includes("root.addEventListener('pointerover'") &&
  source.includes('scheduleAppyWarm(lastAppy()'),
  'Appy workspaces must support hover prediction and idle warming of the last workspace.');
assert(source.includes('startBackgroundRefreshScheduler();') &&
  source.includes('function activeBackgroundRefresh()') &&
  !source.includes('worldRefreshTimer') &&
  !source.includes('serverMetricsTimer') &&
  !source.includes('directoryAdminSyncTimer'),
  'Visible background data must use one coordinated, route-aware scheduler.');
assert(source.includes('function hostingFocusActive()') &&
  source.includes('document.body.dataset.hostingFocus') &&
  source.includes("['characters','mods','rsdw-l'].includes(value)") &&
  source.includes('computer-profile-mode') &&
  source.includes('save-computer-profile'),
  'Computer Profiles must expose settings and defer nonessential Appy work only while verified hosting is active.');
assert(source.includes('Pause 3D previews') && source.includes('hosting-focus-placeholder'),
  'Hosting Focus must avoid instantiating the live 3D webview when visual suspension is enabled.');
assert(!source.includes('characters.native.tools.read') &&
  source.includes("if(state.rsdwTool!=='character-editor')setTimeout(()=>hydrateNativeRsdwTool(state.rsdwTool),0)"),
  'Character Studio must parse only the selected subsystem instead of every editor at once.');
assert(releaseNavigation.includes("if(button.textContent!=='▣ Open Placard')button.textContent='▣ Open Placard'") &&
  releasePolish.includes("new CustomEvent('dws:open-profile-mods'") &&
  source.includes("document.addEventListener('dws:open-profile-mods'") &&
  performanceCss.includes('.mod-clean-row {\n  content-visibility: visible;'),
  'World Manage and profile Mods navigation must remain idempotent and free of observer/layout loops.');

function sha256(relativePath) {
  return crypto.createHash('sha256')
    .update(fs.readFileSync(path.join(root, relativePath)))
    .digest('hex');
}

function assertPng(relativePath) {
  const file = fs.readFileSync(path.join(root, relativePath));
  assert(file.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])),
    `${relativePath} must be a valid PNG asset.`);
}

function assertIco(relativePath) {
  const file = fs.readFileSync(path.join(root, relativePath));
  assert(file.length > 6 && file[0] === 0 && file[1] === 0 && file[2] === 1 && file[3] === 0,
    `${relativePath} must be a valid ICO asset.`);
}

assertPng('renderer/assets/navigation/rsdw-l.png');
assert(sha256('renderer/assets/navigation/rsdw-l.png') === '6fca88b1bdfe9180bb3e86920889d18249f05756112d7246cabe2d0220bc91e2',
  'The RSDW-L navbar icon must match the supplied approved artwork.');
assertIco('renderer/assets/dragonwilds_icon.ico');
assert(sha256('renderer/assets/dragonwilds_icon.ico') === '3ccd660ed77e252940fce0a53e0938d897b4f0ff0bcb71fee4bba41469fe5e8e',
  'The RSDragonwilds navbar icon must remain the canonical game executable icon.');

const platformAssets = {
  'renderer/assets/platforms/runeschema.png': '379a7b239490eb8fcc01ff6bafdaf291f09393ab30106658af02bf96c716b105',
  'renderer/assets/platforms/ue4ss.png': '5d85d20b008b32516ee3115318b4aeaba54631f6d254477e60af55101823d98a',
};

for (const [relativePath, expectedHash] of Object.entries(platformAssets)) {
  assertPng(relativePath);
  assert(sha256(relativePath) === expectedHash,
    `${relativePath} does not match its approved canonical artwork.`);
}

for (const placard of [1, 2, 3, 4]) {
  assertPng(`renderer/assets/placards/${placard}.png`);
}

assert(source.includes("--world-placard:url('assets/placards/${placardId}.png')"),
  'Desktop world cards must use the selected placard as their full background.');
assert(source.includes('world-card-media') && source.includes('world-card-banner-blend'),
  'Desktop world cards must keep the banner and its blend layer at the top.');
assert(source.includes('world-list-row has-placard') && source.includes('hosted-list-row has-placard'),
  'Horizontal World cards must inherit the selected placard background.');

const websitePlacards = fs.readFileSync(path.join(root, 'website', 'placards.js'), 'utf8');
assert(websitePlacards.includes('raw?.banner_b64') && websitePlacards.includes('raw?.icon_b64'),
  'Website placards must accept the application banner and icon payloads.');
assert(websitePlacards.includes("makeImage('world-placard-backdrop'"),
  'Website placards must render the selected placard as the full background.');
assert((websitePlacards.match(/back\.appendChild\(makeMedia\(world\)\)/g) || []).length === 1,
  'The reverse face must inherit the same server banner as the front face.');
assert(websitePlacards.includes("card.classList.toggle('flipped')") &&
  websitePlacards.includes("event.key === 'Enter' || event.key === ' '"),
  'Website placards must provide click and keyboard-operated 3D flipping.');

console.log('renderer route and visual asset contract checks passed');
