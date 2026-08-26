'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const assetRoot = path.join(root, 'renderer', 'assets');
const sourceRoots = ['renderer', 'electron', 'backend', 'scripts', 'help', 'docs', 'resources'];
const sourceFiles = ['package.json', 'package-lock.json', 'build.bat'];
const textExtensions = new Set([
  '.cjs', '.css', '.html', '.ini', '.js', '.json', '.jsonc', '.md', '.ps1', '.py',
  '.toml', '.txt', '.xml', '.yaml', '.yml',
]);

function walk(directory, files = []) {
  if (!fs.existsSync(directory)) return files;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(absolute, files);
    else files.push(absolute);
  }
  return files;
}

const mappings = walk(assetRoot)
  .filter((file) => file.toLowerCase().endsWith('.webp'))
  .map((file) => {
    const relative = path.relative(assetRoot, file).replaceAll('\\', '/');
    return {
      oldAsset: `assets/${relative.replace(/\.webp$/i, '.png')}`,
      newAsset: `assets/${relative}`,
      oldRenderer: `renderer/assets/${relative.replace(/\.webp$/i, '.png')}`,
      newRenderer: `renderer/assets/${relative}`,
    };
  });

const candidates = sourceRoots.flatMap((directory) => walk(path.join(root, directory)))
  .concat(sourceFiles.map((file) => path.join(root, file)))
  .filter((file) => fs.existsSync(file) && textExtensions.has(path.extname(file).toLowerCase()));

let changedFiles = 0;
let replacements = 0;
for (const file of candidates) {
  const original = fs.readFileSync(file, 'utf8');
  let updated = original;
  for (const mapping of mappings) {
    for (const [from, to] of [
      [mapping.oldRenderer, mapping.newRenderer],
      [mapping.oldAsset, mapping.newAsset],
    ]) {
      if (!updated.includes(from)) continue;
      const pieces = updated.split(from);
      replacements += pieces.length - 1;
      updated = pieces.join(to);
    }
  }
  if (updated !== original) {
    fs.writeFileSync(file, updated, 'utf8');
    changedFiles += 1;
  }
}

console.log(`Updated ${replacements} packaged image references across ${changedFiles} files.`);
