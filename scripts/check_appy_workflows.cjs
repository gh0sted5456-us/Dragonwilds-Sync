'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');
const need = (condition, message) => { if (!condition) throw new Error(`Appy workflow contract: ${message}`); };

const app = read('renderer/app-v2.js');
const styles = read('renderer/styles.css');
const responsive = read('renderer/release-responsiveness.css');
const capture = read('electron/main-v2.cjs');
const helpManifest = JSON.parse(read('help/manifest.json'));

const navRoutes = ['world-management', 'characters-app', 'mods-app', 'rsdw-launcher', 'webhost', 'help', 'settings'];
for (const route of navRoutes) need(app.includes(`navButton('${route}'`), `${route} must remain a first-class navigation entry`);
need(app.includes("event.target?.closest?.('[data-route]')") && app.includes('handleRouteNavigation(el.dataset.route)'), 'all Appy buttons must use the persistent delegated route handler');
need(!app.includes("navButton('rsdragonwilds-app'"), 'Dragonwilds/Hosting must not reappear as a duplicate navigation item');
need(app.includes("navButton('world-management',navIconAsset('assets/dragonwilds_icon.ico'),'Dragonwilds'"), 'Dragonwilds must retain the canonical game icon');
for (const token of [
  "navButton('characters-app',navIconAsset('assets/rsdw-toolkit/character-editor.png')",
  "navButton('mods-app',navIconAsset('assets/rsdw-toolkit/modded-items.svg')",
  "navButton('rsdw-launcher',navIconAsset('assets/navigation/rsdw-l.png')",
  "navButton('webhost',navIconAsset('assets/navigation/sync.svg')",
  "navButton('help',navIconAsset('assets/navigation/help.svg')",
  "navButton('settings',navIconAsset('assets/navigation/settings.svg')",
]) need(app.includes(token), `navigation icon contract missing ${token}`);
for (const relative of [
  'renderer/assets/dragonwilds_icon.ico', 'renderer/assets/rsdw-toolkit/character-editor.png',
  'renderer/assets/rsdw-toolkit/modded-items.svg', 'renderer/assets/navigation/rsdw-l.png',
  'renderer/assets/navigation/sync.svg', 'renderer/assets/navigation/help.svg',
  'renderer/assets/navigation/settings.svg',
]) need(fs.existsSync(path.join(root, relative)) && fs.statSync(path.join(root, relative)).size > 0, `${relative} must be a packaged non-empty navigation icon`);
need(app.includes("'Singleplayer · Co-Op · Dedicated · connect'"), 'Dragonwilds must describe every combined launch role');
need(app.includes("next === 'rsdragonwilds-app'") && app.includes("handleRouteNavigation('world-management')"), 'legacy Hosting shortcuts must redirect into Dragonwilds safely');
need(app.includes('function renderPersistentShell(page)') && app.includes("root.dataset.persistentShell='1'"), 'normal navigation must keep one persistent shell instance');
need(app.includes("syncPersistentTitlebar(root.querySelector(':scope > .titlebar'))") && app.includes("syncPersistentSidebar(root.querySelector(':scope > .sidebar'))"), 'persistent shell state must be synchronized without replacing the navigation DOM');
need(app.includes('else renderPersistentShell(page);') && !app.includes("`${renderTitlebar()}${renderSidebar()}${operationMarkup()}"), 'normal renders must replace only the main workspace, not the titlebar/sidebar');
need(app.includes('bindPersistentOnce(') && app.includes('const persistentShellBindings=new WeakMap()'), 'persistent titlebar/Profile controls must not accumulate duplicate event handlers');

need(app.includes('Associated Character Saves') && app.includes('data-profile-character-editor='), 'Profile must list associated Character saves with an editor handoff');
need(app.includes("state.rsdwTool='character-editor'") && app.includes('await enterRsdwToolkit()'), 'Profile handoff must select the Character Editor through RSDW-L');
need(responsive.includes('.profile-character-save{') && responsive.includes('.profile-character-worlds{'), 'Profile Character saves must have responsive layout and World chips');

for (const token of [
  'character-editor-redesign', "[['appearance','Appearance'],['equipment','Equipment'],['pose','Pose']]",
  "nativeAppearanceSelector(editor,'Head','Face')", "nativeAppearanceSelector(editor,'HairPreset','Hair')",
  "nativeAppearanceSelector(editor,'FacialHairPreset','Beard')", 'characterEquipmentSurface(liveAvatar)',
  'Array.from({length:8}', 'data-character-save', 'data-character-export',
  'data-character-undo', 'data-character-redo', 'data-avatar-upstream-select="avatar-animation-select"',
  'characterEquipmentCompatible(row, slot)', 'character-equipment-context-menu',
  'openStudioEquipmentMenu(socket,event)', 'data-character-equip-item',
  "action:'remove',section:'loadout'", 'Browse All Compatible Items…',
]) need(app.includes(token), `Character Editor redesign contract missing ${token}`);
need(app.includes('nativeCharacterEditor.querySelectorAll(\'[data-character-editor-tab]\')') && app.includes('panel.classList.toggle(\'active\''), 'Character Editor tabs must swap panels in place without recreating the live preview');
const tabSwapStart = app.indexOf('const setCharacterEditorTab=');
const tabSwap = app.slice(tabSwapStart, app.indexOf("nativeCharacterEditor.querySelectorAll('[data-native-step]')", tabSwapStart));
need(tabSwap.includes("panel.classList.toggle('active'") && !tabSwap.includes('render('), 'Character Editor tab swaps must only toggle mounted panels');
const equipmentApply = app.slice(app.indexOf('const applyStudioContextItem='), app.indexOf('const openStudioEquipmentMenu='));
need(equipmentApply.includes('refreshStudioEquipmentSocket(') && !equipmentApply.includes('render();'), 'equipping or clearing a quick-select item must update its mounted socket without repainting the Character Editor');
need(app.includes('Object.values(editor.tabs||{}).flatMap((tab)=>tab.items||[])'), 'Quick Equip must merge every Item Editor tab, including Modded Items');
need(!app.includes('data-studio-native-meta') && !app.includes('data-studio-native-customization') && !app.includes('data-studio-native-value'), 'superseded pre-redesign appearance facade must stay removed');
need(!styles.includes('.character-equipment-studio') && !styles.includes('.character-equipment-groups'), 'superseded pre-redesign equipment layout CSS must stay removed');
need(app.includes("target&&!target.matches('[data-native-meta], [data-native-customization]"), 'preview-only camera, background, and Pose controls must not dirty the save');
need(styles.includes('grid-template-columns:minmax(320px,370px) minmax(480px,1fr) minmax(340px,400px)'), 'Character Editor desktop layout must preserve controls, dominant preview, and equipped columns');
need(styles.includes('.character-action-bar{') && styles.includes('grid-template-columns:repeat(8'), 'Character Editor must render the exact eight-slot action bar');
need(styles.includes('.character-equipment-context-menu{') && styles.includes('.character-equipment-menu-items{'), 'right-click equipment selection must retain a bounded searchable context-menu layout');

for (const token of [
  "runOperation('Starting hosted World'",
  "runOperation('Stopping hosted World'",
  "runOperation('Restarting hosted World'",
  "runOperation('Starting Co-Op Sync'",
  "runOperation('Stopping Co-Op Sync'",
  "local?'Launching Singleplayer':'Synchronizing & launching World'",
]) need(app.includes(token), `${token} must use the shared non-overlapping operation guard`);
need(app.includes("if (state.operation) throw new Error"), 'overlapping lifecycle/Sync actions must be rejected');
need(app.includes("const labels = { idle:'Ready', connecting:'Connecting', authenticating:'Validating World', syncing:'Synchronizing Files', verifying:'Verifying Match', launching:'Launching Dragonwilds'"), 'Quick Launch must expose a staged Sync/startup flow');

for (const token of [
  "'singleplayer.mod.file.open'", "'singleplayer.mod.file.save'",
  "'server.world.config.open'", "'server.world.config.save'",
  'File saved atomically.', 'Invalid JSON',
]) need(app.includes(token) || read('renderer/release-phase5.js').includes(token), `mod editing contract missing ${token}`);

need(helpManifest.schema === 'DragonwildsSync.Help.v1' && helpManifest.version >= 2, 'Help manifest must identify the refreshed walkthrough');
need(helpManifest.pages.some((page) => page.id === 'appy-walkthrough'), 'Help must include the end-to-end Appy walkthrough');
need(capture.includes('assertAppyNavigation') && capture.includes("'42-profile-character-saves.png'"), 'Help capture must exercise all Appys and the Profile character-save handoff');

for (const relative of [
  'help/appy-walkthrough.md', 'help/getting-started.md', 'help/characters-rsdw.md',
  'help/server-webhost.md', 'help/mods-items.md', 'help/worlds-sync.md',
]) {
  const absolute = path.join(root, relative);
  need(fs.existsSync(absolute), `${relative} is missing`);
  for (const match of read(relative).matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)) {
    need(fs.existsSync(path.resolve(path.dirname(absolute), match[1])), `${relative} references missing image ${match[1]}`);
  }
}

console.log('Appy navigation, startup, character, mod editing, Sync, and Help workflow contract: PASS');
