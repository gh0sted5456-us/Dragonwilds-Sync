const dgram = require("dgram");
const os = require("os");
const manifest = require("./manifest");

const DISCOVERY_PORT = 27051;
const MAGIC = "dragonwilds-sync-discovery-v2";
const state = globalThis.__DRAGONWILDS_SYNC_DISCOVERY || (globalThis.__DRAGONWILDS_SYNC_DISCOVERY = {
  socket: null, worldId: null, port: null, timer: null, startedAt: null,
});

function localAddresses() {
  const out = [];
  for (const entries of Object.values(os.networkInterfaces())) {
    for (const item of entries || []) if (item.family === "IPv4" && !item.internal) out.push(item.address);
  }
  return out;
}

function advertisement(worldId, syncPort = 4317) {
  const value = manifest.buildWorldManifest(worldId);
  return {
    magic: MAGIC,
    protocol: value.protocol,
    protocolVersion: value.protocolVersion,
    worldId: value.world.id,
    name: value.world.name,
    gamePort: value.world.gamePort,
    syncPort,
    revision: value.revision,
    modCount: value.units.length,
    modBadges: [...new Set(value.units.map((unit) => unit.type.toUpperCase()))],
    addresses: localAddresses(),
    generatedAt: value.generatedAt,
  };
}

function send(socket, payload, port, address) {
  const data = Buffer.from(JSON.stringify(payload));
  socket.send(data, port, address, () => {});
}

function start(worldId, options = {}) {
  stop();
  const port = Number(options.discoveryPort || DISCOVERY_PORT);
  const syncPort = Number(options.syncPort || 4317);
  const socket = dgram.createSocket({ type: "udp4", reuseAddr: true });
  socket.on("message", (data, remote) => {
    try {
      const request = JSON.parse(data.toString("utf8"));
      if (request?.magic === MAGIC && request?.action === "probe") send(socket, { ...advertisement(worldId, syncPort), action: "advertisement" }, remote.port, remote.address);
    } catch { /* ignore unrelated UDP traffic */ }
  });
  socket.on("error", () => stop());
  socket.bind(port, "0.0.0.0", () => {
    socket.setBroadcast(true);
    const announce = () => send(socket, { ...advertisement(worldId, syncPort), action: "advertisement" }, port, "255.255.255.255");
    announce();
    state.timer = setInterval(announce, 5000);
    state.timer.unref?.();
  });
  state.socket = socket;
  state.worldId = worldId;
  state.port = port;
  state.startedAt = Date.now();
  return status();
}

function stop() {
  if (state.timer) clearInterval(state.timer);
  if (state.socket) { try { state.socket.close(); } catch {} }
  state.socket = null; state.timer = null; state.worldId = null; state.port = null; state.startedAt = null;
  return status();
}

function status() {
  return { broadcasting: !!state.socket, worldId: state.worldId, discoveryPort: state.port, startedAt: state.startedAt };
}

function probe(address = "255.255.255.255", options = {}) {
  const port = Number(options.discoveryPort || DISCOVERY_PORT);
  const timeout = Math.min(Math.max(Number(options.timeoutMs || 3000), 250), 10000);
  return new Promise((resolve, reject) => {
    const socket = dgram.createSocket("udp4");
    const rows = new Map();
    const finish = () => { try { socket.close(); } catch {}; resolve([...rows.values()]); };
    const timer = setTimeout(finish, timeout);
    socket.on("error", (error) => { clearTimeout(timer); try { socket.close(); } catch {}; reject(error); });
    socket.on("message", (data, remote) => {
      try {
        const row = JSON.parse(data.toString("utf8"));
        if (row?.magic !== MAGIC || row?.action !== "advertisement") return;
        rows.set(`${row.worldId}:${remote.address}:${row.syncPort}`, { ...row, queriedIp: remote.address });
      } catch { /* ignore */ }
    });
    socket.bind(0, "0.0.0.0", () => {
      socket.setBroadcast(true);
      send(socket, { magic: MAGIC, action: "probe" }, port, address);
    });
  });
}

module.exports = { DISCOVERY_PORT, MAGIC, start, stop, status, probe, advertisement };
