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
const characterLayout = fs.readFileSync(path.join(root, 'renderer', 'release-character-layout.js'), 'utf8');
const characterLayoutCss = fs.readFileSync(path.join(root, 'renderer', 'release-character-layout.css'), 'utf8');
const characterLayoutHotfixCss = fs.readFileSync(path.join(root, 'renderer', 'release-character-layout-hotfix.css'), 'utf8');
const characterTabsCss = fs.readFileSync(path.join(root, 'renderer', 'release-character-tabs.css'), 'utf8');
const characterMenuCss = fs.readFileSync(path.join(root, 'renderer', 'release-character-menu.css'), 'utf8');
const localProfileSync = fs.readFileSync(path.join(root, 'renderer', 'release-local-profile-sync.js'), 'utf8');
const popupSafety = fs.readFileSync(path.join(root, 'renderer', 'release-popup-safety.js'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(characterLayout.includes("/^background$/i") && characterLayout.includes('backgroundPanel.appendChild(background)') &&
  characterTabsCss.includes('grid-template-columns:repeat(4,minmax(100px,1fr))!important'),
  'Character Background must be the fourth tab after Pose without recreating its live control.');
assert(characterLayout.includes('character-hotbar-dock') && characterLayout.includes('dock.appendChild(hotbar)') &&
  characterLayoutCss.includes('justify-content:center') && characterLayoutCss.includes('width:max-content'),
  'The character hotbar must occupy its own centered row directly beneath the preview.');
assert(characterLayoutHotfixCss.includes('grid-column:4!important') && characterLayoutHotfixCss.includes('grid-template-columns:repeat(8,64px)!important') &&
  characterLayoutHotfixCss.includes('width:64px!important') && characterLayoutHotfixCss.includes('height:64px!important'),
  'Background must remain beside Pose and the centered hotbar must retain eight compact square slots.');
assert(characterLayout.includes('character-item-menu-filters') && characterLayout.includes('browse all compatible items/i') && characterMenuCss.includes('.character-hotbar-context-menu'),
  'Equipment and hotbar item selection must use the filtered right-click flow instead of a left-click repository shortcut.');
assert(localProfileSync.includes('profile.local_sync.configure') && localProfileSync.includes('profile.local_sync.run') &&
  localProfileSync.includes('pickDirectory') && localProfileSync.includes('45000'),
  'Optional OneDrive/Google Drive profile sync must use a selected local folder and bounded automatic refresh.');
assert(popupSafety.includes("event.key!=='Escape'") && popupSafety.includes('data-popup-safety-close') &&
  popupSafety.includes('closeModPopup') && popupSafety.includes('event.target===popup'),
  'Every modal popup must support a close control, Escape, backdrop dismissal, and placard-specific cleanup.');

assert(source.includes('data-webhost-tab="live">Dragonwilds Sync'),
  'The combined Sync workspace must expose its Dragonwilds Sync preview tab.');
assert(source.includes('data-webhost-tab="settings">Website &amp; Networking'),
  'The combined Sync workspace must expose its Networking tab.');
assert(source.includes("navButton('webhost',navIconAsset('assets/navigation/sync.svg'),'Sync'"),
  'Website and Remote Server capabilities must roll up under one Sync navigation item.');
assert(source.includes("navButton('characters-app'") && source.includes("navButton('mods-app'") && source.includes("navButton('world-management'"),
  'Characters, Mods, and Dragonwilds must be first-class Appy navigation entries.');
assert(source.includes("navButton('rsdw-launcher',navIconAsset('assets/navigation/rsdw-l.png')") &&
  source.includes("navButton('world-management',navIconAsset('assets/navigation/dragonwilds.png'),'Dragonwilds'") &&
  source.includes("navButton('mods-app',navIconAsset('assets/navigation/mods.png'),'Mods'") &&
  !source.includes("navButton('rsdragonwilds-app'") &&
  baseCss.includes('.nav-icon-image{display:block;width:22px;height:22px'),
  'Dragonwilds and Mods must retain their dedicated artwork, with Hosting owned by the single Dragonwilds entry.');
assert(baseCss.includes('.studio-appearance-swatches{grid-column:1/-1;min-width:0') &&
  baseCss.includes('.studio-appearance-swatches>div{display:flex;flex-wrap:wrap;gap:6px') &&
  baseCss.includes('.studio-appearance-swatches button{flex:0 0 26px;width:26px'),
  'Character Editor color swatches must span the appearance panel with readable, wrapping choices.');
assert(source.includes('native-pastel-picker') && source.includes('native-pastel-wheel') && baseCss.includes('.native-pastel-wheel'),
  'Character color controls must expose the styled radial painter palette.');
assert(source.includes('id="rsdw-see-changes"') && source.includes('queueRsdwAvatarPreview'),
  '3D appearance changes must remain queued until See changes is selected.');
assert(source.includes('rsdwPreviewRefreshAuthorized') && source.includes('applyPendingWeaponChanges') && source.includes('will appear after See changes'),
  'Equipment, weapon, and toolkit preview changes must not alter the mounted 3D view before See changes.');
assert(source.includes('avatarCssInserted') && source.includes('avatarPreparePromise') && source.includes('avatarPollDelay'),
  '3D preview readiness must deduplicate CSS injection and use adaptive polling.');
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
  /\.mod-clean-row \{\r?\n  content-visibility: visible;/.test(performanceCss),
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
assert(sha256('renderer/assets/navigation/rsdw-l.png') === '2275ed1b2d08f8025a35812ec5293dfb6485acd3184a91b1519c05309d1c4695',
  'The RSDW-L navbar icon must match the supplied approved artwork.');
assertIco('renderer/assets/dragonwilds_icon.ico');
assert(sha256('renderer/assets/dragonwilds_icon.ico') === '3ccd660ed77e252940fce0a53e0938d897b4f0ff0bcb71fee4bba41469fe5e8e',
  'The Dragonwilds navbar icon must remain the canonical game executable icon.');

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
assert(baseCss.includes('.world-list-row.has-placard{color:#f4f1e9!important}') &&
  baseCss.includes('.world-list-row.has-placard .world-row-actions .btn.ghost{display:inline-flex}'),
  'Horizontal placards must keep readable controls in light, dark, and mobile layouts.');

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
