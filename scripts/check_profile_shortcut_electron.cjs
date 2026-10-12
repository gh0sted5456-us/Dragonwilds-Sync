'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { app, shell } = require('electron');
const { buildQuickShortcutArgs } = require('../electron/quick_shortcut.cjs');

async function main() {
  if (process.platform !== 'win32') {
    console.log('profile desktop shortcut smoke test skipped outside Windows');
    return;
  }
  const desktop = app.getPath('desktop');
  const cases = [
    { file: 'Dragonwilds Sync Player Shortcut Verification.lnk', id: 'verification-player', mode: 'player' },
    { file: 'Dragonwilds Sync Server Shortcut Verification.lnk', id: 'verification-server', mode: 'server' },
  ];
  try {
    for (const item of cases) {
      const shortcutPath = path.join(desktop, item.file);
      const args = buildQuickShortcutArgs({ profileId: item.id, mode: item.mode, autoStart: true });
      const created = shell.writeShortcutLink(shortcutPath, 'create', {
        target: process.execPath,
        args,
        description: `Dragonwilds Sync ${item.mode} shortcut verification`,
        cwd: path.dirname(process.execPath),
        icon: process.execPath,
        iconIndex: 0,
      });
      assert.strictEqual(created, true, `Windows did not create ${item.mode} shortcut`);
      const saved = shell.readShortcutLink(shortcutPath);
      assert.strictEqual(path.resolve(saved.target), path.resolve(process.execPath));
      assert.strictEqual(saved.args, args);
      fs.unlinkSync(shortcutPath);
    }
    console.log('physical Player and Server desktop shortcut smoke tests passed');
  } finally {
    for (const item of cases) fs.rmSync(path.join(desktop, item.file), { force: true });
  }
}

app.whenReady().then(main).then(() => app.quit()).catch((error) => {
  console.error(error?.stack || error);
  app.exit(1);
});
