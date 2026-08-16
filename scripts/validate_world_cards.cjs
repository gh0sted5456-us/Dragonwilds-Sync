'use strict';

const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '..');
const fixture = path.join(__dirname, 'fixtures', 'world_cards.html');
const outputDir = path.join(root, 'Codex Outputs', 'GUI Validation');

function fail(message) {
  throw new Error(`World card GUI validation failed: ${message}`);
}

function intersects(a, b) {
  return a.left < b.right - 0.5 && a.right > b.left + 0.5 && a.top < b.bottom - 0.5 && a.bottom > b.top + 0.5;
}

async function inspect(win) {
  return win.webContents.executeJavaScript(`(() => {
    const rect = (node) => {
      const r=node.getBoundingClientRect();
      return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};
    };
    const card=document.querySelector('#validation-placard');
    const body=card.querySelector('.world-card-body');
    const footer=card.querySelector('.card-footer');
    const actions=card.querySelector('.placard-actions.integrated');
    const buttons=[...actions.querySelectorAll('.btn')].map(rect);
    const row=document.querySelector('#validation-row');
    const rowButtons=[...row.querySelectorAll('.btn')].map(rect);
    return {card:rect(card),body:rect(body),footer:rect(footer),actions:rect(actions),buttons,row:rect(row),rowButtons};
  })()`);
}

function validate(name, layout) {
  if (layout.actions.top + 0.5 < layout.body.bottom) fail(`${name}: action strip overlaps the card body`);
  if (layout.buttons.some((button) => button.top + 0.5 < layout.footer.bottom)) fail(`${name}: an action button overlaps the rating/footer`);
  if (layout.buttons.some((button) => button.left < layout.card.left - 0.5 || button.right > layout.card.right + 0.5)) fail(`${name}: an action button escapes the placard`);
  for (let i=0;i<layout.buttons.length;i+=1) for (let j=i+1;j<layout.buttons.length;j+=1) {
    if (intersects(layout.buttons[i],layout.buttons[j])) fail(`${name}: placard buttons overlap`);
  }
  if (layout.row.height > 90.5) fail(`${name}: horizontal card is ${layout.row.height}px tall; expected no more than 90px`);
  if (layout.rowButtons.some((button) => button.top < layout.row.top - 0.5 || button.bottom > layout.row.bottom + 0.5)) fail(`${name}: a horizontal action escapes its row`);
  for (let i=0;i<layout.rowButtons.length;i+=1) for (let j=i+1;j<layout.rowButtons.length;j+=1) {
    if (intersects(layout.rowButtons[i],layout.rowButtons[j])) fail(`${name}: horizontal buttons overlap`);
  }
}

app.disableHardwareAcceleration();
app.commandLine.appendSwitch('disable-gpu');
app.setPath('userData', path.join(os.tmpdir(), 'dragonwilds-sync-gui-validation'));
app.whenReady().then(async () => {
  fs.mkdirSync(outputDir, { recursive: true });
  const cases = [
    { name:'dark-desktop', theme:'dark', width:1100, height:900 },
    { name:'light-desktop', theme:'light', width:1100, height:900 },
    { name:'light-mobile', theme:'light', width:430, height:1100 },
  ];
  for (const testCase of cases) {
    const win = new BrowserWindow({ show:false, width:testCase.width, height:testCase.height, webPreferences:{ sandbox:true } });
    await win.loadFile(fixture);
    await win.webContents.executeJavaScript(`document.body.dataset.theme=${JSON.stringify(testCase.theme)}`);
    await new Promise((resolve) => setTimeout(resolve, 100));
    const layout = await inspect(win);
    validate(testCase.name, layout);
    const image = await win.webContents.capturePage();
    fs.writeFileSync(path.join(outputDir, `world-cards-${testCase.name}.png`), image.toPNG());
    console.log(`[OK] ${testCase.name}: placard buttons separated; horizontal height ${layout.row.height}px`);
    win.destroy();
  }
  console.log(`[OK] GUI screenshots: ${outputDir}`);
  app.quit();
}).catch((error) => {
  console.error(error.stack || error.message || String(error));
  app.exit(1);
});
