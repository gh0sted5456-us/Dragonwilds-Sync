'use strict';

const fs = require('fs');
const path = require('path');

const HEADLESS_EXE_PATTERN = /^Dragonwilds Sync Headless-(.+)\.exe$/i;

function resolveGuiShortcutTarget(executablePath) {
  const target = path.resolve(String(executablePath || ''));
  if (!target) throw new Error('The normal application executable path is unavailable.');
  return target;
}

function resolveHeadlessShortcutTarget({ executablePath, version = '', requestedPath = '', existsSync = fs.existsSync, readdirSync = fs.readdirSync } = {}) {
  const explicit = String(requestedPath || '').trim();
  if (explicit) {
    const target = path.resolve(explicit);
    if (existsSync(target) && HEADLESS_EXE_PATTERN.test(path.basename(target))) return target;
    throw new Error('The selected headless executable is missing or is not a Dragonwilds Sync Headless EXE.');
  }
  const guiTarget = resolveGuiShortcutTarget(executablePath);
  const directory = path.dirname(guiTarget);
  const exact = path.join(directory, `Dragonwilds Sync Headless-${String(version || '').trim()}.exe`);
  if (version && existsSync(exact)) return exact;
  const candidates = readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isFile() && HEADLESS_EXE_PATTERN.test(entry.name))
    .map((entry) => path.join(directory, entry.name))
    .sort((left, right) => right.localeCompare(left, undefined, { numeric: true, sensitivity: 'base' }));
  if (candidates.length) return candidates[0];
  throw new Error('No standalone Headless EXE was found beside the normal application. Place both downloads in the same folder, then recreate the shortcut.');
}

module.exports = { HEADLESS_EXE_PATTERN, resolveGuiShortcutTarget, resolveHeadlessShortcutTarget };
