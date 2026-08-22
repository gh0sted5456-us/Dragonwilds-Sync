const net = require('net');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

const DISCORD_APPLICATION_ID = '1537292761303097364';
const DISCORD_PUBLIC_KEY = '0583e9dc6227d2a7cca010adf1d9a233d8ffbe23246d871521c6fc1bd7693402';

function frame(op, payload) {
  const body = Buffer.from(JSON.stringify(payload), 'utf8');
  const header = Buffer.allocUnsafe(8);
  header.writeUInt32LE(op, 0);
  header.writeUInt32LE(body.length, 4);
  return Buffer.concat([header, body]);
}

function candidatePipes() {
  if (process.platform === 'win32') {
    return Array.from({ length: 10 }, (_, i) => `\\\\?\\pipe\\discord-ipc-${i}`);
  }
  const bases = [process.env.XDG_RUNTIME_DIR, process.env.TMPDIR, process.env.TMP, process.env.TEMP, '/tmp']
    .filter(Boolean);
  const found = [];
  for (const base of bases) {
    for (let i = 0; i < 10; i++) found.push(path.join(base, `discord-ipc-${i}`));
  }
  return [...new Set(found)];
}

class DiscordRichPresence {
  constructor() {
    this.socket = null;
    this.buffer = Buffer.alloc(0);
    this.ready = false;
    this.connecting = null;
    this.lastActivity = null;
    this.lastError = '';
    this.connectedPipe = '';
  }

  status() {
    return {
      application_id: DISCORD_APPLICATION_ID,
      public_key: DISCORD_PUBLIC_KEY,
      connected: !!(this.socket && !this.socket.destroyed),
      ready: this.ready,
      pipe: this.connectedPipe,
      last_error: this.lastError,
      transport: 'discord-desktop-rpc',
    };
  }

  async connect() {
    if (this.socket && !this.socket.destroyed && this.ready) return true;
    if (this.connecting) return this.connecting;
    this.connecting = this._connectAny().finally(() => { this.connecting = null; });
    return this.connecting;
  }

  async _connectAny() {
    this.destroy();
    for (const pipeName of candidatePipes()) {
      try {
        const socket = await new Promise((resolve, reject) => {
          const s = net.createConnection(pipeName);
          const timer = setTimeout(() => { s.destroy(); reject(new Error('Discord IPC timeout')); }, 350);
          s.once('connect', () => { clearTimeout(timer); resolve(s); });
          s.once('error', (err) => { clearTimeout(timer); reject(err); });
        });
        this.socket = socket;
        this.connectedPipe = pipeName;
        this.ready = false;
        socket.on('data', chunk => this._onData(chunk));
        socket.on('error', err => { this.lastError = err.message; this.ready = false; });
        socket.on('close', () => { this.ready = false; this.socket = null; });
        socket.write(frame(0, { v: 1, client_id: DISCORD_APPLICATION_ID }));
        await this._waitReady(1000);
        this.lastError = '';
        if (this.lastActivity) this._sendActivity(this.lastActivity);
        return true;
      } catch (error) {
        this.lastError = error.message;
      }
    }
    return false;
  }

  _waitReady(timeoutMs) {
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const tick = () => {
        if (this.ready) return resolve(true);
        if (!this.socket || this.socket.destroyed) return reject(new Error('Discord desktop client is not connected'));
        if (Date.now() - started >= timeoutMs) return reject(new Error('Discord RPC handshake timed out'));
        setTimeout(tick, 25);
      };
      tick();
    });
  }

  _onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (this.buffer.length >= 8) {
      const op = this.buffer.readUInt32LE(0);
      const len = this.buffer.readUInt32LE(4);
      if (len > 1024 * 1024) { this.destroy(); return; }
      if (this.buffer.length < 8 + len) return;
      const body = this.buffer.subarray(8, 8 + len).toString('utf8');
      this.buffer = this.buffer.subarray(8 + len);
      try {
        const message = JSON.parse(body);
        if (op === 1 && message && (message.evt === 'READY' || message.cmd === 'DISPATCH')) this.ready = true;
        if (op === 2 && this.socket) this.socket.write(frame(3, message));
      } catch (_) { /* malformed Discord frames are ignored */ }
    }
  }

  async setActivity(activity) {
    this.lastActivity = activity || null;
    if (!(await this.connect())) return this.status();
    this._sendActivity(this.lastActivity);
    return this.status();
  }

  _sendActivity(activity) {
    if (!this.socket || this.socket.destroyed || !this.ready) return;
    const safe = activity ? {
      details: String(activity.details || '').slice(0, 128) || undefined,
      state: String(activity.state || '').slice(0, 128) || undefined,
      timestamps: activity.startTimestamp ? { start: Number(activity.startTimestamp) } : undefined,
      assets: activity.largeImage || activity.largeText || activity.smallImage || activity.smallText ? {
        large_image: activity.largeImage || undefined,
        large_text: String(activity.largeText || '').slice(0, 128) || undefined,
        small_image: activity.smallImage || undefined,
        small_text: String(activity.smallText || '').slice(0, 128) || undefined,
      } : undefined,
      buttons: Array.isArray(activity.buttons) ? activity.buttons.slice(0, 2).map((button) => ({
        label: String(button?.label || '').slice(0, 32),
        url: /^https:\/\//i.test(String(button?.url || '')) ? String(button.url) : undefined,
      })).filter((button) => button.label && button.url) : undefined,
      party: activity.partySize != null && activity.partyMax != null ? {
        size: [Number(activity.partySize) || 0, Number(activity.partyMax) || 0],
      } : undefined,
      instance: false,
    } : null;
    const payload = {
      cmd: 'SET_ACTIVITY',
      args: { pid: process.pid, activity: safe },
      nonce: crypto.randomUUID(),
    };
    try { this.socket.write(frame(1, payload)); }
    catch (error) { this.lastError = error.message; }
  }

  clear() { return this.setActivity(null); }

  destroy() {
    if (this.socket) {
      try { this.socket.destroy(); } catch (_) {}
    }
    this.socket = null;
    this.ready = false;
    this.connectedPipe = '';
    this.buffer = Buffer.alloc(0);
  }
}

module.exports = { DiscordRichPresence, DISCORD_APPLICATION_ID, DISCORD_PUBLIC_KEY };
