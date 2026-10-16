const dgram = require("dgram");
const os = require("os");
const net = require("net");

const DISCOVERY_PORT = 27051;
const MAGIC = "dragonwilds-sync-discovery-v2";
const state = globalThis.__DRAGONWILDS_SYNC_DISCOVERY || (globalThis.__DRAGONWILDS_SYNC_DISCOVERY = {
  socket: null, port: null, syncPort: null, startedAt: null, error: null, starting: null, cancelStart: null,
});
function validPort(value) { return Number.isInteger(value) && value >= 1 && value <= 65535; }
function boundedTimeout(value, fallback, min, max) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.min(Math.max(numeric, min), max) : fallback;
}

// Directed broadcasts reach each configured adapter, not just Windows' default route.
function broadcastTargets(interfaces = os.networkInterfaces()) {
  const targets = new Set(["255.255.255.255"]);
  for (const entries of Object.values(interfaces)) {
    for (const item of entries || []) {
      if (!["IPv4", 4].includes(item.family) || item.internal || net.isIP(item.address) !== 4 || net.isIP(item.netmask) !== 4) continue;
      const address = item.address.split(".").map(Number);
      const mask = item.netmask.split(".").map(Number);
      // Point-to-point adapters (/31, /32) do not have a LAN broadcast address.
      const hostBits = mask.reduce((sum, byte) => sum + (255 - byte), 0);
      if (hostBits <= 1) continue;
      targets.add(address.map((byte, index) => byte | (255 ^ mask[index])).join("."));
    }
  }
  return [...targets];
}
function send(socket, payload, port, address) {
  try { socket.send(Buffer.from(JSON.stringify(payload)), port, address, () => {}); } catch { /* closing */ }
}

// Announce the directory, not its files or credentials. Clients then fetch its
// public preview over TCP and explicitly authenticate before importing a manifest.
async function start(_worldId, options = {}) {
  const port = Number(options.discoveryPort || DISCOVERY_PORT);
  const syncPort = Number(options.syncPort || process.env.APP_MANAGER_SHARE_PORT || process.env.APP_MANAGER_PORT || 4318);
  if (!validPort(port) || !validPort(syncPort)) throw new Error("Invalid discovery or Sync port.");
  if (state.socket && state.port === port && state.syncPort === syncPort) return state.starting || status();
  stop();
  const socket = dgram.createSocket({ type: "udp4", reuseAddr: true });
  state.socket = socket; state.port = port; state.syncPort = syncPort; state.error = null;
  const recent = new Map();
  const payload = { magic: MAGIC, action: "directory", syncPort };
  socket.on("message", (data, remote) => {
    if (state.socket !== socket || data.length > 512) return;
    try {
      const request = JSON.parse(data.toString("utf8"));
      if (request?.magic !== MAGIC || request?.action !== "probe") return;
      const now = Date.now();
      if (now - (recent.get(remote.address) || 0) < 250) return;
      if (recent.size >= 256) recent.clear();
      recent.set(remote.address, now);
      send(socket, payload, remote.port, remote.address);
    } catch { /* unrelated or malformed UDP traffic */ }
  });
  const ready = new Promise((resolve, reject) => {
    state.cancelStart = reject;
    socket.on("error", (error) => {
      // Keep the real bind/socket error rather than replacing it with "stopped".
      state.cancelStart = null;
      if (state.socket === socket) { stop(); state.error = error.message; }
      reject(error);
    });
    socket.bind(port, options.bindHost || "0.0.0.0", () => {
      if (state.socket !== socket) { reject(new Error("LAN discovery was stopped.")); return; }
      state.startedAt = Date.now();
      state.cancelStart = null;
      socket.unref?.();
      resolve(status());
    });
  });
  state.starting = ready;
  try { return await ready; }
  finally { if (state.starting === ready) state.starting = null; }
}
function stop() {
  state.cancelStart?.(new Error("LAN discovery was stopped."));
  state.cancelStart = null; state.starting = null;
  if (state.socket) { try { state.socket.close(); } catch {} }
  state.socket = null; state.port = null; state.syncPort = null; state.startedAt = null; state.error = null;
  return status();
}
function status() {
  return { broadcasting: !!state.socket && !!state.startedAt, discoveryPort: state.port || DISCOVERY_PORT, syncPort: state.syncPort, startedAt: state.startedAt, error: state.error };
}

// Accept only bounded, typed advertisements; never trust advertised addresses.
// Legacy v2 world advertisements remain compatible with older RSDW hosts.
function parseAdvertisement(data, remote) {
  if (data.length > 8192 || net.isIP(remote.address) !== 4) return null;
  try {
    const row = JSON.parse(data.toString("utf8"));
    if (row?.magic !== MAGIC || !validPort(Number(row.syncPort))) return null;
    const base = { queriedIp: remote.address, syncPort: Number(row.syncPort) };
    if (row.action === "directory") return base;
    if (row.action !== "advertisement" || typeof row.worldId !== "string" || !row.worldId || row.worldId.length > 128) return null;
    return {
      ...base, worldId: row.worldId, name: String(row.name || "World").slice(0, 120),
      gamePort: validPort(Number(row.gamePort)) ? Number(row.gamePort) : undefined,
      revision: String(row.revision || "").slice(0, 256),
      modCount: Number.isSafeInteger(row.modCount) && row.modCount >= 0 ? row.modCount : 0,
      modBadges: Array.isArray(row.modBadges) ? row.modBadges.filter((badge) => typeof badge === "string").slice(0, 16).map((badge) => badge.slice(0, 32)) : [],
      rules: { access: String(row.rules?.access || "Private").slice(0, 32), passwordRequired: row.rules?.passwordRequired !== false },
    };
  } catch { return null; }
}
function probePackets(targets, options = {}) {
  const port = Number(options.discoveryPort || DISCOVERY_PORT);
  if (!validPort(port)) return Promise.reject(new Error("Invalid LAN discovery port."));
  const timeout = boundedTimeout(options.timeoutMs, 3000, 250, 10000);
  return new Promise((resolve, reject) => {
    const socket = dgram.createSocket("udp4");
    const rows = new Map();
    let done = false, retry = null;
    const finish = (error) => {
      if (done) return;
      done = true; clearTimeout(timer); clearTimeout(retry);
      try { socket.close(); } catch {}
      if (error) reject(error); else resolve([...rows.values()]);
    };
    const timer = setTimeout(() => finish(), timeout);
    socket.on("error", finish);
    socket.on("message", (data, remote) => {
      if (done) return;
      const row = parseAdvertisement(data, remote);
      if (!row) return;
      const key = `${row.worldId || "directory"}:${row.queriedIp}:${row.syncPort}`;
      if (rows.size < 64 || rows.has(key)) rows.set(key, row);
    });
    socket.bind(0, "0.0.0.0", () => {
      if (done) return;
      try { socket.setBroadcast(true); } catch (error) { finish(error); return; }
      const query = () => targets.forEach((target) => send(socket, { magic: MAGIC, action: "probe" }, port, target));
      query();
      if (timeout > 1000) retry = setTimeout(query, 1000);
    });
  });
}
async function probe(address = "255.255.255.255", options = {}) {
  const targets = address === "255.255.255.255" ? broadcastTargets() : [address];
  const packets = await probePackets(targets, options);
  const worlds = packets.filter((row) => row.worldId);
  // Bounded concurrency, one request per actual responder. A failed directory
  // must not hide healthy hosts; directory reads have their own short timeout.
  const directories = packets.filter((row) => !row.worldId).slice(0, 16);
  for (let offset = 0; offset < directories.length; offset += 4) {
    const batch = await Promise.all(directories.slice(offset, offset + 4).map(async (row) => {
      try { return await probeDirect(`${row.queriedIp}:${row.syncPort}`, { timeoutMs: 2000 }); } catch { return []; }
    }));
    worlds.push(...batch.flat());
  }
  return [...new Map(worlds.slice(0, 256).map((row) => [`${row.worldId}:${row.queriedIp}:${row.syncPort}`, row])).values()];
}

function parseEndpoint(input, defaultPort = 4318) {
  const raw = String(input || "").trim();
  if (!raw) throw new Error("Enter the server IP address.");
  const value = /^https?:\/\//i.test(raw) ? raw : `http://${raw}`;
  const url = new URL(value);
  if (url.protocol !== "http:" || url.username || url.password || (url.pathname && url.pathname !== "/")) throw new Error("Enter an IP address or hostname, optionally followed by :port.");
  return { address: url.hostname, syncPort: Number(url.port || defaultPort) };
}

async function probeDirect(input, options = {}) {
  const endpoint = parseEndpoint(input, Number(options.syncPort || 4318));
  if (!Number.isInteger(endpoint.syncPort) || endpoint.syncPort < 1 || endpoint.syncPort > 65535) throw new Error("Invalid Sync port.");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Math.min(Math.max(Number(options.timeoutMs || 8000), 1000), 15000));
  try {
    const response = await fetch(`http://${endpoint.address}:${endpoint.syncPort}/api/sync/public`, { cache: "no-store", signal: controller.signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !Array.isArray(payload.worlds)) throw new Error(payload.error || "This address is not publishing an RSDW Sync directory.");
    return payload.worlds.map((world) => ({ ...world, queriedIp: endpoint.address, syncPort: Number(world.syncPort || endpoint.syncPort) }));
  } finally { clearTimeout(timeout); }
}

module.exports = { DISCOVERY_PORT, MAGIC, start, stop, status, probe, probeDirect, parseEndpoint, broadcastTargets, parseAdvertisement };
