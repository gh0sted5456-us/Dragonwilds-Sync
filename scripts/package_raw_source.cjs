#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const projectRoot = path.resolve(__dirname, '..');
const outputRoot = path.resolve(
  process.env.DWSYNC_RAW_OUTPUT ||
  process.argv[2] ||
  path.join(projectRoot, 'Codex Outputs', 'DragonwildsSync_V2_Raw_Source'),
);

const sourceDirectories = [
  '.github',
  'backend',
  'cloudflare',
  'docs',
  'electron',
  'help',
  'renderer',
  'resources',
  'scripts',
  'website',
];

const sourceFiles = [
  '.gitignore',
  'build.bat',
  'LICENSE.txt',
  'package-lock.json',
  'package.json',
  'README.md',
  'RELEASE.txt',
];

const excludedDirectoryNames = new Set([
  '__pycache__',
  '.pytest_cache',
  '.venv',
  '.test-venv',
  '.venv-linux-build',
  'node_modules',
  'release',
  'release-linux',
  'dist-service',
  'dist-service-linux',
  'build-service',
  'build-service-linux',
  'flatpak-build',
  'flatpak-repo',
  'build-logs',
  'build',
  'build-tests',
  'dist',
]);

const excludedExtensions = new Set(['.pyc', '.pyo']);

function assertSafeOutput() {
  const relative = path.relative(projectRoot, outputRoot);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error(`Raw-source output must remain inside the project: ${outputRoot}`);
  }
  const normalized = relative.split(path.sep).join('/');
  if (!normalized.startsWith('Codex Outputs/')) {
    throw new Error(`Raw-source output must be under Codex Outputs: ${outputRoot}`);
  }
}

function includePath(candidate) {
  const stat = fs.statSync(candidate);
  if (stat.isDirectory() && excludedDirectoryNames.has(path.basename(candidate))) return false;
  if (candidate.includes(`${path.sep}renderer${path.sep}vendor${path.sep}monaco`)) return false;
  if (stat.isFile() && excludedExtensions.has(path.extname(candidate).toLowerCase())) return false;
  return true;
}

function copyRequired(relativePath) {
  const source = path.join(projectRoot, relativePath);
  const destination = path.join(outputRoot, relativePath);
  if (!fs.existsSync(source)) throw new Error(`Required raw-source input is missing: ${relativePath}`);
  const stat = fs.statSync(source);
  if (stat.isDirectory()) {
    fs.cpSync(source, destination, { recursive: true, force: true, filter: includePath });
  } else {
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.copyFileSync(source, destination);
  }
}

function countFiles(root) {
  let total = 0;
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const full = path.join(root, entry.name);
    total += entry.isDirectory() ? countFiles(full) : 1;
  }
  return total;
}

assertSafeOutput();
fs.rmSync(outputRoot, { recursive: true, force: true });
fs.mkdirSync(outputRoot, { recursive: true });

for (const directory of sourceDirectories) copyRequired(directory);
for (const file of sourceFiles) copyRequired(file);

const generated = new Date().toISOString();
const manifest = `# Dragonwilds Sync V2 Raw Source\n\nGenerated: ${generated}\n\nThis folder is a reproducible Windows source/build workspace. Generated dependency and compiler outputs are intentionally omitted.\n\n## Build\n\n- Windows: run \`build.bat\` or \`npm run build:win\`.\n- Verification only: run \`npm ci\`, then \`npm run verify\`.\n\nThe build restores pinned Node/Python dependencies, regenerates Monaco under \`renderer/vendor\`, verifies the service and renderer, and produces the portable Windows executable. Official releases also provide an Ubuntu AppImage built by GitHub Actions.\n\nHelp screenshots, third-party attribution, runtime bootstrap archives, tests, and release documentation are included. User data, passwords, server profiles, game saves, caches, logs, dependency folders, and compiled release output are not included.\n`;
fs.writeFileSync(path.join(outputRoot, 'RAW_SOURCE_CONTENTS.md'), manifest, 'utf8');

const fileCount = countFiles(outputRoot);
process.stdout.write(`Raw source staged: ${outputRoot}\nFiles: ${fileCount}\n`);
