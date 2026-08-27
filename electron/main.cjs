// V3 argument adapter around the retained Electron main process.
// One executable, one backend: new Quick CLI is translated to the proven
// stable-profile-id window launch contract before main-v2.cjs initializes.
const { app, ipcMain, shell } = require('electron');
const path = require('path');
const { buildHeadlessShortcutArgs, buildQuickShortcutArgs, normalizeProfileId, normalizeQuickMode } = require('./quick_shortcut.cjs');
const { resolveGuiShortcutTarget, resolveHeadlessShortcutTarget } = require('./shortcut_targets.cjs');

// The save-backed RSDWModel preview is a WebContents guest. Keep its WebGL
// renderer at full priority even when a popover or another launcher window has
// focus; Chromium's background throttling otherwise makes initial model-layer
// hydration look stalled on Linux and lower-power Windows systems.
app.on('web-contents-created', (_event, contents) => {
  try { contents.setBackgroundThrottling(false); } catch (_) {}
});


function createV3QuickShortcut(data = {}) {
  if (process.platform !== 'win32') throw new Error('Create Quick Shortcut is currently a Windows desktop feature.');
  const id = normalizeProfileId(data.profileId || data.worldId);
  const shortcutMode = normalizeQuickMode(data.mode);
  const auto = data.autoStart === true;
  const runtime = String(data.runtime || 'gui').trim().toLowerCase() === 'headless' ? 'headless' : 'gui';
  if (runtime === 'headless' && shortcutMode !== 'server') throw new Error('Standalone headless shortcuts are currently server-only.');
  const baseName = String(data.name || 'Dragonwilds World').replace(/[<>:"/\\|?*]/g, '').trim() || 'Dragonwilds World';
  const role = shortcutMode === 'server' ? 'Server' : (shortcutMode === 'coop' ? 'Co-Op' : 'Player');
  const safeName = `${baseName} · ${runtime === 'headless' ? 'Headless ' : ''}${role}`;
  const shortcutPath = path.join(app.getPath('desktop'), `${safeName}.lnk`);
  const projectRoot = path.resolve(__dirname, '..');
  const guiTarget = resolveGuiShortcutTarget(process.execPath);
  const target = runtime === 'headless' && app.isPackaged
    ? resolveHeadlessShortcutTarget({ executablePath: guiTarget, version: app.getVersion(), requestedPath: data.executablePath })
    : guiTarget;
  const launchArgs = runtime === 'headless'
    ? buildHeadlessShortcutArgs({ profileId: id, mode: shortcutMode, command: 'run' })
    : buildQuickShortcutArgs({ profileId: id, mode: shortcutMode, autoStart: auto });
  const shortcutArgs = app.isPackaged ? launchArgs : `"${projectRoot}" ${launchArgs}`;
  const ok = shell.writeShortcutLink(shortcutPath, 'create', {
    target,
    args: shortcutArgs,
    description: runtime === 'headless' ? `Run ${baseName} headlessly` : `${auto ? 'Open Quick + Start' : 'Open Quick'} · ${baseName} · ${role}`,
    cwd: app.isPackaged ? path.dirname(target) : projectRoot,
    icon: target,
    iconIndex: 0,
  });
  if (!ok) throw new Error('Windows did not create the Quick desktop shortcut.');
  return { ok: true, path: shortcutPath, target, profileId: id, mode: shortcutMode, runtime, autoStart: auto };
}
ipcMain.handle('dragonwilds:create-v3-quick-shortcut', (_event, data) => createV3QuickShortcut(data));

function valueAfter(args, flag) {
  const exact = args.indexOf(flag);
  if (exact >= 0 && exact + 1 < args.length) return String(args[exact + 1] || '');
  const prefix = `${flag}=`;
  const hit = args.find((arg) => String(arg).startsWith(prefix));
  return hit ? String(hit).slice(prefix.length) : '';
}
function dropFlagWithValue(args, flag) {
  const out = [];
  for (let i = 0; i < args.length; i += 1) {
    const arg = String(args[i]);
    if (arg === flag) { i += 1; continue; }
    if (arg.startsWith(`${flag}=`)) continue;
    out.push(args[i]);
  }
  return out;
}

let args = [...process.argv];
const explicitQuick = args.includes('--quick');
const legacyQuick = args.includes('--quick-launch');
const legacyMinimal = args.includes('--minimal-mode');
const quick = explicitQuick || legacyQuick || legacyMinimal;
let profileId = valueAfter(args, '--profile') || valueAfter(args, '--world-id');
let mode = (valueAfter(args, '--mode') || '').toLowerCase();
if (!['player', 'coop', 'server'].includes(mode)) {
  const legacyKind = (valueAfter(args, '--world-kind') || '').toLowerCase();
  mode = legacyMinimal || legacyKind === 'server' ? 'server' : (legacyKind === 'private' ? 'coop' : 'player');
}
const autoStart = args.includes('--auto-start');

if (quick) {
  process.env.DWS_V3_QUICK = '1';
  process.env.DWS_V3_QUICK_PROFILE = profileId;
  process.env.DWS_V3_QUICK_MODE = mode;
  process.env.DWS_V3_QUICK_AUTOSTART = autoStart ? '1' : '0';

  // Remove V3-only arguments before the retained main parser sees argv.
  // Keep --auto-start in argv. The already-running primary instance receives
  // argv through Electron's second-instance event; environment variables from
  // this short-lived process are not inherited by that primary instance.
  args = args.filter((arg) => !['--quick', '--full'].includes(String(arg)));
  args = dropFlagWithValue(args, '--profile');
  args = dropFlagWithValue(args, '--mode');
  args = args.filter((arg) => !String(arg).startsWith('--profile=') && !String(arg).startsWith('--mode='));

  if (!args.includes('--world-id') && !args.some((arg) => String(arg).startsWith('--world-id=')) && profileId) args.push(`--world-id=${profileId}`);
  if (!args.some((arg) => String(arg).startsWith('--world-kind=')) && !args.includes('--world-kind')) {
    args.push(`--world-kind=${mode === 'server' ? 'server' : (mode === 'coop' ? 'private' : 'world')}`);
  }
  // Server Quick reuses the established larger Minimal control window; Player
  // and Co-Op reuse the compact quick window. The renderer labels all as Quick.
  if (mode === 'server') {
    args = args.filter((arg) => arg !== '--quick-launch');
    if (!args.includes('--minimal-mode')) args.push('--minimal-mode');
  } else {
    args = args.filter((arg) => arg !== '--minimal-mode');
    if (!args.includes('--quick-launch')) args.push('--quick-launch');
  }
  process.argv = args;
}

if (quick) {
  app.on('browser-window-created', (_event, window) => {
    try { window.setTitle(`Dragonwilds Sync Quick · ${mode === 'server' ? 'Server' : (mode === 'coop' ? 'Co-Op' : 'Player')}`); } catch (_) {}
  });
}

require('./main-v2.cjs');
