// V3 argument adapter around the retained Electron main process.
// One executable, one backend: new Quick CLI is translated to the proven
// stable-profile-id window launch contract before main-v2.cjs initializes.
const { app, BrowserWindow, ipcMain, shell, nativeImage } = require('electron');
const fs = require('fs');
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
  const guiTarget = resolveGuiShortcutTarget(process.env.PORTABLE_EXECUTABLE_FILE || process.execPath);
  const target = runtime === 'headless' && app.isPackaged
    ? resolveHeadlessShortcutTarget({ executablePath: guiTarget, version: app.getVersion(), requestedPath: data.executablePath })
    : guiTarget;
  const launchArgs = runtime === 'headless'
    ? buildHeadlessShortcutArgs({ profileId: id, mode: shortcutMode, command: 'run' })
    : buildQuickShortcutArgs({ profileId: id, mode: shortcutMode, autoStart: auto });
  const shortcutArgs = app.isPackaged ? launchArgs : `"${projectRoot}" ${launchArgs}`;
  let icon = target;
  try {
    const raw = String(data.iconData || '');
    if (raw) {
      const image = nativeImage.createFromDataURL(raw.startsWith('data:') ? raw : `data:image/png;base64,${raw}`);
      if (!image.isEmpty()) {
        const png=image.resize({width:256,height:256}).toPNG();const header=Buffer.alloc(22);
        header.writeUInt16LE(0,0);header.writeUInt16LE(1,2);header.writeUInt16LE(1,4);header.writeUInt16LE(1,10);header.writeUInt16LE(32,12);header.writeUInt32LE(png.length,14);header.writeUInt32LE(22,18);
        const directory=path.join(app.getPath('userData'),'QuickLaunchIcons');fs.mkdirSync(directory,{recursive:true});
        icon=path.join(directory,`${id.replace(/[^A-Za-z0-9_-]/g,'_')}.ico`);fs.writeFileSync(icon,Buffer.concat([header,png]));
      }
    }
  } catch (_) { icon=target; }
  const ok = shell.writeShortcutLink(shortcutPath, 'create', {
    target,
    args: shortcutArgs,
    description: runtime === 'headless' ? `Run ${baseName} headlessly` : `${auto ? 'Open Quick + Start' : 'Open Quick'} · ${baseName} · ${role}`,
    cwd: app.isPackaged ? path.dirname(target) : projectRoot,
    icon,
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

// Quick Play minimizes the launcher to the taskbar while Dragonwilds owns the
// foreground. The renderer decides when the game session has ended from the
// authoritative Quick status; this native restore keeps the same launcher
// window/process alive instead of closing or promoting a second window.
ipcMain.handle('dragonwilds:window-restore', (event) => {
  const window = BrowserWindow.fromWebContents(event.sender);
  if (!window || window.isDestroyed()) return false;
  if (window.isMinimized()) window.restore();
  window.show();
  window.focus();
  return true;
});

require('./main-v2.cjs');
