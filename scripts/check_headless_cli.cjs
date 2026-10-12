const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');
const requireText = (text, token, label) => {
  if (!text.includes(token)) throw new Error(`Headless contract missing ${label}: ${token}`);
};

const bootstrap = read('electron/bootstrap.cjs');
const service = read('backend/dragonwilds_service.py');
const cli = read('backend/headless_cli.py');

requireText(bootstrap, "process.argv.includes('--headless')", 'no-renderer bootstrap gate');
requireText(bootstrap, "stdio: 'inherit'", 'terminal stdio inheritance');
requireText(service, 'from headless_cli import run as _headless_run', 'service CLI dispatch');
requireText(cli, 'handle("quick.start"', 'shared Quick start authority');
requireText(cli, 'handle("quick.stop"', 'shared Quick stop authority');
requireText(cli, '("world.discovery.heartbeat", "client.background.tick")', 'continuous World heartbeat');
requireText(cli, '"server.scheduler.tick"', 'server scheduler ownership');
requireText(cli, 'stop_on_exit=False', 'log-follow detach safety');
if (cli.includes('handle("application.shutdown"')) throw new Error('One-shot CLI commands must not stop attached runtime workers.');

console.log('Headless CLI contracts passed.');
