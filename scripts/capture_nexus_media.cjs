const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');

app.whenReady().then(async () => {
  const root = path.resolve(__dirname, '..');
  const outputDir = path.join(root, 'website', 'assets', 'nexus');
  fs.mkdirSync(outputDir, { recursive: true });
  const window = new BrowserWindow({
    width: 1400,
    height: 520,
    show: false,
    frame: false,
    backgroundColor: '#070a0b',
    webPreferences: { sandbox: true, contextIsolation: true },
  });
  try {
    await window.loadFile(path.join(root, 'docs', 'nexusmods', 'media-source.html'));
    await window.webContents.executeJavaScript('new Promise((resolve) => document.fonts.ready.then(() => requestAnimationFrame(() => resolve(true))))');
    const image = await window.webContents.capturePage({ x: 0, y: 0, width: 1400, height: 520 });
    const hero = path.join(outputDir, 'dragonwilds-sync-nexus-hero.png');
    fs.writeFileSync(hero, image.toPNG());
    const quickSource = path.join(root, 'test-results', 'quick-dashboard-v3.5.png');
    const quickTarget = path.join(outputDir, 'quick-server-dashboard-v3.5.png');
    if (fs.existsSync(quickSource)) fs.copyFileSync(quickSource, quickTarget);
    console.log(`Nexus media: ${hero}`);
    if (fs.existsSync(quickTarget)) console.log(`Nexus media: ${quickTarget}`);
  } catch (error) {
    console.error(error?.stack || error);
    process.exitCode = 1;
  } finally {
    window.destroy();
    app.quit();
  }
}).catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
  app.quit();
});
