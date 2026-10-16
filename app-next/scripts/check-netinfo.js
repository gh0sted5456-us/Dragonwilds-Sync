const assert = require("assert");
const { publicIPv4 } = require("../lib/netinfo");

(async () => {
  assert.equal(await publicIPv4(async () => { throw new Error("offline"); }, 1), null);
  let calls = 0;
  const fetcher = async (url, options) => {
    calls++;
    assert.equal(url, "https://api.ipify.org?format=json");
    assert(options.signal);
    return { ok: true, json: async () => ({ ip: "203.0.113.7" }) };
  };
  assert.equal(await publicIPv4(fetcher, 60_002), "203.0.113.7");
  assert.equal(await publicIPv4(fetcher, 60_003), "203.0.113.7");
  assert.equal(calls, 1, "public IP should be cached instead of queried on every render");
  console.log("Public IP lookup and cache: OK");
})().catch((error) => { console.error(error); process.exitCode = 1; });
