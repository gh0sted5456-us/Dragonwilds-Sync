const assert = require("assert");
const http = require("http");
const discovery = require("../lib/sync/discovery");

(async () => {
  const server = http.createServer((req, res) => {
    if (req.url !== "/api/sync/public") { res.writeHead(404).end(); return; }
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ ok: true, worlds: [{ worldId: "friend-world", name: "Friends", syncPort: 4318, modCount: 2, modBadges: ["PAK"], rules: { access: "Private", passwordRequired: true } }] }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const port = server.address().port;
    const endpoint = discovery.parseEndpoint(`127.0.0.1:${port}`);
    assert.strictEqual(endpoint.address, "127.0.0.1");
    assert.strictEqual(endpoint.syncPort, port);
    const worlds = await discovery.probeDirect(`127.0.0.1:${port}`, { timeoutMs: 2000 });
    assert.strictEqual(worlds.length, 1);
    assert.strictEqual(worlds[0].worldId, "friend-world");
    assert.strictEqual(worlds[0].queriedIp, "127.0.0.1");
    assert.strictEqual(worlds[0].rules.passwordRequired, true);
    console.log("Direct IP discovery: OK");
  } finally { await new Promise((resolve) => server.close(resolve)); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
