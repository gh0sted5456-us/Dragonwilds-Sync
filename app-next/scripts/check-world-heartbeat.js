const assert = require("assert");
const heartbeat = require("../lib/sync/heartbeat");

(async () => {
  const calls = [];
  const online = await heartbeat.probe({ address: "127.0.0.1", syncPort: 4318, worldId: "friends", password: "secret" }, {
    fetchImpl: async (url, request) => {
      calls.push({ url, password: request.headers["X-RSDW-World-Password"] });
      return { ok: true, status: 200, json: async () => ({ ok: true, world: { gamePort: 7777 } }) };
    },
  });
  assert.equal(online.state, "online");
  assert.equal(online.authenticated, true);
  assert.equal(online.gamePort, 7777);
  assert.equal(calls[0].password, "secret");
  assert(calls[0].url.endsWith("/api/sync/public/friends/heartbeat"));

  const unauthorized = await heartbeat.probe({ address: "host.example", syncPort: 4318, worldId: "friends" }, {
    fetchImpl: async () => ({ ok: false, status: 401, json: async () => ({ error: "no" }) }),
  });
  assert.equal(unauthorized.state, "credentials");
  assert.equal(unauthorized.online, true);

  let legacyCalls = 0;
  const legacy = await heartbeat.probe({ address: "host.example", syncPort: 4318, worldId: "old" }, {
    fetchImpl: async () => ++legacyCalls === 1
      ? { ok: false, status: 404, json: async () => ({}) }
      : { ok: true, status: 200, json: async () => ({ ok: true, manifest: { revision: "rev-1", world: { gamePort: 7777 } } }) },
  });
  assert.equal(legacy.state, "online");
  assert.equal(legacy.revision, "rev-1");
  assert.equal(legacyCalls, 2);
  console.log("Connected World heartbeat: OK");
})().catch((error) => { console.error(error); process.exitCode = 1; });
