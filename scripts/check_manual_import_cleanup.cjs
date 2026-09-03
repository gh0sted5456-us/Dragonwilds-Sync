'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');
const app = read('renderer/app-v2.js');
const overlay = read('renderer/release-profile-mod-folders.js');

const forbiddenApp = [
  'openSmartModImport',
  'installSinglePlayerZip',
  'installServerZip',
  'bindModDropZone',
  'id="sp-install-mod"',
  'id="install-server-mod-zip"',
  'id="sp-mod-dropzone"',
  'id="server-mod-dropzone"',
  'Install Manual ZIP',
  'Import Mod Package',
  'confirm-smart-mod-import',
  'Install Manual RSDWL Mod',
];
for (const marker of forbiddenApp) {
  if (app.includes(marker)) throw new Error(`legacy manual importer marker remains in app-v2.js: ${marker}`);
}

const forbiddenOverlay = [
  'replaceImportButton',
  'replaceDropZone',
  '#sp-install-mod',
  '#install-server-mod-zip',
  '#sp-mod-dropzone',
  '#server-mod-dropzone',
  'refreshLegacyHelpCopy',
];
for (const marker of forbiddenOverlay) {
  if (overlay.includes(marker)) throw new Error(`legacy importer compatibility marker remains in profile-folder overlay: ${marker}`);
}

const requiredApp = [
  'id="sp-open-mods-folder"',
  'id="server-open-mods-folder"',
  'data-profile-mod-folder-note="local"',
  'Manual mod archive import retired',
  "api.invoke('profile.package.inspect'",
  "api.invoke('profile.package.import'",
  "api.invoke('singleplayer.mod.detect'",
  "api.invoke('singleplayer.mod.install'",
  "api.invoke('server.maintenance.detect_mod_zip'",
  "api.invoke('server.world.mod.install'",
];
for (const marker of requiredApp) {
  if (!app.includes(marker)) throw new Error(`supported workflow marker was lost from app-v2.js: ${marker}`);
}

const requiredOverlay = [
  "bindProfileFolderButton('#sp-open-mods-folder', 'local')",
  "bindProfileFolderButton('#server-open-mods-folder', 'server')",
  "bridge.invoke('application.storage.paths'",
  "rescan: true",
  'PROTECTED RECOVERY BASELINE',
];
for (const marker of requiredOverlay) {
  if (!overlay.includes(marker)) throw new Error(`profile-folder or recovery-baseline marker is missing: ${marker}`);
}

const counts = (source, marker) => source.split(marker).length - 1;
if (counts(app, 'id="sp-open-mods-folder"') !== 1) throw new Error('Private World Open Mods Folder control must appear exactly once.');
if (counts(app, 'id="server-open-mods-folder"') !== 1) throw new Error('Server Open Mods Folder control must appear exactly once.');
if (counts(app, "api.invoke('singleplayer.mod.install'") < 2) throw new Error('Nexus install/rollback support was unexpectedly removed.');
if (counts(app, "api.invoke('server.world.mod.install'") < 2) throw new Error('Server Nexus install/rollback support was unexpectedly removed.');
if (!app.includes("path.toLowerCase().endsWith('.rsdwl')")) throw new Error('Normal .rsdwl drag/drop import was unexpectedly removed.');

console.log('manual importer cleanup contract passed');
