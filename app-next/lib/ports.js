// lib/ports.js  (spec §2 port allocation)
const net = require("net");
const { listWorlds } = require("./db");

// Suggest the next free port block: worldN -> 8211+10*(N-1) etc.
function suggestPorts() {
  const worlds = listWorlds();
  const used = new Set();
  for (const w of worlds) {
    used.add(w.game_port); used.add(w.query_port);
    used.add(w.rest_api_port); used.add(w.rcon_port);
  }
  // Dragonwilds defaults start at 7777
  let base = 7777, rcon = 25575;
  for (let i = 0; i < 500; i++) {
    const game = base + i * 10;
    const query = game + 1;
    const rest = game + 2;   // e.g. 8213 — distinct from game(8211) and query(8212)
    const rc = rcon + i;
    if (![game, query, rest, rc].some((p) => used.has(p))) {
      return { game_port: game, query_port: query, rest_api_port: rest, rcon_port: rc };
    }
  }
  return { game_port: 7777, query_port: 7778, rest_api_port: 7779, rcon_port: 25575 };
}

// Returns list of ports that collide with existing profiles.
function conflictsInRegistry(ports, excludeWorldId) {
  const worlds = listWorlds().filter((w) => w.world_id !== excludeWorldId);
  const taken = new Map();
  for (const w of worlds) {
    for (const p of [w.game_port, w.query_port, w.rest_api_port, w.rcon_port]) {
      taken.set(p, w.display_name);
    }
  }
  const out = [];
  for (const [label, p] of Object.entries(ports)) {
    if (taken.has(p)) out.push({ port: p, label, usedBy: taken.get(p) });
  }
  return out;
}

// Async check: is a TCP port free to bind on the host right now?
function isPortFree(port) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (v) => { if (!settled) { settled = true; resolve(v); } };
    let srv;
    try {
      srv = net.createServer();
    } catch {
      return done(true); // can't probe — assume free rather than crash
    }
    srv.on("error", () => { try { srv.close(); } catch {} done(false); });
    srv.on("listening", () => { try { srv.close(() => done(true)); } catch { done(true); } });
    try {
      srv.listen(port, "127.0.0.1");
    } catch {
      done(true);
    }
    // safety timeout so we never hang a request
    setTimeout(() => done(true), 1500);
  });
}

module.exports = { suggestPorts, conflictsInRegistry, isPortFree };
