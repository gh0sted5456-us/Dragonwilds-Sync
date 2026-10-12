'use strict';

const PROFILE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,239}$/;

function normalizeProfileId(value) {
  const id = String(value || '').trim();
  if (!PROFILE_ID_PATTERN.test(id)) throw new Error('World profile ID contains unsupported characters.');
  return id;
}

function normalizeQuickMode(value, fallback = 'player') {
  const mode = String(value || '').trim().toLowerCase();
  return ['player', 'coop', 'server'].includes(mode) ? mode : fallback;
}

function modeForWorldKind(value) {
  return String(value || '').trim().toLowerCase() === 'server' ? 'server' : 'player';
}

function buildQuickShortcutArgs({ profileId, mode = 'player', autoStart = true } = {}) {
  const id = normalizeProfileId(profileId);
  const normalizedMode = normalizeQuickMode(mode);
  return `--quick --profile=${id} --mode=${normalizedMode}${autoStart ? ' --auto-start' : ''}`;
}

function buildNormalShortcutArgs({ profileId, mode = 'player' } = {}) {
  const id = normalizeProfileId(profileId);
  const normalizedMode = normalizeQuickMode(mode);
  const worldKind = normalizedMode === 'server' ? 'server' : (normalizedMode === 'coop' ? 'private' : 'world');
  return `--world-id=${id} --world-kind=${worldKind}`;
}

function buildHeadlessShortcutArgs({ profileId, mode = 'server', command = 'run' } = {}) {
  const id = normalizeProfileId(profileId);
  const normalizedMode = normalizeQuickMode(mode, 'server');
  const normalizedCommand = String(command || 'run').trim().toLowerCase();
  if (!['run', 'start', 'status'].includes(normalizedCommand)) throw new Error('Unsupported headless shortcut command.');
  return `--headless ${normalizedCommand} --profile=${id} --mode=${normalizedMode}`;
}

module.exports = { buildHeadlessShortcutArgs, buildNormalShortcutArgs, buildQuickShortcutArgs, modeForWorldKind, normalizeProfileId, normalizeQuickMode };
