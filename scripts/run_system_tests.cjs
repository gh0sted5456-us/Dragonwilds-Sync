const { spawnSync } = require('child_process');
const path = require('path');

const configured = String(process.env.DRAGONWILDS_SYNC_PYTHON || '').trim();
const workspacePython = process.platform === 'win32'
  ? path.resolve('.venv-build', 'Scripts', 'python.exe')
  : path.resolve('.venv-build', 'bin', 'python');
const candidates = [
  ...(configured ? [{ command: configured, prefix: [] }] : []),
  { command: workspacePython, prefix: [] },
  ...(process.platform === 'win32'
    ? [{ command: 'py', prefix: ['-3'] }, { command: 'python', prefix: [] }, { command: 'python3', prefix: [] }]
    : [{ command: 'python3', prefix: [] }, { command: 'python', prefix: [] }]),
];

let python = null;
for (const candidate of candidates) {
  const probe = spawnSync(candidate.command, [...candidate.prefix, '--version'], { stdio: 'ignore', shell: false });
  if (!probe.error && probe.status === 0) {
    python = candidate;
    break;
  }
}
if (!python) {
  console.error('[ERROR] Python 3 was not found. Set DRAGONWILDS_SYNC_PYTHON or install Python 3.');
  process.exit(1);
}

const result = spawnSync(
  python.command,
  [...python.prefix, path.resolve('scripts', 'run_system_tests.py'), ...process.argv.slice(2)],
  { stdio: 'inherit', shell: false, env: process.env },
);
if (result.error) {
  console.error(`[ERROR] Could not launch system tests: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status == null ? 1 : result.status);
