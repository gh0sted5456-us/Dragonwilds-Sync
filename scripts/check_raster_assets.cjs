'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const assets = path.join(root, 'renderer', 'assets');
const remaining = [];

function walk(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(absolute);
    else if (entry.name.toLowerCase().endsWith('.png')) remaining.push(path.relative(root, absolute));
  }
}

walk(assets);
if (remaining.length) {
  throw new Error(`Packaged PNG assets must be converted with scripts/optimize_raster_assets.py:\n${remaining.join('\n')}`);
}

for (const required of [
  'renderer/assets/dragonwilds_icon.ico',
  'renderer/assets/navigation/sync.svg',
  'renderer/assets/platforms/paks.svg',
]) {
  const absolute = path.join(root, required);
  if (!fs.existsSync(absolute) || fs.statSync(absolute).size === 0) {
    throw new Error(`Required native/vector icon is missing: ${required}`);
  }
}

console.log('Packaged raster asset contract: PASS · WebP/SVG with Windows ICO retained');
