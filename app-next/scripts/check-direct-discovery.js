const assert = require("assert");
const http = require("http");
const dgram = require("dgram");
const fs = require("fs");
const path = require("path");
const discovery = require("../lib/sync/discovery");

(async () => {
  const targets = discovery.broadcastTargets({
    ethernet: [{ family: "IPv4", address: "192.168.4.21", netmask: "255.255.255.0", internal: false }],
    wifi: [{ family: "IPv4", address: "10.20.3.7", netmask: "255.255.0.0", internal: false }],
    loopback: [{ family: "IPv4", address: "127.0.0.1", netmask: "255.0.0.0", internal: true }],
    pointToPoint: [{ family: "IPv4", address: "10.10.10.1", netmask: "255.255.255.255", internal: false }],
    v6: [{ family: "IPv6", address: "::1", internal: false }],
  });
  assert.deepEqual(targets, ["255.255.255.255", "192.168.4.255", "10.20.255.255"]);
  const packet = (value) => Buffer.from(JSON.stringify(value));
  const remote = { address: "127.0.0.1" };
  assert.equal(discovery.parseAdvertisement(packet({ magic: "foreign", action: "directory", syncPort: 4318 }), remote), null);
  assert.equal(discovery.parseAdvertisement(packet({ magic: discovery.MAGIC, action: "directory", syncPort: -1 }), remote), null);
  assert.equal(discovery.parseAdvertisement(Buffer.alloc(8193), remote), null);
  assert.equal(discovery.parseAdvertisement(Buffer.from("{broken"), remote), null);
  assert.equal(discovery.parseAdvertisement(packet({ magic: discovery.MAGIC, action: "directory", syncPort: 4318 }), { address: "host/path" }), null);
  assert.deepEqual(discovery.parseAdvertisement(packet({ magic: discovery.MAGIC, action: "directory", syncPort: 4318, addresses: ["evil.invalid"], password: "never-copy" }), remote), { queriedIp: "127.0.0.1", syncPort: 4318 });
  const legacy = discovery.parseAdvertisement(packet({ magic: discovery.MAGIC, action: "advertisement", worldId: "legacy", name: "Old host", syncPort: 4318 }), remote);
  assert.equal(legacy.worldId, "legacy"); assert.equal(legacy.rules.passwordRequired, true);
  assert.equal(discovery.status().broadcasting, false, "merely importing discovery must not open a listener");
  const server = http.createServer((req, res) => {
    if (req.url !== "/api/sync/public") { res.writeHead(404).end(); return; }
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ ok: true, worlds: [
      { worldId: "friend-world", name: "Friends", syncPort: server.address().port, modCount: 2, modBadges: ["PAK"], rules: { access: "Private", passwordRequired: true } },
      { worldId: "player-share", name: "Shared player profile", syncPort: server.address().port, modCount: 1, modBadges: ["RUNESCHEMA"], rules: { access: "Shared", passwordRequired: false } },
    ] }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const port = server.address().port;
    const endpoint = discovery.parseEndpoint(`127.0.0.1:${port}`);
    assert.strictEqual(endpoint.address, "127.0.0.1");
    assert.strictEqual(endpoint.syncPort, port);
    const worlds = await discovery.probeDirect(`127.0.0.1:${port}`, { timeoutMs: 2000 });
    assert.strictEqual(worlds.length, 2);
    assert.strictEqual(worlds[0].worldId, "friend-world");
    assert.strictEqual(worlds[0].queriedIp, "127.0.0.1");
    assert.strictEqual(worlds[0].rules.passwordRequired, true);
    const allocator = dgram.createSocket("udp4");
    await new Promise((resolve) => allocator.bind(0, "127.0.0.1", resolve));
    const udpPort = allocator.address().port;
    await new Promise((resolve) => allocator.close(resolve));
    const [active, same] = await Promise.all([
      discovery.start(null, { discoveryPort: udpPort, syncPort: port, bindHost: "127.0.0.1" }),
      discovery.start(null, { discoveryPort: udpPort, syncPort: port, bindHost: "127.0.0.1" }),
    ]);
    assert(active.broadcasting && same.broadcasting, "concurrent starts must await the same listener");
    const lan = await discovery.probe("127.0.0.1", { discoveryPort: udpPort, timeoutMs: 300 });
    assert.equal(lan.length, 2); assert.equal(lan[0].worldId, "friend-world");
    assert.equal(lan[1].worldId, "player-share", "all published worlds on a host must be discoverable");
    assert.equal(lan[0].rules.passwordRequired, true, "LAN preview must preserve password requirements");
    assert.equal(lan[0].queriedIp, "127.0.0.1");
    const wire = dgram.createSocket("udp4");
    await new Promise((resolve) => wire.bind(0, "127.0.0.1", resolve));
    const received = new Promise((resolve) => wire.once("message", (data) => resolve(JSON.parse(data))));
    wire.send(packet({ magic: discovery.MAGIC, action: "probe" }), udpPort, "127.0.0.1");
    const announced = await Promise.race([received, new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error("No UDP directory response")), 1500); timer.unref(); })]);
    await new Promise((resolve) => wire.close(resolve));
    assert.deepEqual(announced, { magic: discovery.MAGIC, action: "directory", syncPort: port }, "UDP must never contain credentials, file paths or manifests");
    discovery.stop();
    assert.equal(discovery.status().broadcasting, false);
    assert.deepEqual(await discovery.probe("127.0.0.1", { discoveryPort: udpPort, timeoutMs: 250 }), []);
    await assert.rejects(discovery.start(null, { discoveryPort: 70000 }), /Invalid/);
    const blocker = dgram.createSocket("udp4");
    await new Promise((resolve) => blocker.bind(0, "127.0.0.1", resolve));
    try {
      // Windows reports an exclusive UDP binding as EACCES; Unix uses EADDRINUSE.
      await assert.rejects(discovery.start(null, { discoveryPort: blocker.address().port, syncPort: port, bindHost: "127.0.0.1" }), /EADDRINUSE|EACCES/);
      assert(!discovery.status().broadcasting, "failed binding must not leave a fake active listener");
    } finally { await new Promise((resolve) => blocker.close(resolve)); }
    const root = path.resolve(__dirname, "..");
    const read = (file) => fs.readFileSync(path.join(root, file), "utf8");
    for (const file of ["app/api/sync/broadcast/route.js", "app/api/sync/discover/route.js"]) assert(read(file).includes("ra.requireAdmin(req)"), "LAN controls must remain local-admin only");
    assert(read("app/api/sync/broadcast/route.js").includes('dbm.getSetting("sync:lanDiscoveryEnabled", false) === true'));
    assert(read("electron/main.js").includes('localCloudApi("/api/sync/broadcast", { restore: true })'));
    assert(read("components/PlayerWorldLibrary.jsx").includes('world.queriedIp || address.trim()'), "LAN manifest imports must use the discovered responder address");
    assert(read("components/PlayerWorldLibrary.jsx").includes("password, service: platform"), "LAN manifests must go through normal authentication");
    console.log("Direct IP + LAN discovery: multi-adapter targets, UDP/TCP round-trip, credentials boundary, legacy compatibility, opt-in restore and shutdown: OK");
  } finally { discovery.stop(); await new Promise((resolve) => server.close(resolve)); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
