const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

app.whenReady().then(async () => {
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, 'test-results', 'quick-dashboard-v3.5.png');
  fs.mkdirSync(path.dirname(output), { recursive: true });
  const window = new BrowserWindow({
    width: 1100, height: 820, show: false, backgroundColor: '#050808',
    webPreferences: { preload: path.join(__dirname, 'quick_window_fixture_preload.cjs'), contextIsolation: true, sandbox: false }
  });
  try {
    await window.loadFile(path.join(root, 'renderer', 'quick.html'));
    await window.webContents.executeJavaScript(`new Promise((resolve, reject) => {
      const limit = Date.now() + 8000;
      const timer = setInterval(() => {
        const shell = document.querySelector('[data-v3-quick-root]');
        if (shell) { clearInterval(timer); requestAnimationFrame(() => requestAnimationFrame(resolve)); }
        else if (Date.now() > limit) { clearInterval(timer); reject(new Error('Quick dashboard did not render')); }
      }, 50);
    })`);
    const layout = await window.webContents.executeJavaScript(`(() => {
      const box = (selector) => document.querySelector(selector)?.getBoundingClientRect();
      const root = box('#app'); const shell = box('.v3q-shell'); const header = box('.v3q-header'); const toolbar = box('.v3q-toolbar'); const telemetry = box('.v3q-telemetry-grid');
      const dragonLink = document.querySelector('[data-v3q-section="dragonlink"]');
      const autoHelper = document.querySelector('.v3q-autostart small');
      return {
        root: root && { width: root.width }, shell: shell && { width: shell.width }, header: header && { width: header.width }, toolbar: toolbar && { width: toolbar.width }, telemetry: telemetry && { width: telemetry.width },
        launchPlan: !!document.querySelector('.v3q-launch-plan'),
        dragonLinkVisible: !!dragonLink && getComputedStyle(dragonLink).display !== 'none' && dragonLink.getBoundingClientRect().width > 0,
        autoHelperDisplay: autoHelper ? getComputedStyle(autoHelper).display : '',
        scrollWidth: document.documentElement.scrollWidth, viewport: innerWidth
      };
    })()`);
    for (const [name, value] of Object.entries({ root: layout.root?.width, shell: layout.shell?.width, header: layout.header?.width, toolbar: layout.toolbar?.width })) {
      if (!(value > 900)) throw new Error(`${name} collapsed to ${value}px`);
    }
    if (layout.scrollWidth > layout.viewport + 2) throw new Error(`Quick dashboard overflows horizontally (${layout.scrollWidth} > ${layout.viewport})`);
    if (!(layout.telemetry?.width > 900)) throw new Error(`Server telemetry collapsed to ${layout.telemetry?.width}px`);
    if (layout.launchPlan) throw new Error('Idle server Quick dashboard must not show the Hosted Server launch path');
    if (layout.dragonLinkVisible) throw new Error('Retired DragonLink controls must not be visible in Quick');
    if (layout.autoHelperDisplay !== 'block') throw new Error(`Quick auto-start helper must occupy its own line (display=${layout.autoHelperDisplay || 'missing'})`);
    const image = await window.webContents.capturePage();
    fs.writeFileSync(output, image.toPNG());
    console.log(`Quick dashboard: PASS · full-width responsive layout · retired DragonLink controls hidden · ${output}`);
  } catch (error) {
    console.error(error?.stack || error);
    process.exitCode = 1;
  } finally {
    window.destroy();
    app.quit();
  }
});
