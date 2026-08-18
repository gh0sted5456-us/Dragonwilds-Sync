'use strict';

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const nvmrc = fs.readFileSync(path.join(root, '.nvmrc'), 'utf8').trim();
const expectedMajor = Number((nvmrc.match(/^(\d+)/) || [])[1] || 0);
const actual = process.versions.node;
const actualMajor = Number(actual.split('.')[0]);

if (!expectedMajor) {
  console.error('[ERROR] .nvmrc does not declare a valid Node major version.');
  process.exit(1);
}

if (actualMajor !== expectedMajor) {
  console.error(`[ERROR] Dragonwilds Sync requires Node ${expectedMajor}.x LTS for this branch; running Node ${actual}.`);
  console.error(`        Install/use Node ${nvmrc} (for nvm: nvm install && nvm use).`);
  process.exit(1);
}

console.log(`Node runtime contract: PASS · ${actual} (pinned ${nvmrc})`);
