const DEFAULT_TIMEOUT = 8000;

function endpoint(connection) {
  const address = String(connection?.address || connection?.internalIp || connection?.externalIp || "").trim();
  const worldId = String(connection?.worldId || "").trim();
  const port = Number(connection?.syncPort || 4318);
  if (!address || !/^[a-zA-Z0-9._:-]+$/.test(address) || !worldId || !Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("This World does not have a valid Sync endpoint.");
  }
  const host = address.includes(":") && !address.startsWith("[") ? `[${address}]` : address;
  return { address, worldId, port, base: `http://${host}:${port}/api/sync/public/${encodeURIComponent(worldId)}` };
}

async function readPayload(response) {
  try { return await response.json(); }
  catch { return {}; }
}

async function probe(connection, options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const timeoutMs = Math.min(Math.max(Number(options.timeoutMs || DEFAULT_TIMEOUT), 1000), 15000);
  const checkedAt = Date.now();
  let timer;
  try {
    const target = endpoint(connection);
    const controller = new AbortController();
    timer = setTimeout(() => controller.abort(), timeoutMs);
    const request = {
      cache: "no-store",
      signal: controller.signal,
      headers: {
        "X-RSDW-World-Password": String(connection?.password || ""),
        "X-RSDW-Client-Platform": connection?.service === "gamepass" || connection?.platform === "gamepass" ? "gamepass" : "steam",
      },
    };
    let response = await fetchImpl(`${target.base}/heartbeat`, request);
    // Older RSDW Sync hosts do not expose the compact endpoint. Their manifest
    // route is still a valid authenticated reachability check.
    if (response.status === 404) response = await fetchImpl(target.base, request);
    const payload = await readPayload(response);
    const latencyMs = Math.max(0, Date.now() - checkedAt);
    if (response.ok && (payload.ok || payload.manifest)) {
      return {
        state: "online", online: true, authenticated: true, checkedAt, latencyMs,
        gamePort: Number(payload.world?.gamePort || payload.manifest?.world?.gamePort || connection?.rules?.gamePort || 0) || null,
        revision: payload.revision || payload.manifest?.revision || null,
      };
    }
    if (response.status === 401 || response.status === 403) {
      return { state: "credentials", online: true, authenticated: false, checkedAt, latencyMs, error: "Credentials need attention" };
    }
    return { state: "offline", online: false, authenticated: false, checkedAt, latencyMs, error: String(payload.error || `HTTP ${response.status}`).slice(0, 160) };
  } catch (error) {
    return {
      state: "offline", online: false, authenticated: false, checkedAt,
      latencyMs: Math.max(0, Date.now() - checkedAt),
      error: error?.name === "AbortError" ? "Heartbeat timed out" : String(error?.message || "Server unavailable").slice(0, 160),
    };
  } finally { if (timer) clearTimeout(timer); }
}

module.exports = { DEFAULT_TIMEOUT, endpoint, probe };
