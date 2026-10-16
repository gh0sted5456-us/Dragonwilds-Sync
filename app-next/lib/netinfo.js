// lib/netinfo.js
// Detects the machine's own LAN IPv4 address(es) so the UI can show players the
// address to actually connect to from another PC on the same network — instead of
// only 127.0.0.1, which is reachable *only from this same machine* and led users to
// believe the server was bound to loopback (issue #3).
const os = require("os");
const net = require("net");

let publicCache = { address: null, expires: 0, pending: null };

// Opt-in on the Server detail page only. Keep the LAN endpoint fast and never
// block page rendering on an external service or imply UDP reachability.
async function publicIPv4(fetcher = fetch, now = Date.now()) {
  if (now < publicCache.expires) return publicCache.address;
  if (publicCache.pending) return publicCache.pending;
  publicCache.pending = (async () => {
    let address = null;
    try {
      const response = await fetcher("https://api.ipify.org?format=json", { signal: AbortSignal.timeout(2500), cache: "no-store" });
      if (!response.ok) throw new Error("Public IP lookup failed");
      const value = (await response.json()).ip;
      if (net.isIP(value) !== 4) throw new Error("Public IP lookup returned an invalid IPv4 address");
      address = value;
    } catch { /* Offline, blocked, or timed out: keep a neutral unavailable state. */ }
    publicCache = { address, expires: now + (address ? 10 * 60_000 : 60_000), pending: null };
    return address;
  })();
  return publicCache.pending;
}

// Rank interfaces so a "real" Ethernet/Wi-Fi NIC wins over virtual adapters
// (Hyper-V, WSL, VMware, VirtualBox, Docker), which otherwise clutter the list.
function score(name) {
  const n = name.toLowerCase();
  if (/(vethernet|wsl|hyper-v|vmware|virtualbox|vbox|docker|loopback|tailscale|zerotier|radmin|hamachi)/.test(n)) return 0;
  if (/(ethernet|eth|en\d|lan)/.test(n)) return 3;
  if (/(wi-?fi|wlan|wireless)/.test(n)) return 2;
  return 1;
}

// All non-internal IPv4 addresses on the host, best candidate first. Each entry:
//   { address, iface, primary }
function lanAddresses() {
  const ifaces = os.networkInterfaces();
  const out = [];
  for (const [name, addrs] of Object.entries(ifaces)) {
    for (const a of addrs || []) {
      // node <18 exposes family as "IPv4"; >=18 as 4 — accept both.
      const isv4 = a.family === "IPv4" || a.family === 4;
      if (!isv4 || a.internal) continue;
      out.push({ address: a.address, iface: name, _score: score(name) });
    }
  }
  out.sort((x, y) => y._score - x._score || x.address.localeCompare(y.address));
  return out.map((e, i) => ({ address: e.address, iface: e.iface, primary: i === 0 }));
}

module.exports = { lanAddresses, publicIPv4 };
