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
const recommendedPlacardsCss = fs.readFileSync(path.join(root, 'renderer', 'release-recommended-placards.css'), 'utf8');
const electronMain = fs.readFileSync(path.join(root, 'electron', 'main-v2.cjs'), 'utf8');
const publicServers = fs.readFileSync(path.join(root, 'renderer', 'public-server-list.js'), 'utf8');
const liveHelp = fs.readFileSync(path.join(root, 'renderer', 'release-vnext.js'), 'utf8');
const liveHelpMedia = fs.readFileSync(path.join(root, 'renderer', 'release-vnext-help-media.js'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const websiteBase = 'https://gh0sted5456-us.github.io/Dragonwilds-Sync-Web/';
const websiteRepository = 'https://github.com/gh0sted5456-us/Dragonwilds-Sync-Web';
const websiteRaw = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync-Web/main/help/';
const websiteMediaRaw = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync-Web/main/renderer/assets/help/';
const applicationRepository = 'https://github.com/gh0sted5456-us/Dragonwilds-Sync';
assert(source.includes(websiteBase) && source.includes(`${websiteBase}helpy.html`) &&
  electronMain.includes('/Dragonwilds-Sync-Web/helpy.html') && publicServers.includes(websiteBase),
  'Public website, Helpy, and directory-page links must use the standalone website deployment.');
assert(liveHelp.includes(`${websiteRaw}manifest.json`) && liveHelpMedia.includes(websiteMediaRaw) &&
  websiteRepository.endsWith('/Dragonwilds-Sync-Web'),
  'Live Help content must come from the standalone website repository.');
assert(source.includes(`const repositoryUrl = '${applicationRepository}'`) &&
  source.includes(`appUpdateApply({ repositoryUrl: '${applicationRepository}'`),
  'Application update checks and installers must remain on the application repository.');
assert(![source,electronMain,publicServers,liveHelp,liveHelpMedia,releasePolish].some((text)=>
  text.includes('gh0sted5456-us.github.io/Dragonwilds-Sync/') ||
  text.includes('Dragonwilds-Sync/main/help/')),
  'Runtime application sources must not retain the retired website or Help paths.');

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
assert(source.includes('recommended-mod-card recommended-mod-placard has-placard ${providerKey}') &&
  source.includes('recommended-mod-watermark') && source.includes('>Open Nexus</button>') &&
  !source.includes('class="recommended-mod-media"') &&
  recommendedPlacardsCss.includes('var(--world-placard) center/cover no-repeat') &&
  recommendedPlacardsCss.includes('opacity:.11'),
  'Recommended mods must use local placard artwork, a faded provider watermark, and an Open Nexus action.');

assert(source.includes("if (next === 'webhost' && state.route !== 'webhost') state.webhostTab = 'settings'") &&
  source.includes("syncTab('settings','Website &amp; Directory')") &&
  source.includes("syncTab('manifest','Manifest &amp; Heartbeats')") &&
  source.includes("syncTab('remote','Server Management')") &&
  source.includes("syncTab('live','WebGUI Preview')"),
  'The V3 Sync entry must retain configuration, heartbeat, Server Management, and preview tabs.');
assert(source.includes('Broadcast World') && source.includes('No World currently broadcast') &&
  source.includes("state.data?.server?.runtime?.active_profile_id") &&
  !source.includes('data-webhost-tab="home">Server Directory') && !source.includes('SYNC_HOME_URL'),
  'The V3 WebGUI must select the active hosted broadcast rather than a website or cached client World.');
assert(source.includes("navButton('webhost',navIconAsset('assets/navigation/sync.svg'),'Sync'"),
  'Website and Remote Server capabilities must roll up under one Sync navigation item.');
assert(source.includes("navButton('characters-app'") && source.includes("navButton('mods-app'") &&
  source.includes("navButton('world-management'") && !source.includes("navButton('worlds'"),
  'Characters and Mods must remain Appys while World browsing is owned by Dragonwilds.');
assert(source.includes('TCP 27051 + instance offset') && source.includes('UDP 8422'),
  'Sync must identify TCP transfer separately from host-wide Direct Connect discovery UDP 8422.');
assert(!source.includes('passwordFailure=!local') && !source.includes('The host rejected the saved World Password'),
  'Sync Play must not add a launcher password retry gateway before Dragonwilds validates the World Password.');
assert(source.includes("navButton('rsdw-launcher',navIconAsset('assets/navigation/rsdw-l.webp')") &&
  source.includes("navButton('world-management',navIconAsset('assets/navigation/dragonwilds.webp'),'Dragonwilds'") &&
  source.includes("navButton('mods-app',navIconAsset('assets/navigation/mods.webp'),'Mods'") &&
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
assert(avatarPreload.includes('__DWS_PREVIEW_PIXEL_RATIO__') && avatarPreload.includes('Math.min(nativeRatio,1.25)'),
  'The embedded Character Preview must cap excessive 3D pixel density before WebGL initializes.');
assert(!source.includes("navButton('remote-server'"),
  'Remote Server must not create a second Host navigation item.');
assert(source.includes('id="toggle-webhost-remote-admin"'),
  'Sync Networking must independently expose Remote Server Access.');
assert(source.includes("const profileDistribution=u.classification==='server_only'?'PROFILE RETAINED':'PROFILE ACTIVE'") &&
  source.includes('${modCategoryIcon(section,true)}<strong title=') && source.includes('· SHA-256 ${escapeHtml(fingerprint)}'),
  'Private and Singleplayer mod lists must retain server-grade family icons, lifecycle, distribution, and fingerprints.');
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
assert(source.includes("api.invoke('world.sync.job.start'") && source.includes("api.invoke('world.sync.job.status'") &&
  source.includes("['connecting','comparing','downloading','unpacking','applying','verifying','profile','ready']") &&
  baseCss.includes('.operation-progress-track') && baseCss.includes('.operation-phases'),
  'World connection must show pollable download, unpack, profile apply, verification, and ready progress.');
assert(source.includes('CLIENT SYNC · ${clientRequiredCount}') &&
  source.includes("placardBackSection('Client-Required Mods'") &&
  source.includes("placardBackSection('Server-Retained Mods'"),
  'World placards must distinguish files pushed to clients from server-retained mods.');
assert(source.includes('Reset & Resync World') && source.includes("runWorldSyncJob(world,'sync',true)") && source.includes('force_complete:!!forceComplete') &&
  source.includes('Reset & Reload Profile') && source.includes("singleplayer.profile.reset_reload"),
  'Every saved Connected World and Private World placard must expose the correct protected reset workflow.');
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
assert(source.includes('id="mod-repository-search"') &&
  source.includes("row.dataset.modSearch||''") &&
  source.includes('modRepositorySearch.addEventListener(\'input\',applyModRepositorySearch)'),
  'Mod Management must provide an in-memory name/type/source/profile search without rescanning on each keystroke.');
assert(source.includes('data-repository-build-id') && source.includes("'mod.repository.identity'") &&
  source.includes('Write &amp; verify ID.txt'),
  'Mod Management must preview and safely consolidate legacy metadata into ID.txt.');
assert(source.includes('include_world_passwords:false') && source.includes('Profile-wrapped and safe to share'),
  'Connected-world profile exports must always exclude passwords and explain their profile wrapper.');

function sha256(relativePath) {
  return crypto.createHash('sha256')
    .update(fs.readFileSync(path.join(root, relativePath)))
    .digest('hex');
}

function assertWebp(relativePath) {
  const file = fs.readFileSync(path.join(root, relativePath));
  assert(file.length >= 12 && file.subarray(0, 4).toString('ascii') === 'RIFF' &&
    file.subarray(8, 12).toString('ascii') === 'WEBP',
  `${relativePath} must be a valid WebP asset.`);
}

function assertIco(relativePath) {
  const file = fs.readFileSync(path.join(root, relativePath));
  assert(file.length > 6 && file[0] === 0 && file[1] === 0 && file[2] === 1 && file[3] === 0,
    `${relativePath} must be a valid ICO asset.`);
}

assertWebp('renderer/assets/navigation/rsdw-l.webp');
assert(sha256('renderer/assets/navigation/rsdw-l.webp') === '6b1ef09a779d61cd7b86939264d217be7c350241debb5d6f769653fc3b9a6cb2',
  'The RSDW-L navbar icon must match the supplied approved artwork.');
assertIco('renderer/assets/dragonwilds_icon.ico');
assert(sha256('renderer/assets/dragonwilds_icon.ico') === 'c629fbe41934bb36069bad355e5714374185f6665b94cf2e86165f3dd5eb79b5',
  'The application icon must remain the approved RSDW Sync brand artwork.');

const platformAssets = {
  'renderer/assets/platforms/runeschema.webp': '21688f323fd6b032f78add727917d92846c1061c20962e54b0a70ac5fb88c2d2',
  'renderer/assets/platforms/ue4ss.webp': 'b8cf83fb09cfe58d08dd8dc424ff146f73f367a7fb301f3684512f0f965155a3',
};

for (const [relativePath, expectedHash] of Object.entries(platformAssets)) {
  assertWebp(relativePath);
  assert(sha256(relativePath) === expectedHash,
    `${relativePath} does not match its approved canonical artwork.`);
}

for (const placard of [1, 2, 3, 4]) {
  assertWebp(`renderer/assets/placards/${placard}.webp`);
}

assert(source.includes("--world-placard:url('assets/placards/${placardId}.webp')"),
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
